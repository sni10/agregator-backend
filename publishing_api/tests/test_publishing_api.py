from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from publications.models import Publication, PublicationRevision
from publishing_api.models import PublishAudit

KEY = 'k' * 64
URL = '/publishing/publications'


def payload(**changes):
    data = {
        'external_id': 'event-187',
        'category': 'crypto',
        'status': 'published',
        'title': 'Bitcoin Core ends embargoes for AI-discoverable bugs',
        'summary': 'Bitcoin Core will fix easily found flaws at once.',
        'body_md': 'Antoine Poinsot announced the change on **Thursday**.\n\nA second paragraph.',
        'sources': [{'title': 'Bitcoin Core changes security rules', 'url': 'https://www.coindesk.com/a',
                     'publisher': 'CoinDesk'}],
        'quality': {'status': 'passed', 'verified_claims': 12},
        'image_queries': ['blockchain network abstract'],
    }
    return {**data, **changes}


@override_settings(PUBLISHING_API_KEY=KEY)
class PublishingApiTests(TestCase):
    def setUp(self):
        self.client = APIClient(headers={'X-Api-Key': KEY})

    def test_creates_a_published_story_with_rendered_html_and_a_first_revision(self):
        response = self.client.post(URL, payload(), format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['revision'], 1)
        self.assertEqual(response['ETag'], '"1"')
        story = Publication.objects.get(external_id='event-187')
        self.assertEqual((story.status, story.slug), ('published', 'bitcoin-core-ends-embargoes-for-ai-discoverable-bugs'))
        self.assertIsNotNone(story.published_at)
        self.assertIn('<strong>Thursday</strong>', story.body_html)
        self.assertEqual(story.sources.get().publisher, 'CoinDesk')
        self.assertEqual(story.revisions.get().author, PublicationRevision.Author.PIPELINE)

    def test_a_repeated_post_changes_nothing(self):
        self.client.post(URL, payload(), format='json')

        response = self.client.post(URL, payload(title='Another title'), format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Publication.objects.get().title, 'Bitcoin Core ends embargoes for AI-discoverable bugs')

    def test_html_from_the_pipeline_is_stripped(self):
        self.client.post(URL, payload(body_md='Hi <script>alert(1)</script> [x](javascript:alert(1)) '
                                               '[ok](https://example.com)'), format='json')

        html = Publication.objects.get().body_html
        self.assertNotIn('<script', html)
        self.assertNotIn('javascript:', html)
        self.assertIn('href="https://example.com"', html)
        self.assertIn('rel="nofollow noopener noreferrer"', html)

    def test_a_review_story_is_not_published(self):
        self.client.post(URL, payload(status='review'), format='json')

        story = Publication.objects.get()
        self.assertEqual((story.status, story.published_at), ('review', None))

    def test_a_story_is_dated_by_its_sources(self):
        self.client.post(URL, payload(event_at='2026-10-28T09:15:00Z'), format='json')
        self.client.post(URL, payload(external_id='future', title='Future', event_at='2099-01-01T00:00:00Z'),
                         format='json')

        self.assertEqual(Publication.objects.get(external_id='event-187').published_at.isoformat(),
                         '2026-10-28T09:15:00+00:00')
        self.assertLessEqual(Publication.objects.get(external_id='future').published_at, timezone.now())

    def test_a_story_needs_a_source_and_a_known_category(self):
        response = self.client.post(URL, payload(sources=[], category='sports'), format='json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.data), {'sources', 'category'})

    def test_a_follow_up_links_to_the_earlier_story(self):
        self.client.post(URL, payload(), format='json')

        self.client.post(URL, payload(external_id='event-200', title='Follow-up', previous_external_id='event-187'),
                         format='json')
        unknown = self.client.post(URL, payload(external_id='event-201', previous_external_id='nope'), format='json')

        self.assertEqual(Publication.objects.get(external_id='event-200').previous.external_id, 'event-187')
        self.assertEqual(unknown.status_code, 400)

    def test_same_title_gets_another_slug(self):
        self.client.post(URL, payload(), format='json')
        self.client.post(URL, payload(external_id='event-188'), format='json')

        self.assertEqual(Publication.objects.get(external_id='event-188').slug,
                         'bitcoin-core-ends-embargoes-for-ai-discoverable-bugs-2')

    def test_update_needs_the_current_revision(self):
        self.client.post(URL, payload(), format='json')
        detail = f'{URL}/event-187'

        missing = self.client.put(detail, payload(title='New'), format='json')
        stale = self.client.put(detail, payload(title='New'), format='json', headers={'If-Match': '"7"'})
        updated = self.client.put(detail, payload(title='New', sources=[
            {'title': 'Other', 'url': 'https://decrypt.co/b', 'publisher': 'Decrypt'}]), format='json',
                                  headers={'If-Match': '"1"'})

        self.assertEqual((missing.status_code, stale.status_code, updated.status_code), (428, 412, 200))
        self.assertEqual(stale.data['revision'], 1)
        story = Publication.objects.get()
        self.assertEqual((story.title, story.revision, story.slug),
                         ('New', 2, 'bitcoin-core-ends-embargoes-for-ai-discoverable-bugs'))
        self.assertEqual(list(story.sources.values_list('publisher', flat=True)), ['Decrypt'])
        self.assertEqual(story.revisions.count(), 2)

    def test_a_withdrawn_story_stays_withdrawn(self):
        self.client.post(URL, payload(), format='json')
        Publication.objects.update(status=Publication.Status.WITHDRAWN)

        self.client.put(f'{URL}/event-187', payload(), format='json', headers={'If-Match': '1'})

        self.assertEqual(Publication.objects.get().status, 'withdrawn')

    def test_get_shows_the_state(self):
        self.client.post(URL, payload(), format='json')

        response = self.client.get(f'{URL}/event-187')

        self.assertEqual((response.data['status'], response.data['revision']), ('published', 1))
        self.assertEqual(self.client.get(f'{URL}/nope').status_code, 404)

    def test_every_request_is_audited(self):
        self.client.post(URL, payload(), format='json', headers={'X-Request-Id': 'run-7'})
        APIClient().post(URL, payload(), format='json')

        audits = list(PublishAudit.objects.order_by('id').values_list('action', 'external_id', 'status_code',
                                                                      'request_id'))
        self.assertEqual(audits, [('create', 'event-187', 201, 'run-7'), ('create', 'event-187', 403, '')])


class PublishingKeyTests(TestCase):
    def test_wrong_key_or_no_key_configured_is_refused(self):
        with override_settings(PUBLISHING_API_KEY=KEY):
            wrong = APIClient(headers={'X-Api-Key': 'x' * 64}).post(URL, payload(), format='json')
        with override_settings(PUBLISHING_API_KEY=''):
            off = APIClient(headers={'X-Api-Key': ''}).post(URL, payload(), format='json')

        self.assertEqual((wrong.status_code, off.status_code), (403, 403))
        self.assertFalse(Publication.objects.exists())

    def test_health(self):
        self.assertEqual(APIClient().get('/health').json(), {'status': 'ok'})
