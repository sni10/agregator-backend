"""For search engines and readers: sitemap.xml, news-sitemap.xml (Google News) and rss.xml. Served on the front's
domain (Caddy proxies these paths here); every link points to the front (SITE_URL), never to the API."""
from datetime import timedelta
from email.utils import format_datetime

from django.conf import settings
from django.db.models import Count, Q
from django.shortcuts import render
from django.utils import timezone
from django.utils.cache import patch_cache_control

from publications.images import variants
from publications.models import Category, Publication, Tag

MAX_AGE = 300
NEWS_WINDOW = timedelta(days=2)  # Google News reads only stories of the last two days
NEWS_LIMIT = 1000
RSS_LIMIT = 50
PAGES = ['/', '/about']  # besides the categories and the stories


def stories():
    return Publication.objects.published().select_related('category', 'image').order_by('-published_at', '-id')


def sitemap(request):
    items = [{'loc': page} for page in PAGES]
    items += [{'loc': f'/{category.slug}'} for category in Category.objects.all()]
    items += [{'loc': f'/tag/{slug}'} for slug in indexed_tags()]
    items += [{'loc': f'/news/{story.slug}', 'lastmod': story.updated_at, 'image': _cover(story)}
              for story in stories()]
    return _xml(request, 'feeds/sitemap.xml', {'items': items})


def indexed_tags() -> list[str]:
    """Slugs of the tags with enough published stories for a page worth indexing."""
    count = Count('publications', filter=Q(publications__in=Publication.objects.published()))
    return list(Tag.objects.annotate(count=count).filter(count__gte=Tag.MIN_STORIES).order_by('slug')
                .values_list('slug', flat=True))


def news_sitemap(request):
    recent = stories().filter(published_at__gte=timezone.now() - NEWS_WINDOW)[:NEWS_LIMIT]
    return _xml(request, 'feeds/news-sitemap.xml', {'stories': recent})


def rss(request):
    items = [{'story': story, 'pub_date': format_datetime(story.published_at), 'image': _cover(story)}
             for story in stories()[:RSS_LIMIT]]
    return _xml(request, 'feeds/rss.xml', {'items': items, 'description': 'IT, AI and crypto news',
                                           'content_type': 'application/rss+xml'})


def _cover(story: Publication) -> str | None:
    return variants(story.image)[0][1] if story.image else None


def _xml(request, template: str, context: dict):
    content_type = context.pop('content_type', 'application/xml')
    response = render(request, template, {**context, 'site_url': settings.SITE_URL, 'site_name': settings.SITE_NAME},
                      content_type=f'{content_type}; charset=utf-8')
    patch_cache_control(response, public=True, max_age=MAX_AGE)
    return response
