from django.contrib.auth.models import User

from ..models import NotificationSettings
from .test_auth_api import ApiTestCase
from .test_registration import STRONG


class NotificationSettingsApiTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('anna@example.com', 'anna@example.com', STRONG)
        access = self.post('/auth/login', email='anna@example.com', password=STRONG).json()['access']
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {access}'}

    def patch(self, **data):
        return self.client.patch('/me/notifications', data, content_type='application/json', **self.auth)

    def test_all_off_at_first_and_private(self):
        r = self.client.get('/me/notifications', **self.auth)

        self.assertEqual(r.json(), {'emailDigest': False, 'push': False})
        self.assertIn('no-store', r['Cache-Control'])
        self.assertIn('private', r['Cache-Control'])

    def test_only_the_sent_fields_change(self):
        self.assertEqual(self.patch(emailDigest=True).json(), {'emailDigest': True, 'push': False})
        self.assertEqual(self.patch(push=True).json(), {'emailDigest': True, 'push': True})
        self.assertEqual(self.patch(emailDigest=False).json(), {'emailDigest': False, 'push': True})

        s = NotificationSettings.objects.get(user=self.user)
        self.assertEqual((s.email_digest, s.push), (False, True))

    def test_bad_value_and_no_token(self):
        self.assertEqual(self.patch(push='maybe').status_code, 400)
        self.assertEqual(self.client.get('/me/notifications').status_code, 401)
        self.assertEqual(self.client.patch('/me/notifications', {'push': True}, content_type='application/json')
                         .status_code, 401)

    def test_deleted_with_the_user(self):
        self.patch(push=True)
        self.user.delete()
        self.assertFalse(NotificationSettings.objects.exists())
