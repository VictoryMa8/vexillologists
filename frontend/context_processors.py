from .campaigns import world_cup_2026_campaign_active


def campaigns(request):
    return {
        'world_cup_2026_campaign_active': world_cup_2026_campaign_active(),
    }
