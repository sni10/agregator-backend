from xml.etree import ElementTree

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from publications import services
from publications.models import Publication, Tag
from publishing_api.tests.test_publishing_api import KEY, URL, payload

from .test_feeds import NS
from .test_public_api import story


@override_settings(PUBLISHING_API_KEY=KEY)
class SetTagsTests(TestCase):
    def setUp(self):
        self.client = APIClient(headers={'X-Api-Key': KEY})
        self.client.post(URL, payload(), format='json')

    def put(self, tags):
        return self.client.put(f'{URL}/event-187/tags', {'tags': tags}, format='json')

    def test_tags_are_created_once_whatever_the_spelling(self):
        response = self.put(['Bitcoin Core', '  bitcoin   core ', 'Security bugs'])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(sorted(response.data['tags']), ['Bitcoin Core', 'Security bugs'])
        self.assertEqual(response.data['revision'], 1)  # the text is unchanged
        story('other')
        services.set_tags(Publication.objects.get(slug='other'), ['BITCOIN CORE'])
        self.assertEqual(Tag.objects.get(slug='bitcoin-core').name, 'Bitcoin Core')
        self.assertEqual(Tag.objects.count(), 2)

    def test_replaced_not_added(self):
        self.put(['Bitcoin', 'Security bugs'])
        self.assertEqual(self.put(['Bitcoin']).data['tags'], ['Bitcoin'])

    def test_needs_the_key_and_a_story(self):
        self.assertEqual(APIClient().put(f'{URL}/event-187/tags', {'tags': []}, format='json').status_code, 403)
        self.assertEqual(self.client.put(f'{URL}/nope/tags', {'tags': []}, format='json').status_code, 404)
        self.assertEqual(self.put(['x'] * 9).status_code, 400)


@override_settings(SITE_URL='https://renews.test')
class TagPageTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        for slug in ('a', 'b'):
            services.set_tags(story(slug), ['OpenAI', 'AI coding agents'])
        services.set_tags(story('draft', status=Publication.Status.REVIEW), ['OpenAI'])

    def test_heading_counts_published_stories_only(self):
        response = self.client.get('/tags/openai')
        self.assertEqual(response.data, {'slug': 'openai', 'name': 'OpenAI', 'count': 2, 'indexed': False})
        services.set_tags(story('c'), ['OpenAI'])
        self.assertTrue(self.client.get('/tags/openai').data['indexed'])

    def test_unknown_or_empty_tag_is_404(self):
        Tag.objects.create(slug='empty', name='Empty')
        self.assertEqual(self.client.get('/tags/empty').status_code, 404)
        self.assertEqual(self.client.get('/tags/nope').status_code, 404)

    def test_feed_by_tag_and_tags_on_the_story(self):
        story('untagged')
        feed = self.client.get('/publications', {'tag': 'ai-coding-agents'}).data['results']
        self.assertEqual([s['slug'] for s in feed], ['b', 'a'])
        self.assertEqual(self.client.get('/publications/a').data['tags'],
                         [{'slug': 'ai-coding-agents', 'name': 'AI coding agents'},
                          {'slug': 'openai', 'name': 'OpenAI'}])

    def test_sitemap_has_tags_with_enough_stories(self):
        services.set_tags(story('c'), ['OpenAI'])
        xml = ElementTree.fromstring(self.client.get('/sitemap.xml').content)
        locations = [loc.text for loc in xml.findall('s:url/s:loc', NS)]
        self.assertIn('https://renews.test/tag/openai', locations)
        self.assertNotIn('https://renews.test/tag/ai-coding-agents', locations)
