"""Game-mode definitions and mode-selection helpers."""

from dataclasses import dataclass
import hashlib
import random
from collections.abc import Callable

from django.db.models import Max
from django.utils import timezone

from .models import FlagProgress, GameResult


CountryData = dict
CountryFilter = Callable[[list[CountryData]], list[CountryData]]


def _all_countries(countries):
    return list(countries)


def _region(name):
    def filter_by_region(countries):
        return [country for country in countries if country["region"] == name]

    return filter_by_region


def _entry_type(name):
    def filter_by_entry_type(countries):
        return [country for country in countries if country["entry_type"] == name]

    return filter_by_entry_type


@dataclass(frozen=True)
class GameMode:
    name: str
    icon: str
    description: str
    difficulty: str
    category: str
    ruleset: str
    filter_countries: CountryFilter = _all_countries
    lives: int | None = None
    round_size: int | None = None
    time_limit: int | None = None
    daily: bool = False
    multiple_choice: bool = False
    adaptive: bool = False


GAME_MODES = {
    "practice": GameMode(
        "Practice",
        "🌱",
        "Learn at your own pace with three lives and clear feedback after every answer.",
        "Beginner friendly",
        "featured",
        "lives",
        lives=3,
    ),
    "daily": GameMode(
        "Daily Challenge",
        "📅",
        "The same ten flags for everyone each day. Make your one scored attempt count!",
        "Daily",
        "featured",
        "fixed",
        round_size=10,
        daily=True,
    ),
    "speed_round": GameMode(
        "Speed Round",
        "⏱️",
        "Name as many flags as possible in 60 seconds. Wrong answers do not end the run.",
        "Fast",
        "featured",
        "timed",
        time_limit=60,
    ),
    "perfect_ten": GameMode(
        "Perfect Ten",
        "🎯",
        "Ten flags, ten chances. Finish the set and chase a perfect score.",
        "Quick",
        "featured",
        "fixed",
        round_size=10,
    ),
    "multiple_choice": GameMode(
        "Multiple Choice",
        "🧩",
        "Match ten country names to the correct flag from four visual choices.",
        "Accessible",
        "featured",
        "fixed",
        round_size=10,
        multiple_choice=True,
    ),
    "mastery_review": GameMode(
        "Mastery Review",
        "🧠",
        "Prioritizes flags you have not mastered and the ones you miss most often.",
        "Adaptive",
        "featured",
        "lives",
        lives=3,
        round_size=20,
        adaptive=True,
    ),
    "world_tour": GameMode(
        "World Tour",
        "🌍",
        "Classic sudden death across every country and territory. One mistake ends the run.",
        "Very hard",
        "featured",
        "sudden_death",
    ),
    "north_america": GameMode(
        "North America Challenge",
        "🏔️",
        "Classic sudden death using North American flags.",
        "Easy",
        "regions",
        "sudden_death",
        _region("North America"),
    ),
    "south_america": GameMode(
        "South America Challenge",
        "🦎",
        "Classic sudden death using South American flags.",
        "Easy",
        "regions",
        "sudden_death",
        _region("South America"),
    ),
    "asia": GameMode(
        "Asia Challenge",
        "🏯",
        "Classic sudden death using flags from Asia.",
        "Hard",
        "regions",
        "sudden_death",
        _region("Asia"),
    ),
    "europe": GameMode(
        "Europe Challenge",
        "🇪🇺",
        "Classic sudden death using flags from Europe.",
        "Hard",
        "regions",
        "sudden_death",
        _region("Europe"),
    ),
    "oceania": GameMode(
        "Oceania Challenge",
        "🌴",
        "Classic sudden death using flags from Oceania.",
        "Medium",
        "regions",
        "sudden_death",
        _region("Oceania"),
    ),
    "africa": GameMode(
        "Africa Challenge",
        "🦒",
        "Classic sudden death using flags from Africa.",
        "Hard",
        "regions",
        "sudden_death",
        _region("Africa"),
    ),
    "autonomous_regions": GameMode(
        "Autonomous Regions",
        "🌋",
        "A focused sudden-death collection of autonomous regions.",
        "Medium",
        "collections",
        "sudden_death",
        _entry_type("Autonomous Region"),
    ),
    "occupied_or_disputed_countries": GameMode(
        "Occupied or Disputed Countries",
        "💼",
        "A focused sudden-death collection of disputed places.",
        "Medium",
        "collections",
        "sudden_death",
        _entry_type("Occupied or Disputed Country"),
    ),
    "subnational_entities": GameMode(
        "Subnational Entities",
        "🐓",
        "States, provinces, and other subnational flags.",
        "Hard",
        "collections",
        "sudden_death",
        _entry_type("Subnational Entity"),
    ),
    "miscellaneous": GameMode(
        "Miscellaneous",
        "🤔",
        "Interesting flags from history and around the world.",
        "Easy",
        "collections",
        "sudden_death",
        _entry_type("Miscellaneous"),
    ),
}


MODE_TONES = {
    "practice": "emerald",
    "daily": "amber",
    "speed_round": "coral",
    "perfect_ten": "violet",
    "multiple_choice": "sky",
    "mastery_review": "rose",
    "world_tour": "teal",
    "north_america": "sky",
    "south_america": "emerald",
    "asia": "coral",
    "europe": "violet",
    "oceania": "teal",
    "africa": "amber",
    "autonomous_regions": "coral",
    "occupied_or_disputed_countries": "violet",
    "subnational_entities": "sky",
    "miscellaneous": "amber",
}

MODE_SECTIONS = (
    {
        "key": "featured",
        "icon": "🎲",
        "title": "Ways to Play",
        "subtitle": "Different rules, different rhythm",
        "open": True,
    },
    {
        "key": "regions",
        "icon": "🗺️",
        "title": "Regional Challenges",
        "subtitle": "Take the classic game around the world",
        "open": False,
    },
    {
        "key": "collections",
        "icon": "🏛️",
        "title": "Special Collections",
        "subtitle": "The unusual, historic, and hard to classify",
        "open": False,
    },
)


def build_mode_pool(mode_key, countries, user=None):
    mode = GAME_MODES[mode_key]
    pool = mode.filter_countries(countries)

    if mode.daily:
        seed = hashlib.sha256(timezone.localdate().isoformat().encode()).digest()
        random.Random(seed).shuffle(pool)
        return pool[: min(mode.round_size, len(pool))]

    if mode.adaptive:
        limit = min(mode.round_size, len(pool))
        if not user or not user.is_authenticated:
            return random.sample(pool, limit) if limit else []

        progress = {
            item.country.name: item
            for item in FlagProgress.objects.filter(user=user).select_related("country")
        }
        mastered = set(user.mastered_flags.values_list("name", flat=True))

        def review_priority(country):
            item = progress.get(country["name"])
            attempts = item.attempts if item else 0
            accuracy = item.correct_answers / attempts if attempts else -1
            wrong_answers = item.wrong_answers if item else 0
            return country["name"] in mastered, accuracy, -wrong_answers, country["name"]

        return sorted(pool, key=review_priority)[:limit]

    if mode.round_size and mode.ruleset == "fixed":
        size = min(mode.round_size, len(pool))
        return random.sample(pool, size) if size else []
    return pool


def _player_mode_stats(user):
    if not user.is_authenticated:
        return set(), {}, False

    mastered = set(user.mastered_flags.values_list("name", flat=True))
    best_scores = {
        row["gamemode"]: row["best"]
        for row in GameResult.objects.filter(user=user)
        .values("gamemode")
        .annotate(best=Max("score"))
    }
    completed_daily = GameResult.objects.filter(
        user=user,
        gamemode="daily",
        challenge_date=timezone.localdate(),
    ).exists()
    return mastered, best_scores, completed_daily


def _mode_card(key, mode, countries, mastered, best_scores, completed_daily):
    pool = mode.filter_countries(countries)
    score_cap = min(mode.round_size, len(pool)) if mode.round_size else None
    return {
        "key": key,
        "name": mode.name,
        "icon": mode.icon,
        "description": mode.description,
        "difficulty": mode.difficulty,
        "category": mode.category,
        "mastered": len({country["name"] for country in pool} & mastered),
        "total": len(pool),
        "best_score": best_scores.get(key),
        "score_cap": score_cap,
        "completed_today": key == "daily" and completed_daily,
        "ruleset": mode.ruleset,
        "rule_label": _rule_label(mode, len(pool)),
        "tone": MODE_TONES.get(key, "teal"),
    }


def gamemode_sections(countries, user):
    mastered, best_scores, completed_daily = _player_mode_stats(user)
    grouped = {section["key"]: [] for section in MODE_SECTIONS}
    for key, mode in GAME_MODES.items():
        grouped[mode.category].append(
            _mode_card(
                key,
                mode,
                countries,
                mastered,
                best_scores,
                completed_daily,
            )
        )
    return [
        {**section, "cards": grouped[section["key"]]} for section in MODE_SECTIONS
    ]


def _rule_label(mode, pool_size):
    if mode.ruleset == "timed":
        return f"{mode.time_limit} second sprint"
    if mode.ruleset == "lives":
        return f"{mode.lives} lives"
    if mode.ruleset == "fixed":
        return f"{min(mode.round_size, pool_size)} question set"
    return "Sudden death"
