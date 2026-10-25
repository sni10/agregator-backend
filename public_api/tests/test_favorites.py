from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.services.token_pairs import TokenPairService
from publications.models import Publication

from .test_public_api import story


class FavoriteApiTests(TestCase):
    def setUp(self):
        user = User.objects.create_user('anna@example.com', 'anna@example.com', 'x')
        access = TokenPairService().issue(user).access
        self.client = APIClient(headers={'Authorization': f'Bearer {access}'})

    def test_add_list_and_remove(self):
        story('older', hours_ago=5)
        story('newer', hours_ago=1)

        self.assertEqual(self.client.put('/me/favorites/older').status_code, 204)
        self.client.put('/me/favorites/newer')
        self.client.put('/me/favorites/older')  # twice: still one

        listed = self.client.get('/me/favorites')
        self.assertEqual([item['slug'] for item in listed.data['results']], ['newer', 'older'])  # last added first
        self.assertIn('no-store', listed['Cache-Control'])
        self.assertEqual(self.client.get('/me/favorites/slugs').data, ['newer', 'older'])

        self.assertEqual(self.client.delete('/me/favorites/newer').status_code, 204)
        self.assertEqual(self.client.get('/me/favorites/slugs').data, ['older'])

    def test_only_published_stories(self):
        story('pending', status=Publication.Status.REVIEW)
        withdrawn = story('gone')
        self.client.put('/me/favorites/gone')
        Publication.objects.filter(pk=withdrawn.pk).update(status=Publication.Status.WITHDRAWN)

        self.assertEqual(self.client.put('/me/favorites/pending').status_code, 404)
        self.assertEqual(self.client.get('/me/favorites').data['count'], 0)
        self.assertEqual(self.client.get('/me/favorites/slugs').data, [])

    def test_readers_only(self):
        story('model-x')

        anonymous = APIClient()
        self.assertEqual(anonymous.put('/me/favorites/model-x').status_code, 401)
        self.assertEqual(anonymous.get('/me/favorites').status_code, 401)
        self.assertEqual(anonymous.get('/publications').status_code, 200)  # reading stays public
