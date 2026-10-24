from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from common.markdown import render
from publications.models import Category, Publication


def story(slug, category='ai', status=Publication.Status.PUBLISHED, hours_ago=1, **fields):
    published_at = timezone.now() - timedelta(hours=hours_ago) if status == Publication.Status.PUBLISHED else None
    body = fields.pop('body_md', f'Text about {slug}.')
    publication = Publication.objects.create(
        external_id=slug, slug=slug, category=Category.objects.get(slug=category), title=f'Title {slug}',
        summary=f'Summary {slug}', body_md=body, body_html=render(body), status=status, published_at=published_at,
        **fields)
    publication.sources.create(title='Article', url='https://example.com/a', publisher='Example')
    return publication


class PublicApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_feed_shows_published_stories_newest_first(self):
        story('old', hours_ago=5)
        story('new', hours_ago=1)
        story('pending', status=Publication.Status.REVIEW)
        story('gone', status=Publication.Status.WITHDRAWN)

        response = self.client.get('/publications')

        self.assertEqual([item['slug'] for item in response.data['results']], ['new', 'old'])
        self.assertEqual(response.data['results'][0]['source_count'], 1)
        self.assertEqual(response.data['results'][0]['category'], {'slug': 'ai', 'name': 'AI'})
        self.assertIn('max-age=60', response['Cache-Control'])

    def test_feed_by_category(self):
        story('model', category='ai')
        story('hack', category='it')

        response = self.client.get('/publications?category=it')

        self.assertEqual([item['slug'] for item in response.data['results']], ['hack'])

    def test_story_with_text_sources_and_follow_ups(self):
        first = story('first', hours_ago=5)
        story('second', previous=first)
        story('hidden', previous=first, status=Publication.Status.REVIEW)

        detail = self.client.get('/publications/first').data
        follow_up = self.client.get('/publications/second').data

        self.assertEqual(detail['body_html'], '<p>Text about first.</p>')
        self.assertEqual(detail['sources'][0]['publisher'], 'Example')
        self.assertEqual([link['slug'] for link in detail['follow_ups']], ['second'])
        self.assertEqual(follow_up['previous']['slug'], 'first')

    def test_unpublished_story_is_not_found(self):
        story('pending', status=Publication.Status.REVIEW)

        self.assertEqual(self.client.get('/publications/pending').status_code, 404)

    def test_search(self):
        story('etf', body_md='Bitcoin ETFs recorded outflows on Thursday.')
        story('php', body_md='PHP released emergency patches.')
        story('draft', body_md='Bitcoin draft.', status=Publication.Status.REVIEW)

        response = self.client.get('/search', {'q': 'bitcoin outflows'})

        self.assertEqual([item['slug'] for item in response.data['results']], ['etf'])
        self.assertEqual(self.client.get('/search').data['results'], [])

    def test_categories(self):
        self.assertEqual([c['slug'] for c in self.client.get('/categories').data], ['it', 'ai', 'crypto'])
