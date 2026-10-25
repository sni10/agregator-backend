from django.contrib.postgres.indexes import GinIndex, OpClass
from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('publications', '0004_favorite'),
    ]

    operations = [
        TrigramExtension(),
        migrations.AddIndex(
            model_name='publication',
            index=GinIndex(OpClass('title', name='gin_trgm_ops'), name='publication_title_trgm'),
        ),
    ]
