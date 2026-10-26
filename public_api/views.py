import hashlib
import re
from datetime import timedelta

from django.core.cache import cache
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector, TrigramWordSimilarity
from django.db.models import Count, F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.cache import patch_cache_control
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from publications.models import Category, Favorite, Publication

from . import coins
from .serializers import (CategorySerializer, PriceSerializer, PublicationDetailSerializer,
                          PublicationListSerializer, SuggestionSerializer)

LIST_MAX_AGE = 60  # seconds: the feed changes a few times a day, the SSR micro-cache sits in front anyway
DETAIL_MAX_AGE = 300


class FeedPagination(PageNumberPagination):
    page_size = 20


class ReadView:
    throttle_scope = 'read'
    max_age = LIST_MAX_AGE

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if response.status_code == 200:
            patch_cache_control(response, public=True, max_age=self.max_age)
        return response


def published():
    return (Publication.objects.published().select_related('category', 'image')
            .annotate(source_count=Count('sources', distinct=True)))


@extend_schema(parameters=[
    OpenApiParameter('category', str, description='it | ai | crypto'),
    OpenApiParameter('type', str, description='event | digest'),
])
class PublicationListView(ReadView, generics.ListAPIView):
    """The feed: published stories, newest first."""

    serializer_class = PublicationListSerializer
    pagination_class = FeedPagination

    def get_queryset(self):
        stories = published()
        if category := self.request.query_params.get('category'):
            stories = stories.filter(category__slug=category)
        if kind := self.request.query_params.get('type'):
            stories = stories.filter(type=kind)
        return stories.order_by('-published_at', '-id')


class PublicationDetailView(ReadView, generics.RetrieveAPIView):
    """One story with its text, sources and follow-ups."""

    serializer_class = PublicationDetailSerializer
    lookup_field = 'slug'
    max_age = DETAIL_MAX_AGE

    def get_queryset(self):
        return published().select_related('previous').prefetch_related('sources')


BOT = re.compile(r'bot|crawl|spider|slurp|preview|headless|lighthouse', re.IGNORECASE)


class ViewCountView(APIView):
    """A reader opened the story: the front sends this from the browser after the page shows (most bots run no
    scripts, the rest are told apart by User-Agent). One view per IP, story and day; the IP is kept only hashed,
    in the cache. Always 204 for a published story, counted or not."""

    authentication_classes = []  # anyone; a stale token must not turn this into a 401
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'read'

    @extend_schema(request=None, responses={204: None, 404: None})
    def post(self, request, slug):
        stories = Publication.objects.published().filter(slug=slug)
        if not stories.exists():
            return Response(status=status.HTTP_404_NOT_FOUND)
        if not BOT.search(request.headers.get('User-Agent', '')):
            day = timezone.now().date().isoformat()
            ip = ScopedRateThrottle().get_ident(request)
            mark = 'view:' + hashlib.sha256(f'{ip}|{slug}|{day}'.encode()).hexdigest()
            if cache.add(mark, 1, timeout=24 * 3600):
                stories.update(views=F('views') + 1)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CategoryListView(ReadView, generics.ListAPIView):
    serializer_class = CategorySerializer
    queryset = Category.objects.all()
    pagination_class = None
    max_age = DETAIL_MAX_AGE


SINCE = {'day': timedelta(days=1), 'week': timedelta(weeks=1), 'month': timedelta(days=31),
         'year': timedelta(days=366)}
FUZZY_MIN = 0.3  # word similarity of a title to the query when the exact search finds nothing (typos)


def words(text: str, limit: int = 8) -> list[str]:
    return re.findall(r'\w+', text)[:limit]


class SearchPagination(FeedPagination):
    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        response.data['fuzzy'] = getattr(self.request, 'search_fuzzy', False)
        return response

    def get_paginated_response_schema(self, schema):
        schema = super().get_paginated_response_schema(schema)
        schema['properties']['fuzzy'] = {
            'type': 'boolean', 'description': 'Nothing matched exactly: these are close matches (typos)'}
        return schema


@extend_schema(parameters=[
    OpenApiParameter('q', str, description='Words to look for; empty with a filter: the filtered feed'),
    OpenApiParameter('category', str, description='it | ai | crypto'),
    OpenApiParameter('since', str, enum=list(SINCE), description='Published in the last day, week, month, year'),
    OpenApiParameter('sources', int, description='At least this many sources'),
    OpenApiParameter('sort', str, enum=['relevance', 'newest'], description='Default: relevance (newest without q)'),
])
class SearchView(ReadView, generics.ListAPIView):
    """Full-text search over published stories (PostgreSQL, English) with filters. When the words match nothing,
    titles that look like them (pg_trgm), so a typo still finds the story: `fuzzy` is then true."""

    serializer_class = PublicationListSerializer
    pagination_class = SearchPagination

    def filtered(self):
        params = self.request.query_params
        stories = published()
        if category := params.get('category'):
            stories = stories.filter(category__slug=category)
        if since := SINCE.get(params.get('since', '')):
            stories = stories.filter(published_at__gte=timezone.now() - since)
        if (sources := params.get('sources', '')).isdigit() and int(sources) > 1:
            stories = stories.filter(source_count__gte=int(sources))
        return stories

    def get_queryset(self):
        params = self.request.query_params
        text = params.get('q', '').strip()[:200]  # websearch syntax: "exact phrase", -word, or
        filtered = any(params.get(name) for name in ('category', 'since', 'sources'))
        newest = ('-published_at', '-id')
        if not words(text):
            return self.filtered().order_by(*newest) if filtered else Publication.objects.none()

        query = SearchQuery(text, search_type='websearch', config='english')
        vector = SearchVector('title', 'summary', 'body_md', config='english')
        stories = self.filtered().annotate(search=vector, rank=SearchRank(vector, query)).filter(search=query)
        if not stories.exists():
            self.request.search_fuzzy = True
            stories = (self.filtered().annotate(rank=TrigramWordSimilarity(' '.join(words(text, 20)), 'title'))
                       .filter(rank__gte=FUZZY_MIN))
        if params.get('sort') == 'newest':
            return stories.order_by(*newest)
        return stories.order_by(F('rank').desc(), *newest)


@extend_schema(parameters=[OpenApiParameter('q', str, required=True, description='What the reader has typed so far')],
               responses=SuggestionSerializer(many=True))
class SuggestView(ReadView, APIView):
    """Titles for the search box while the reader types: the last word counts as a prefix ("bitc" -> Bitcoin),
    with a typo-tolerant fallback. At most 6, best first."""

    LIMIT = 6

    def get(self, request):
        terms = [t.lower() for t in words(request.query_params.get('q', '')[:100])]
        if not terms or len(''.join(terms)) < 2:
            return Response([])
        # raw tsquery from \w+ words only: nothing the reader types can break its syntax
        raw = ' & '.join([*terms[:-1], f'{terms[-1]}:*'])
        query = SearchQuery(raw, search_type='raw', config='english')
        vector = SearchVector('title', 'summary', config='english')
        stories = Publication.objects.published().select_related('category')
        found = list(stories.annotate(search=vector, rank=SearchRank(vector, query)).filter(search=query)
                     .order_by(F('rank').desc(), '-published_at')[:self.LIMIT])
        if not found:
            found = list(stories.annotate(rank=TrigramWordSimilarity(' '.join(terms), 'title'))
                         .filter(rank__gte=FUZZY_MIN).order_by(F('rank').desc(), '-published_at')[:self.LIMIT])
        return Response(SuggestionSerializer(found, many=True).data)


class PriceView(ReadView, APIView):
    """USD prices and 24 h change of the coins stories name (`coins` of a story), from CoinGecko, a couple of
    minutes old at most. 503 when CoinGecko is down and nothing is cached."""

    @extend_schema(responses={200: PriceSerializer(many=True), 503: OpenApiResponse(description='No prices now')})
    def get(self, request):
        rows = coins.prices()
        if rows is None:
            return Response({'detail': 'Prices are unavailable.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(PriceSerializer(rows, many=True).data)


class Private:
    """A reader's own data: never cached by browsers' shared caches, Cloudflare or the SSR micro-cache."""

    permission_classes = [IsAuthenticated]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        patch_cache_control(response, private=True, no_store=True)
        return response


class FavoriteListView(Private, generics.ListAPIView):
    """The reader's favorites: published stories, the last added first."""

    serializer_class = PublicationListSerializer
    pagination_class = FeedPagination

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):  # schema generation: no real user
            return Publication.objects.none()
        return published().filter(favorited_by__user=self.request.user).order_by('-favorited_by__created_at')


class FavoriteSlugsView(Private, APIView):
    @extend_schema(summary='Slugs of all favorite stories: the front marks them in any list',
                   responses={200: OpenApiResponse(description='["slug", ...]')})
    def get(self, request):
        slugs = (Favorite.objects.filter(user=request.user, publication__in=Publication.objects.published())
                 .order_by('-created_at').values_list('publication__slug', flat=True))
        return Response(list(slugs))


class FavoriteView(Private, APIView):
    @extend_schema(summary='Add a story to favorites', request=None,
                   responses={204: OpenApiResponse(description='Added (or already there)'),
                              404: OpenApiResponse(description='No published story with this slug')})
    def put(self, request, slug):
        publication = get_object_or_404(Publication.objects.published(), slug=slug)
        Favorite.objects.get_or_create(user=request.user, publication=publication)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(summary='Remove a story from favorites',
                   responses={204: OpenApiResponse(description='Removed (or was not there)')})
    def delete(self, request, slug):
        Favorite.objects.filter(user=request.user, publication__slug=slug).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
