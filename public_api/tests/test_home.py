from django.test import TestCase
from rest_framework.test import APIClient

from publications import services
from publications.models import Publication

from .test_public_api import story


def add_sources(publication, *publishers):
    for publisher in publishers:
        publication.sources.create(title='Article', url=f'https://{publisher}.test/a', publisher=publisher)
    return publication


def slugs(stories):
    return [s['slug'] for s in stories]


class HomeTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_the_story_with_most_sources_leads_and_none_shows_twice(self):
        for hour in range(1, 12):
            story(f'ai-{hour}', category='ai', hours_ago=hour)
        for hour in range(1, 4):
            story(f'it-{hour}', category='it', hours_ago=hour + 20)
        add_sources(Publication.objects.get(slug='ai-5'), 'The Register', 'Decrypt')
        story('pending', status=Publication.Status.REVIEW)

        home = self.client.get('/home').data

        self.assertEqual(slugs(home['lead']), ['ai-5', 'ai-1', 'ai-2', 'ai-3'])
        self.assertEqual(slugs(home['latest']), ['ai-4', 'ai-6', 'ai-7', 'ai-8', 'ai-9', 'ai-10'])
        self.assertEqual([(s['category']['slug'], slugs(s['stories'])) for s in home['sections']],
                         [('it', ['it-1', 'it-2', 'it-3']), ('ai', ['ai-11'])])  # crypto has none: no block
        self.assertEqual(home['most_read'], [])
        self.assertIn('max-age=60', self.client.get('/home')['Cache-Control'])

    def test_most_read_of_the_last_days(self):
        story('popular', views=40)
        story('read', views=3)
        story('old', views=900, hours_ago=24 * 5)
        story('unread')

        self.assertEqual(slugs(self.client.get('/home').data['most_read']), ['popular', 'read'])

    def test_empty_site(self):
        self.assertEqual(self.client.get('/home').data, {'lead': [], 'latest': [], 'sections': [], 'most_read': []})

    def test_cards_name_the_publishers_once_each(self):
        add_sources(story('a'), 'Decrypt', 'Example', 'The Block')

        card = self.client.get('/publications').data['results'][0]

        self.assertEqual(card['publishers'], ['Example', 'Decrypt', 'The Block'])
        self.assertEqual(card['source_count'], 4)


class TrendingTagsTests(TestCase):
    def test_tags_of_the_last_week_with_two_stories_or_more(self):
        for slug in ('a', 'b', 'c'):
            services.set_tags(story(slug), ['OpenAI', 'Bitcoin'] if slug != 'c' else ['OpenAI'])
        services.set_tags(story('d'), ['Lonely'])
        services.set_tags(story('old', hours_ago=24 * 10), ['Stale'])
        services.set_tags(story('old-2', hours_ago=24 * 10), ['Stale'])
        services.set_tags(story('draft', status=Publication.Status.REVIEW), ['Bitcoin', 'Lonely'])

        response = APIClient().get('/tags')

        self.assertEqual(response.data, [{'slug': 'openai', 'name': 'OpenAI', 'count': 3},
                                         {'slug': 'bitcoin', 'name': 'Bitcoin', 'count': 2}])
