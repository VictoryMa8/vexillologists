from django.db import models, transaction
from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.fields import ArrayField
from django.db.models import Q
from django.db.models.functions import Lower
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache

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
    flag_image_url = models.URLField(max_length=500, null=True, blank=True, help_text="Link to Wikimedia image of flag")
    capital = models.CharField(max_length=100, null=True, blank=True)
    population = models.BigIntegerField(null=True, blank=True)
    area_km2 = models.IntegerField(null=True, blank=True, help_text="Area in square kilometers")
    official_language = models.CharField(max_length=100, null=True, blank=True)
    region = models.CharField(max_length=100, null=True, blank=True)
    entry_type = models.CharField(max_length=100, default="Country", help_text="e.g. Country, Autonomous Region, Territory")
    fact = models.TextField(null=True, blank=True, help_text="An interesting fact about this place")
    aliases = ArrayField(
        models.CharField(max_length=50),
        blank=True,
        default=list,
        help_text="Common abbreviations or alternate names accepted as quiz answers (e.g. DRC, USA, UK)",
    )

    def __str__(self):
        return self.name

"""
Django signals are a publish/subscribe system built into the ORM

Whenever a Country record is saved or deleted (e.g. via the admin panel), Django fires the post_save / post_delete signal and calls this function

We use it to immediately clear the cached country list so the next call to get_countries() re-queries the database and picks up the change

Without this, an admin edit would be invisible until the 1-hour TTL expires
"""
@receiver(post_save, sender=Country)
@receiver(post_delete, sender=Country)
def invalidate_countries_cache(sender, **kwargs):
    # Delete after the write commits so another worker cannot refill the cache
    # with pre-commit data in the gap between the signal and the commit.
    transaction.on_commit(lambda: cache.delete('countries:v2'))
