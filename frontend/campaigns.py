from datetime import date

from django.utils import timezone


WORLD_CUP_2026_CAMPAIGN_END = date(2026, 7, 19)


def world_cup_2026_campaign_active():
    """Keep temporary promotion out of templates after the tournament ends."""
    return timezone.localdate() <= WORLD_CUP_2026_CAMPAIGN_END
