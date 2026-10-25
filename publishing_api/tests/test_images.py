import io
import shutil
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image as Pillow
from rest_framework.test import APIClient

from publications.models import Image, Publication

from .test_publishing_api import KEY, URL, payload

MEDIA = tempfile.mkdtemp()


def photo(width=1280, height=853, kind='JPEG') -> SimpleUploadedFile:
    buffer = io.BytesIO()
    Pillow.new('RGB', (width, height), 'teal').save(buffer, kind)
    return SimpleUploadedFile('photo.jpg', buffer.getvalue(), content_type='image/jpeg')


def meta(**changes):
    return {'external_id': 'pixabay-195893', 'source': 'pixabay', 'author': 'Josch13',
            'author_url': 'https://pixabay.com/users/josch13-48777/',
            'page_url': 'https://pixabay.com/photos/blossom-195893/', **changes}


@override_settings(PUBLISHING_API_KEY=KEY, MEDIA_ROOT=MEDIA, MEDIA_URL='https://api.site.test/media/')
class ImageUploadTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.client = APIClient(headers={'X-Api-Key': KEY})
        self.client.post(URL, payload(), format='json')
        self.image_url = f'{URL}/event-187/image'

    def upload(self, file=None, **changes):
        return self.client.put(self.image_url, {'file': file or photo(), **meta(**changes)}, format='multipart')

    def test_the_photo_is_stored_as_webp_variants_and_shown_with_its_credit(self):
        response = self.upload()

        self.assertEqual((response.status_code, response.data['image'], response.data['revision']),
                         (200, 'pixabay-195893', 1))  # the text is unchanged: no new revision
        for width in (1200, 600, 320):
            with Pillow.open(Path(MEDIA) / f'images/pixabay-195893-{width}.webp') as variant:
                self.assertEqual((variant.format, variant.size), ('WEBP', (width, width * 9 // 16)))

        story = APIClient().get('/publications').data['results'][0]
        self.assertEqual(story['image']['src'], 'https://api.site.test/media/images/pixabay-195893-1200.webp')
        self.assertTrue(story['image']['srcset'].startswith(
            'https://api.site.test/media/images/pixabay-195893-320.webp 320w, '))
        self.assertEqual((story['image']['author'], story['image']['source']), ('Josch13', 'Pixabay'))

    def test_the_same_photo_is_converted_once(self):
        self.upload()
        self.client.post(URL, payload(external_id='event-188'), format='json')

        self.client.put(f'{URL}/event-188/image', {'file': photo(), **meta()}, format='multipart')

        self.assertEqual(Image.objects.count(), 1)
        self.assertEqual(Publication.objects.filter(image__isnull=False).count(), 2)

    def test_not_an_image_or_too_small_is_refused(self):
        fake = SimpleUploadedFile('photo.jpg', b'<?php echo 1; ?>', content_type='image/jpeg')

        broken = self.upload(file=fake)
        small = self.upload(file=photo(400, 300), external_id='pixabay-1')
        bad_link = self.upload(page_url='javascript:alert(1)', external_id='pixabay-2')

        self.assertEqual((broken.status_code, small.status_code, bad_link.status_code), (400, 400, 400))
        self.assertFalse(Image.objects.exists())
        self.assertIsNone(Publication.objects.get().image)

    def test_a_story_without_a_photo_has_no_image(self):
        self.assertIsNone(APIClient().get('/publications').data['results'][0]['image'])

    def test_unknown_story_and_wrong_key(self):
        missing = self.client.put(f'{URL}/nope/image', {'file': photo(), **meta()}, format='multipart')
        refused = APIClient().put(self.image_url, {'file': photo(), **meta()}, format='multipart')

        self.assertEqual((missing.status_code, refused.status_code), (404, 403))
