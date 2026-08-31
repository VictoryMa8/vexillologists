from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_legacy_world_tour_scores(apps, schema_editor):
    User = apps.get_model('frontend', 'Vexillologist')
    GameResult = apps.get_model('frontend', 'GameResult')
    GameResult.objects.bulk_create([
        GameResult(
            user_id=user.pk,
            gamemode='world_tour',
            score=user.high_score,
            answered=user.high_score,
            correct=user.high_score,
            incorrect=0,
            outcome='completed',
        )
        for user in User.objects.filter(high_score__gt=0)
    ])


class Migration(migrations.Migration):

    dependencies = [
        ('frontend', '0008_user_email_unique_and_shared_cache'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='FlagProgress',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('correct_answers', models.PositiveIntegerField(default=0)),
                ('wrong_answers', models.PositiveIntegerField(default=0)),
                ('last_seen', models.DateTimeField(blank=True, null=True)),
                ('country', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='player_progress', to='frontend.country')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='flag_progress', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['country__name'],
            },
        ),
        migrations.CreateModel(
            name='GameResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('gamemode', models.CharField(max_length=64)),
                ('score', models.PositiveIntegerField(default=0)),
                ('answered', models.PositiveIntegerField(default=0)),
                ('correct', models.PositiveIntegerField(default=0)),
                ('incorrect', models.PositiveIntegerField(default=0)),
                ('duration_seconds', models.PositiveIntegerField(blank=True, null=True)),
                ('outcome', models.CharField(choices=[('completed', 'Completed'), ('lost', 'Lost'), ('timed_out', 'Timed out'), ('forfeit', 'Forfeit')], default='completed', max_length=16)),
                ('challenge_date', models.DateField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='game_results', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-completed_at'],
                'indexes': [models.Index(fields=['gamemode', '-score'], name='frontend_mode_score_idx')],
            },
        ),
        migrations.AddConstraint(
            model_name='flagprogress',
            constraint=models.UniqueConstraint(fields=('user', 'country'), name='frontend_flag_progress_unique'),
        ),
        migrations.AddConstraint(
            model_name='gameresult',
            constraint=models.UniqueConstraint(condition=models.Q(('challenge_date__isnull', False)), fields=('user', 'gamemode', 'challenge_date'), name='frontend_daily_result_unique'),
        ),
        migrations.RunPython(backfill_legacy_world_tour_scores, migrations.RunPython.noop),
    ]
