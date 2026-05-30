# Generated manually 2026-05-30

import django.contrib.postgres.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('frontend', '0006_vexillologist_mastered_flags'),
    ]

    operations = [
        migrations.AddField(
            model_name='country',
            name='aliases',
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(max_length=50),
                blank=True,
                default=list,
                help_text='Common abbreviations or alternate names accepted as quiz answers (e.g. DRC, USA, UK)',
                size=None,
            ),
        ),
    ]
