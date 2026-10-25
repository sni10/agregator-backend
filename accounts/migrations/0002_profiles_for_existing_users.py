import base64
from datetime import UTC

from django.conf import settings
from django.db import migrations
from django.utils.crypto import salted_hmac


def public_id(label, pk, link_date):
    """Frozen copy of common.public_ids.make_public_id (a test checks they agree)."""
    message = f'{label}:{pk}:{link_date.astimezone(UTC).isoformat(timespec="microseconds")}'
    digest = salted_hmac('public-id', message, algorithm='sha256').digest()
    return base64.b32encode(digest[:16]).decode().lower().rstrip('=')


def create_profiles(apps, schema_editor):
    """Existing users: a profile with link date = date joined and the public id derived from it."""
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    Profile = apps.get_model('accounts', 'Profile')
    for user in User.objects.filter(profile__isnull=True):
        profile = Profile.objects.create(user=user)
        Profile.objects.filter(pk=profile.pk).update(
            link_date=user.date_joined, public_id=public_id('accounts.profile', profile.pk, user.date_joined),
        )


class Migration(migrations.Migration):
    """The admin and anyone created before accounts existed get a profile (and a public id)."""

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_profiles, migrations.RunPython.noop),
    ]
