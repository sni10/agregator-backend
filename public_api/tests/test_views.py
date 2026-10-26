from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from publications.models import Publication

from .test_public_api import story

BROWSER = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/141.0 Safari/537.36'


class ViewCountTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.story = story('launch')

    def view(self, slug='launch', ip='10.0.0.1', agent=BROWSER, **headers):
        return self.client.post(f'/publications/{slug}/view', HTTP_X_FORWARDED_FOR=ip, HTTP_USER_AGENT=agent,
                                **headers)

    def views(self):
        self.story.refresh_from_db()
        return self.story.views

    def test_once_a_day_per_ip(self):
        self.assertEqual(self.view().status_code, 204)
        self.view()
        self.view(ip='10.0.0.2')
        self.assertEqual(self.views(), 2)

    def test_bots_are_not_counted(self):
        self.assertEqual(self.view(agent='Mozilla/5.0 (compatible; Googlebot/2.1)').status_code, 204)
        self.view(agent='Mozilla/5.0 HeadlessChrome/141.0')
        self.assertEqual(self.views(), 0)

    def test_only_published_stories(self):
        story('draft', status=Publication.Status.REVIEW)
        self.assertEqual(self.view('draft').status_code, 404)
        self.assertEqual(self.view('nope').status_code, 404)

    def test_a_dead_token_does_not_matter(self):
        self.assertEqual(self.view(HTTP_AUTHORIZATION='Bearer expired').status_code, 204)
        self.assertEqual(self.views(), 1)

    def test_shown_in_the_feed_and_the_story(self):
        self.view()
        self.assertEqual(self.client.get('/publications').data['results'][0]['views'], 1)
        self.assertEqual(self.client.get('/publications/launch').data['views'], 1)
