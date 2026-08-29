from django.db import migrations, models
from django.db.models import Q
from django.db.models.functions import Lower


class Migration(migrations.Migration):

    dependencies = [
        ('frontend', '0007_country_aliases'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='vexillologist',
            constraint=models.UniqueConstraint(
                Lower('email'),
                condition=~Q(email=''),
                name='frontend_user_email_ci_unique',
            ),
        ),
        migrations.RunSQL(
            sql='''
                CREATE TABLE IF NOT EXISTS django_cache (
                    cache_key varchar(255) PRIMARY KEY,
                    value text NOT NULL,
                    expires timestamp with time zone NOT NULL
                );
                CREATE INDEX IF NOT EXISTS django_cache_expires
                    ON django_cache (expires);
            ''',
            reverse_sql='''
                DROP TABLE IF EXISTS django_cache;
            ''',
        ),
    ]
