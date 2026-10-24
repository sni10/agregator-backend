from django.db import migrations

CATEGORIES = [('it', 'IT'), ('ai', 'AI'), ('crypto', 'Crypto')]  # the pipeline's categories


def create(apps, schema_editor):
    Category = apps.get_model('publications', 'Category')
    for position, (slug, name) in enumerate(CATEGORIES):
        Category.objects.get_or_create(slug=slug, defaults={'name': name, 'position': position})


class Migration(migrations.Migration):
    dependencies = [('publications', '0001_initial')]

    operations = [migrations.RunPython(create, migrations.RunPython.noop)]
