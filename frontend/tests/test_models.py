from django.db import IntegrityError, transaction
from django.test import TestCase

from frontend.models import Country

from .factories import make_country, make_user


class CountryModelTest(TestCase):
    def test_str_returns_name(self):
        country = make_country(name="Flagtopia")
        self.assertEqual(str(country), "Flagtopia")

    def test_name_is_unique(self):
        make_country(name="Uniqueland")
        with self.assertRaises(IntegrityError):
            make_country(name="Uniqueland")

    def test_optional_fields_can_be_null(self):
        country = Country.objects.create(name="Minimalia")
        self.assertIsNone(country.capital)
        self.assertIsNone(country.population)


class VexillologistModelTest(TestCase):
    def test_str_returns_username(self):
        self.assertEqual(str(make_user(username="flagfan")), "flagfan")

    def test_defaults(self):
        user = make_user()
        self.assertEqual(user.high_score, 0)
        self.assertEqual(user.games_played, 0)
        self.assertEqual(user.mastered_flags.count(), 0)

    def test_mastered_flags_many_to_many(self):
        user = make_user()
        country = make_country(name="Masteria")
        user.mastered_flags.add(country)
        self.assertIn(country, user.mastered_flags.all())

    def test_email_is_unique_case_insensitively_in_database(self):
        make_user(email="owner@example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_user(username="second-user", email="OWNER@example.com")
