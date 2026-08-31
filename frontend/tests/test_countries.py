from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from frontend.countries import (
    COUNTRIES_CACHE_KEY,
    filter_countries,
    get_countries,
)

from .factories import make_country


class CountriesCacheTest(TestCase):
    def setUp(self):
        cache.clear()

    def test_cache_populated_after_get_countries(self):
        make_country(name="Cacheland")
        get_countries()
        self.assertIsNotNone(cache.get(COUNTRIES_CACHE_KEY))

    def test_save_signal_invalidates_cache(self):
        country = make_country(name="Signalia")
        get_countries()

        country.name = "Signalia Renamed"
        with self.captureOnCommitCallbacks(execute=True):
            country.save()

        self.assertIsNone(cache.get(COUNTRIES_CACHE_KEY))

    def test_delete_signal_invalidates_cache(self):
        country = make_country(name="Deletia")
        get_countries()
        with self.captureOnCommitCallbacks(execute=True):
            country.delete()
        self.assertIsNone(cache.get(COUNTRIES_CACHE_KEY))


class FilterCountriesTest(SimpleTestCase):
    SAMPLE = [
        {
            "name": "Argentina",
            "region": "South America",
            "entry_type": "Country",
            "area_km2": 2_780_400,
            "population_2024": 46_000_000,
        },
        {
            "name": "Australia",
            "region": "Oceania",
            "entry_type": "Country",
            "area_km2": 7_692_024,
            "population_2024": 26_000_000,
        },
        {
            "name": "Austria",
            "region": "Europe",
            "entry_type": "Country",
            "area_km2": 83_871,
            "population_2024": 9_000_000,
        },
        {
            "name": "Gibraltar",
            "region": "Europe",
            "entry_type": "Territory",
            "area_km2": 6,
            "population_2024": 34_000,
        },
    ]

    def test_query_prefix_match(self):
        result = filter_countries(self.SAMPLE, query="Ar")
        self.assertEqual([country["name"] for country in result], ["Argentina"])

    def test_query_case_insensitive(self):
        result = filter_countries(self.SAMPLE, query="AU")
        self.assertEqual(
            [country["name"] for country in result],
            ["Australia", "Austria"],
        )

    def test_continent_filter(self):
        result = filter_countries(self.SAMPLE, continent="Europe")
        self.assertEqual(len(result), 2)
        self.assertTrue(all(country["region"] == "Europe" for country in result))

    def test_entry_type_filter(self):
        result = filter_countries(self.SAMPLE, entry_type="Territory")
        self.assertEqual([country["name"] for country in result], ["Gibraltar"])

    def test_min_area_filter(self):
        result = filter_countries(self.SAMPLE, min_area=1_000_000)
        self.assertEqual(
            [country["name"] for country in result],
            ["Argentina", "Australia"],
        )

    def test_min_population_filter(self):
        result = filter_countries(self.SAMPLE, min_population=20_000_000)
        self.assertEqual(
            [country["name"] for country in result],
            ["Argentina", "Australia"],
        )

    def test_empty_query_returns_all(self):
        self.assertEqual(filter_countries(self.SAMPLE), self.SAMPLE)

    def test_combined_filters(self):
        result = filter_countries(
            self.SAMPLE,
            continent="Europe",
            entry_type="Territory",
        )
        self.assertEqual([country["name"] for country in result], ["Gibraltar"])
