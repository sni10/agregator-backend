from django.db import migrations
from django.db.models.functions import Least


def date_by_sources(apps, schema_editor):
    """Stories were dated by when the pipeline's batch arrived: date them by their sources instead."""
    Publication = apps.get_model('publications', 'Publication')
    (Publication.objects.filter(published_at__isnull=False, event_at__isnull=False)
     .update(published_at=Least('event_at', 'published_at')))


class Migration(migrations.Migration):
    dependencies = [('publications', '0007_tags')]

    operations = [migrations.RunPython(date_by_sources, migrations.RunPython.noop)]
