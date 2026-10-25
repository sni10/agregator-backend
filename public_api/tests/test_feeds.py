from xml.etree import ElementTree

from django.test import TestCase, override_settings

from publications.models import Publication

from .test_public_api import story

NS = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9', 'news': 'http://www.google.com/schemas/sitemap-news/0.9'}


@override_settings(SITE_URL='https://renews.test', SITE_NAME='Renews')
class FeedTests(TestCase):
    def get(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertIn('max-age=300', response['Cache-Control'])
        return response, ElementTree.fromstring(response.content)

    def test_sitemap_lists_pages_categories_and_published_stories_on_the_front(self):
        story('model-x')
        story('pending', status=Publication.Status.REVIEW)

        _, xml = self.get('/sitemap.xml')

        locations = [loc.text for loc in xml.findall('s:url/s:loc', NS)]
        self.assertEqual(locations, ['https://renews.test/', 'https://renews.test/about', 'https://renews.test/it',
                                     'https://renews.test/ai', 'https://renews.test/crypto',
                                     'https://renews.test/news/model-x'])

    def test_news_sitemap_has_only_the_last_two_days(self):
        story('fresh', hours_ago=3)
        story('old', hours_ago=72)

        _, xml = self.get('/news-sitemap.xml')

        self.assertEqual([loc.text for loc in xml.findall('s:url/s:loc', NS)], ['https://renews.test/news/fresh'])
        self.assertEqual(xml.find('s:url/news:news/news:publication/news:name', NS).text, 'Renews')
        self.assertEqual(xml.find('s:url/news:news/news:title', NS).text, 'Title fresh')

    def test_rss_escapes_titles(self):
        Publication.objects.filter(pk=story('ampersand').pk).update(title='AT&T <ships> 5G')

        response, xml = self.get('/rss.xml')

        self.assertTrue(response['Content-Type'].startswith('application/rss+xml'))
        item = xml.find('channel/item')
        self.assertEqual((item.find('title').text, item.find('link').text),
                         ('AT&T <ships> 5G', 'https://renews.test/news/ampersand'))
