from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.services.token_pairs import TokenPairService
from publications.models import Publication, Rating

from .test_public_api import story


def reader(email):
    user = User.objects.create_user(email, email, 'x')
    return APIClient(headers={'Authorization': f'Bearer {TokenPairService().issue(user).access}'})


class RatingApiTests(TestCase):
    def test_points_add_up_to_the_cap(self):
        story('model-x')
        anna, bob = reader('anna@example.com'), reader('bob@example.com')

        self.assertEqual(anna.post('/publications/model-x/rating', {'points': 70}).data, {'rating': 70, 'given': 70, 'left': 30})
        self.assertEqual(anna.post('/publications/model-x/rating', {'points': 50}).data, {'rating': 100, 'given': 100, 'left': 0})
        self.assertEqual(anna.post('/publications/model-x/rating', {'points': 1}).data['rating'], 100)  # capped
        self.assertEqual(bob.post('/publications/model-x/rating', {'points': 100}).data['rating'], 200)
        self.assertEqual(bob.get('/publications/model-x/rating').data, {'rating': 200, 'given': 100, 'left': 0})
        self.assertEqual(APIClient().get('/publications/model-x').data['rating'], 200)

    def test_bad_points_and_strangers(self):
        story('model-x')
        story('pending', status=Publication.Status.REVIEW)
        anna = reader('anna@example.com')

        for points in (0, 101, 'x', None):
            self.assertEqual(anna.post('/publications/model-x/rating', {'points': points}, format='json').status_code, 400)
        self.assertEqual(anna.post('/publications/pending/rating', {'points': 5}).status_code, 404)
        self.assertEqual(anna.get('/publications/model-x/rating').data, {'rating': 0, 'given': 0, 'left': 100})

    def test_guests_by_ip(self):
        story('model-x')
        home = APIClient(REMOTE_ADDR='10.0.0.1')
        cafe = APIClient(REMOTE_ADDR='10.0.0.2')

        self.assertEqual(home.post('/publications/model-x/rating', {'points': 80}).data['left'], 20)
        self.assertEqual(home.post('/publications/model-x/rating', {'points': 80}).data['given'], 100)  # capped
        self.assertEqual(cafe.post('/publications/model-x/rating', {'points': 10}).data['rating'], 110)
        self.assertEqual(reader('anna@example.com').post('/publications/model-x/rating', {'points': 5}).data,
                         {'rating': 115, 'given': 5, 'left': 95})  # signed in: their own 100
        self.assertEqual(Rating.objects.filter(user=None).count(), 2)
        self.assertNotIn('10.0.0.1', Rating.objects.values_list('guest', flat=True))  # hashed
