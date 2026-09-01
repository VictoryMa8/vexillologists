"""Country queries, serialization, filtering, and caching."""

from django.core.cache import cache
from django.templatetags.static import static

from .cache_keys import COUNTRIES as COUNTRIES_CACHE_KEY
from .models import Country


COUNTRIES_CACHE_TTL = 60 * 60

# These detailed flags are bundled locally because Wikimedia file moves and
# hotlink failures otherwise leave holes in the explorer and quiz.
LOCAL_FLAG_ASSETS = {
    "Metis": "assets/images/flags/metis.svg",
    "Métis": "assets/images/flags/metis.svg",
    "Navajo": "assets/images/flags/navajo.svg",
    "Oromia": "assets/images/flags/oromia.svg",
    "Pashtun": "assets/images/flags/pashtun.svg",
    "Rohingya": "assets/images/flags/rohingya.svg",
    "Sami": "assets/images/flags/sami.svg",
    "Sámi": "assets/images/flags/sami.svg",
    "Zanzibar": "assets/images/flags/zanzibar.svg",
}


def flag_image_url(country):
    local_asset = LOCAL_FLAG_ASSETS.get(country.name)
    return static(local_asset) if local_asset else country.flag_image_url


def get_countries():
    countries = cache.get(COUNTRIES_CACHE_KEY)
    if countries is not None:
        return countries

    countries = [
        {
            "name": country.name,
            "flag_emoji": country.flag_emoji,
            "flag_image_url": flag_image_url(country),
            "capital": country.capital,
            "population_2024": country.population,
            "area_km2": country.area_km2,
            "official_language": country.official_language,
            "region": country.region,
            "entry_type": country.entry_type,
            "fact": country.fact,
            "aliases": country.aliases,
        }
        for country in Country.objects.order_by("name")
    ]
    cache.set(COUNTRIES_CACHE_KEY, countries, COUNTRIES_CACHE_TTL)
    return countries


def filter_countries(
    countries,
    query="",
    continent="",
    min_area=None,
    min_population=None,
    entry_type="",
):
    query = (query or "").strip().casefold()
    continent = (continent or "").strip()
    entry_type = (entry_type or "").strip()

    result = list(countries)
    if query:
        result = [
            country
            for country in result
            if any(
                (name or "").casefold().startswith(query)
                for name in [country["name"], *(country.get("aliases") or [])]
            )
        ]
    if continent:
        result = [country for country in result if country.get("region") == continent]
    if entry_type:
        result = [
            country for country in result if country.get("entry_type") == entry_type
        ]
    if min_area is not None:
        result = [
            country for country in result if (country.get("area_km2") or 0) >= min_area
        ]
    if min_population is not None:
        result = [
            country
            for country in result
            if (country.get("population_2024") or 0) >= min_population
        ]
    return result


def filter_choices(countries, field):
    return sorted({value.strip() for country in countries if (value := country.get(field))})
