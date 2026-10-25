from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from ...models import ContactMessage


class Command(BaseCommand):
    help = 'Delete contact messages older than CONTACT_RETENTION_DAYS (privacy policy). Run daily (cron, DEPLOY.md).'

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=settings.CONTACT_RETENTION_DAYS)
        deleted, _ = ContactMessage.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(f'Deleted contact messages: {deleted}')
