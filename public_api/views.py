from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import Count, F
from django.utils.cache import patch_cache_control
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.pagination import PageNumberPagination

from publications.models import Category, Publication

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
