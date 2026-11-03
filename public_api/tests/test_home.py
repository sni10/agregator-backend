from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from publications import services
from publications.models import LeadPick, Publication, TopStory

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

        self.assertEqual(slugs(home['lead']), ['ai-5', 'ai-1', 'ai-2', 'ai-3', 'ai-4', 'ai-6'])
        self.assertEqual(slugs(home['latest']), ['ai-7', 'ai-8', 'ai-9', 'ai-10', 'ai-11', 'it-1'])
        self.assertEqual([(s['category']['slug'], slugs(s['stories'])) for s in home['sections']],
                         [('it', ['it-2', 'it-3'])])  # crypto has none: no block
        self.assertEqual(home['most_read'], [])
        self.assertIn('max-age=60', self.client.get('/home')['Cache-Control'])

    def test_most_read_of_the_last_days(self):
        story('popular', views=40)
        story('read', views=3)
        story('old', views=900, hours_ago=24 * 5)
        story('unread')

        self.assertEqual(slugs(self.client.get('/home').data['most_read']), ['popular', 'read'])

    def test_empty_site(self):
        self.assertEqual(self.client.get('/home').data,
                         {'lead': [], 'latest': [], 'sections': [], 'most_read': [], 'top_rated': []})

    def test_cards_name_the_publishers_once_each(self):
        add_sources(story('a'), 'Decrypt', 'Example', 'The Block')

        card = self.client.get('/publications').data['results'][0]

        self.assertEqual(card['publishers'], ['Example', 'Decrypt', 'The Block'])
        self.assertEqual(card['source_count'], 4)


def days(n):
    return timezone.now() + timedelta(days=n)


class PlacementTests(TestCase):
    """The editors' top story and the stories beside it, each for a week unless the dates say otherwise."""

    def setUp(self):
        for hour in range(1, 15):
            story(f's-{hour}', hours_ago=hour)
        add_sources(Publication.objects.get(slug='s-9'), 'Decrypt', 'The Block')  # the top story on its own

    def lead(self):
        return slugs(APIClient().get('/home').data['lead'])

    def place(self, model, slug, **fields):
        return model.objects.create(publication=Publication.objects.get(slug=slug), **fields)

    def test_without_editors_the_most_sourced_leads_and_the_newest_stand_beside(self):
        self.assertEqual(self.lead(), ['s-9', 's-1', 's-2', 's-3', 's-4', 's-5'])

    def test_the_editors_top_story_leads_for_a_week(self):
        top = self.place(TopStory, 's-12')
        self.assertEqual(top.ends_at, top.starts_at + timedelta(days=7))
        self.assertEqual(self.lead(), ['s-12', 's-1', 's-2', 's-3', 's-4', 's-5'])

        top.starts_at, top.ends_at = days(-8), days(-1)
        top.save()
        self.assertEqual(self.lead()[0], 's-9')

    def test_a_top_story_can_be_set_ahead_and_the_last_started_wins(self):
        self.place(TopStory, 's-12', starts_at=days(-2))
        self.place(TopStory, 's-13', starts_at=days(-1))
        self.place(TopStory, 's-14', starts_at=days(1))  # scheduled
        self.assertEqual(self.lead()[0], 's-13')

    def test_a_story_not_published_is_skipped(self):
        self.place(TopStory, 's-12')
        Publication.objects.filter(slug='s-12').update(status=Publication.Status.WITHDRAWN)
        self.assertEqual(self.lead()[0], 's-9')

    def test_picks_stand_at_their_places_and_the_free_ones_get_the_newest(self):
        self.place(LeadPick, 's-13', position=2)
        self.place(LeadPick, 's-12', position=1)
        self.place(LeadPick, 's-9', position=3)  # the top story: shown once, as the top
        self.place(LeadPick, 's-14', position=4, starts_at=days(-9))  # ended
        self.place(LeadPick, 's-11', position=5, starts_at=days(1))  # scheduled

        home = APIClient().get('/home').data

        self.assertEqual(slugs(home['lead']), ['s-9', 's-12', 's-13', 's-1', 's-2', 's-3'])
        self.assertNotIn('s-12', slugs(home['latest']))

    def test_dates_out_of_order_are_refused(self):
        top = TopStory(publication=Publication.objects.get(slug='s-1'), starts_at=days(1), ends_at=days(0))
        with self.assertRaises(ValidationError):
            top.full_clean()


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
