from django.test import TestCase
from rest_framework.test import APIClient

from publications.models import Publication

from .test_public_api import story


def slugs(response):
    return [item['slug'] for item in response.data['results']]


class SearchTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_filters_by_category_period_and_sources(self):
        old = story('etf-old', category='crypto', hours_ago=24 * 10, body_md='Bitcoin ETFs saw inflows.')
        story('etf-new', category='crypto', hours_ago=2, body_md='Bitcoin ETFs saw outflows.')
        story('mining', category='it', hours_ago=3, body_md='Bitcoin mining moves to Texas.')
        old.sources.create(title='Second', url='https://example.com/b', publisher='Other')

        self.assertEqual(slugs(self.client.get('/search', {'q': 'bitcoin', 'category': 'crypto', 'sort': 'newest'})),
                         ['etf-new', 'etf-old'])
        self.assertEqual(slugs(self.client.get('/search', {'q': 'bitcoin', 'since': 'week', 'sort': 'newest'})),
                         ['etf-new', 'mining'])
        self.assertEqual(slugs(self.client.get('/search', {'q': 'bitcoin', 'sources': 2})), ['etf-old'])

    def test_filters_without_words_list_the_newest(self):
        story('a', category='ai', hours_ago=5)
        story('b', category='ai', hours_ago=1)
        story('c', category='it')

        self.assertEqual(slugs(self.client.get('/search', {'category': 'ai'})), ['b', 'a'])
        self.assertEqual(slugs(self.client.get('/search', {'q': '  ?! '})), [])

    def test_websearch_syntax_works(self):
        story('etf', body_md='Bitcoin ETFs recorded outflows.')
        story('mining', body_md='Bitcoin mining difficulty rose.')

        self.assertEqual(slugs(self.client.get('/search', {'q': 'bitcoin -mining'})), ['etf'])

    def test_a_typo_still_finds_the_story_by_its_title(self):
        etf = story('etf')
        Publication.objects.filter(pk=etf.pk).update(title='Ethereum staking ETF approved')

        exact = self.client.get('/search', {'q': 'ethereum'})
        typo = self.client.get('/search', {'q': 'etherium staking'})

        self.assertEqual((slugs(exact), exact.data['fuzzy']), (['etf'], False))
        self.assertEqual((slugs(typo), typo.data['fuzzy']), (['etf'], True))
        self.assertEqual(slugs(self.client.get('/search', {'q': 'quantum chips'})), [])


class SuggestTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        for slug, title, category in [('etf', 'Bitcoin ETFs see record outflows', 'crypto'),
                                      ('php', 'PHP ships emergency patches', 'it')]:
            Publication.objects.filter(pk=story(slug, category=category).pk).update(title=title)
        story('draft', status=Publication.Status.REVIEW)

    def test_the_last_word_is_a_prefix(self):
        response = self.client.get('/search/suggest', {'q': 'bitc'})

        self.assertEqual(response.data, [{'slug': 'etf', 'title': 'Bitcoin ETFs see record outflows',
                                          'category': 'crypto'}])
        self.assertEqual([s['slug'] for s in self.client.get('/search/suggest', {'q': 'emergency pat'}).data],
                         ['php'])
        self.assertIn('max-age=60', response['Cache-Control'])

    def test_typo_fallback_and_junk(self):
        self.assertEqual([s['slug'] for s in self.client.get('/search/suggest', {'q': 'bitcoen'}).data], ['etf'])
        for junk in ('', 'b', "':* & | !(", 'zzzzzz'):
            self.assertEqual(self.client.get('/search/suggest', {'q': junk}).data, [], junk)
