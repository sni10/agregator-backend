from datetime import timedelta
from io import BytesIO, StringIO
from unittest import mock
from urllib.parse import parse_qs

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.services.access_tokens import AccessTokenService

from ..models import ContactMessage

VALID = {'topic': 'correction', 'email': 'anna@example.com', 'pageUrl': 'https://renews.me/news/model-x',
         'message': 'The price in the second paragraph is wrong.', 'captcha': 'turnstile-token'}


@override_settings(CONTACT_EMAIL='editors@example.com', TURNSTILE_SECRET='test-secret', SITE_NAME='Renews')
class ContactApiTest(TestCase):
    headers = {}

    def setUp(self):
        cache.clear()  # throttle counters
        self.urlopen = mock.patch('urllib.request.urlopen',
                                  side_effect=lambda *a, **kw: BytesIO(b'{"success": true}')).start()
        self.addCleanup(mock.patch.stopall)

    def post(self, ip='10.0.0.1', **data):
        return self.client.post('/contact', data, content_type='application/json', HTTP_X_FORWARDED_FOR=ip,
                                HTTP_USER_AGENT='TestBrowser/1.0', **self.headers)

    def test_a_message_is_stored_and_emailed_to_the_editors(self):
        r = self.post(**VALID)

        self.assertEqual((r.status_code, r.content), (204, b''))
        c = ContactMessage.objects.get()
        self.assertEqual((c.topic, c.email, c.page_url, c.ip, c.user_agent, c.user, c.handled),
                         ('correction', 'anna@example.com', VALID['pageUrl'], '10.0.0.1', 'TestBrowser/1.0', None,
                          False))
        [m] = mail.outbox
        self.assertEqual((m.to, m.reply_to), (['editors@example.com'], ['anna@example.com']))
        self.assertEqual(m.subject, '[Renews] Error in a story: anna@example.com')
        for part in (VALID['message'], VALID['pageUrl'], '10.0.0.1', 'TestBrowser/1.0', 'guest'):
            self.assertIn(part, m.body)

    def test_captcha_is_verified_with_the_secret_token_and_ip(self):
        self.post(**VALID)

        [(url, data), kwargs] = self.urlopen.call_args
        self.assertEqual(url, 'https://challenges.cloudflare.com/turnstile/v0/siteverify')
        self.assertEqual(parse_qs(data.decode()),
                         {'secret': ['test-secret'], 'response': ['turnstile-token'], 'remoteip': ['10.0.0.1']})
        self.assertEqual(kwargs, {'timeout': 5})

    def assert_captcha_rejected(self):
        r = self.post(**VALID)
        self.assertEqual((r.status_code, r.json()), (400, {'captcha': ['The check did not pass, please try again.']}))
        self.assertFalse(ContactMessage.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_captcha_not_passed(self):
        self.urlopen.side_effect = lambda *a, **kw: BytesIO(b'{"success": false}')
        self.assert_captcha_rejected()

    def test_cloudflare_down_counts_as_not_passed(self):
        self.urlopen.side_effect = OSError('timeout')
        self.assert_captcha_rejected()

    def test_fields_are_checked(self):
        r = self.post(**{**VALID, 'email': 'nope', 'message': 'short', 'topic': 'spam', 'pageUrl': 'x'})

        self.assertEqual(r.status_code, 400)
        self.assertEqual(set(r.json()), {'email', 'message', 'topic', 'pageUrl'})
        self.urlopen.assert_not_called()  # no captcha check for an invalid form

    def test_five_an_hour_per_ip(self):
        for _ in range(5):
            self.assertEqual(self.post(**VALID).status_code, 204)
        self.assertEqual(self.post(**VALID).status_code, 429)
        self.assertEqual(self.post(ip='10.0.0.2', **VALID).status_code, 204)

    @override_settings(CONTACT_EMAIL='')
    def test_without_an_address_it_is_only_stored(self):
        self.assertEqual(self.post(**VALID).status_code, 204)
        self.assertEqual((ContactMessage.objects.count(), mail.outbox), (1, []))

    def test_a_signed_in_reader_is_linked(self):
        user = User.objects.create_user('anna@example.com', 'anna@example.com', 'x')
        self.headers = {'HTTP_AUTHORIZATION': f'Bearer {AccessTokenService().issue(user)}'}

        self.post(**VALID)

        self.assertEqual(ContactMessage.objects.get().user, user)


class PurgeTest(TestCase):
    def test_old_messages_are_deleted(self):
        old = ContactMessage.objects.create(email='a@example.com', message='x' * 10)
        ContactMessage.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=1096))
        ContactMessage.objects.create(email='b@example.com', message='y' * 10)

        call_command('purge_old_contact_messages', stdout=StringIO())

        self.assertEqual(list(ContactMessage.objects.values_list('email', flat=True)), ['b@example.com'])
