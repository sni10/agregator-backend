from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.services.token_pairs import TokenPairService
from publications.models import Publication, Rating

from .test_public_api import story


def reader(email):
    user = User.objects.create_user(email, email, 'x')
    return APIClient(headers={'Authorization': f'Bearer {TokenPairService().issue(user).access}'})


class RatingApiTests(TestCase):
    def test_points_add_up_to_the_cap(self):
        story('model-x', rating=0)  # no random start: exact sums
        anna, bob = reader('anna@example.com'), reader('bob@example.com')

        self.assertEqual(anna.post('/publications/model-x/rating', {'points': 70}).data, {'rating': 70, 'given': 70, 'left': 30})
        self.assertEqual(anna.post('/publications/model-x/rating', {'points': 50}).data, {'rating': 100, 'given': 100, 'left': 0})
        self.assertEqual(anna.post('/publications/model-x/rating', {'points': 1}).data['rating'], 100)  # capped
        self.assertEqual(bob.post('/publications/model-x/rating', {'points': 100}).data['rating'], 200)
        self.assertEqual(bob.get('/publications/model-x/rating').data, {'rating': 200, 'given': 100, 'left': 0})
        self.assertEqual(APIClient().get('/publications/model-x').data['rating'], 200)

    def test_bad_points_and_strangers(self):
        story('model-x', rating=0)  # no random start: exact sums
        story('pending', status=Publication.Status.REVIEW)
        anna = reader('anna@example.com')

        for points in (0, 101, 'x', None):
            self.assertEqual(anna.post('/publications/model-x/rating', {'points': points}, format='json').status_code, 400)
        self.assertEqual(anna.post('/publications/pending/rating', {'points': 5}).status_code, 404)
        self.assertEqual(anna.get('/publications/model-x/rating').data, {'rating': 0, 'given': 0, 'left': 100})

    def test_guests_by_ip(self):
        story('model-x', rating=0)  # no random start: exact sums
        home = APIClient(REMOTE_ADDR='10.0.0.1')
        cafe = APIClient(REMOTE_ADDR='10.0.0.2')

        self.assertEqual(home.post('/publications/model-x/rating', {'points': 80}).data['left'], 20)
        self.assertEqual(home.post('/publications/model-x/rating', {'points': 80}).data['given'], 100)  # capped
        self.assertEqual(cafe.post('/publications/model-x/rating', {'points': 10}).data['rating'], 110)
        self.assertEqual(reader('anna@example.com').post('/publications/model-x/rating', {'points': 5}).data,
                         {'rating': 115, 'given': 5, 'left': 95})  # signed in: their own 100
        self.assertEqual(Rating.objects.filter(user=None).count(), 2)
        self.assertNotIn('10.0.0.1', Rating.objects.values_list('guest', flat=True))  # hashed


class StartingRatingTests(TestCase):
    def test_a_new_story_starts_between_800_and_2500(self):
        self.assertTrue(800 <= story('model-x').rating <= 2500)


def like(story, points, n=1):
    for i in range(n):
        Rating.objects.create(publication=story, guest=f'{story.slug}-{i}', points=points)


class RatingUseTests(TestCase):
    """The real points (Rating), not rating with its random start, decide."""

    def test_home_top_rated_of_the_last_week(self):
        liked = story('liked', rating=900)
        loved = story('loved', rating=800)
        old = story('old', hours_ago=24 * 9)
        story('random-start-only', rating=2500)
        like(liked, 30)
        like(loved, 100, n=2)
        like(old, 100)

        self.assertEqual([s['slug'] for s in APIClient().get('/home').data['top_rated']], ['loved', 'liked'])

    def test_search_sort_top(self):
        liked = story('bitcoin-liked', category='crypto', rating=800, body_md='bitcoin')
        story('bitcoin-plain', category='crypto', rating=2500, body_md='bitcoin', hours_ago=0.5)
        like(liked, 40, n=3)
        client = APIClient()

        for params in ({'q': 'bitcoin', 'sort': 'top'}, {'category': 'crypto', 'sort': 'top'}):
            self.assertEqual([s['slug'] for s in client.get('/search', params).data['results']],
                             ['bitcoin-liked', 'bitcoin-plain'], params)
        self.assertEqual([s['slug'] for s in client.get('/search', {'category': 'crypto'}).data['results']],
                         ['bitcoin-plain', 'bitcoin-liked'])  # newest without sort

    @override_settings(PUBLISHING_API_KEY='k' * 64)
    def test_reactions_for_the_pipeline(self):
        liked = story('liked', views=7)
        story('unliked', views=50)
        story('old', hours_ago=24 * 40)
        like(liked, 60, n=2)
        pipeline = APIClient(headers={'X-Api-Key': 'k' * 64})

        self.assertEqual([(r['slug'], r['points'], r['readers'], r['views'])
                          for r in pipeline.get('/publishing/reactions').data],
                         [('liked', 120, 2, 7), ('unliked', 0, 0, 50)])
        self.assertEqual(len(pipeline.get('/publishing/reactions', {'days': 60}).data), 3)
        self.assertEqual(APIClient().get('/publishing/reactions').status_code, 403)
