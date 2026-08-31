from django.contrib.auth.models import AbstractUser
from django.core.cache import cache
from django.contrib.postgres.fields import ArrayField
from django.db import models, transaction
from django.db.models import Q
from django.db.models.functions import Lower
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .cache_keys import COUNTRIES


class Vexillologist(AbstractUser):
    high_score = models.IntegerField(default=0)
    games_played = models.IntegerField(default=0)
    mastered_flags = models.ManyToManyField(
        'Country',
        blank=True,
        related_name='mastered_by',
    )

    def __str__(self):
        return self.username

    class Meta:
        verbose_name = 'user'
        verbose_name_plural = 'users'
        constraints = [
            models.UniqueConstraint(
                Lower('email'),
                condition=~Q(email=''),
                name='frontend_user_email_ci_unique',
            ),
        ]


class Country(models.Model):
    name = models.CharField(max_length=100, unique=True)
    flag_emoji = models.CharField(max_length=10, null=True, blank=True)
    flag_image_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        help_text="Link to Wikimedia image of flag",
    )
    capital = models.CharField(max_length=100, null=True, blank=True)
    population = models.BigIntegerField(null=True, blank=True)
    area_km2 = models.IntegerField(
        null=True,
        blank=True,
        help_text="Area in square kilometers",
    )
    official_language = models.CharField(max_length=100, null=True, blank=True)
    region = models.CharField(max_length=100, null=True, blank=True)
    entry_type = models.CharField(
        max_length=100,
        default="Country",
        help_text="e.g. Country, Autonomous Region, Territory",
    )
    fact = models.TextField(
        null=True,
        blank=True,
        help_text="An interesting fact about this place",
    )
    aliases = ArrayField(
        models.CharField(max_length=50),
        blank=True,
        default=list,
        help_text=(
            "Common abbreviations or alternate names accepted as quiz answers "
            "(e.g. DRC, USA, UK)"
        ),
    )

    def __str__(self):
        return self.name


class FlagProgress(models.Model):
    """Per-player recall history used by mastery and adaptive practice."""

    user = models.ForeignKey(
        Vexillologist,
        on_delete=models.CASCADE,
        related_name='flag_progress',
    )
    country = models.ForeignKey(
        Country,
        on_delete=models.CASCADE,
        related_name='player_progress',
    )
    attempts = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    wrong_answers = models.PositiveIntegerField(default=0)
    last_seen = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'country'],
                name='frontend_flag_progress_unique',
            ),
        ]
        ordering = ['country__name']

    def __str__(self):
        return f'{self.user} · {self.country}'


class GameResult(models.Model):
    """A completed quiz run, retained for fair per-mode leaderboards."""

    OUTCOME_CHOICES = [
        ('completed', 'Completed'),
        ('lost', 'Lost'),
        ('timed_out', 'Timed out'),
        ('forfeit', 'Forfeit'),
    ]

    user = models.ForeignKey(
        Vexillologist,
        on_delete=models.CASCADE,
        related_name='game_results',
    )
    gamemode = models.CharField(max_length=64)
    score = models.PositiveIntegerField(default=0)
    answered = models.PositiveIntegerField(default=0)
    correct = models.PositiveIntegerField(default=0)
    incorrect = models.PositiveIntegerField(default=0)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    outcome = models.CharField(max_length=16, choices=OUTCOME_CHOICES, default='completed')
    challenge_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'gamemode', 'challenge_date'],
                condition=Q(challenge_date__isnull=False),
                name='frontend_daily_result_unique',
            ),
        ]
        indexes = [
            models.Index(fields=['gamemode', '-score'], name='frontend_mode_score_idx'),
        ]
        ordering = ['-completed_at']

    def __str__(self):
        return f'{self.user} · {self.gamemode} · {self.score}'


@receiver(post_save, sender=Country)
@receiver(post_delete, sender=Country)
def invalidate_countries_cache(sender, **kwargs):
    """Expose country edits only after their database transaction commits."""
    transaction.on_commit(lambda: cache.delete(COUNTRIES))
