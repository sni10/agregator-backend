from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import Count, F
from django.shortcuts import get_object_or_404
from django.utils.cache import patch_cache_control
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from publications.models import Category, Favorite, Publication

from .serializers import CategorySerializer, PublicationDetailSerializer, PublicationListSerializer

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


class CategoryListView(ReadView, generics.ListAPIView):
    serializer_class = CategorySerializer
    queryset = Category.objects.all()
    pagination_class = None
    max_age = DETAIL_MAX_AGE


@extend_schema(parameters=[OpenApiParameter('q', str, required=True, description='Words to look for')])
class SearchView(ReadView, generics.ListAPIView):
    """Full-text search over published stories (PostgreSQL, English), best match first."""

    serializer_class = PublicationListSerializer
    pagination_class = FeedPagination

    def get_queryset(self):
        text = self.request.query_params.get('q', '').strip()[:200]
        if not text:
            return Publication.objects.none()
        query = SearchQuery(text, search_type='websearch', config='english')
        vector = SearchVector('title', 'summary', 'body_md', config='english')
        return (published().annotate(search=vector, rank=SearchRank(vector, query)).filter(search=query)
                .order_by(F('rank').desc(), '-published_at'))


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
