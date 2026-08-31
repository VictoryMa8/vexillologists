from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils.text import slugify

from .factories import make_country, make_user


class PublicViewsTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_public_pages(self):
        for url_name in [
            "index",
            "about",
            "privacy",
            "contact",
            "release_notes",
            "login",
            "signup",
        ]:
            with self.subTest(url_name=url_name):
                self.assertEqual(self.client.get(reverse(url_name)).status_code, 200)

    def test_leaderboard_redirects_anonymous_users(self):
        self.assertEqual(self.client.get(reverse("leaderboard")).status_code, 302)


class AuthGateTest(TestCase):
    def _assert_redirects_to_login(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_private_pages_require_login(self):
        for url_name in ["leaderboard", "mastery", "settings"]:
            with self.subTest(url_name=url_name):
                self._assert_redirects_to_login(reverse(url_name))

    def test_quiz_is_public(self):
        self.assertEqual(self.client.get(reverse("quiz")).status_code, 200)

    def test_country_detail_is_public(self):
        self.assertEqual(
            self.client.get(reverse("country", args=["testland"])).status_code,
            302,
        )

    def test_search_guesses_is_public(self):
        self.assertEqual(self.client.get(reverse("search_guesses")).status_code, 200)


class CountryDetailViewTest(TestCase):
    def setUp(self):
        cache.clear()
        self.country = make_country(name="Detail Country", region="Asia")

    def test_known_country_returns_200(self):
        response = self.client.get(
            reverse("country", args=[slugify(self.country.name)])
        )
        self.assertEqual(response.status_code, 200)

    def test_unknown_country_redirects(self):
        response = self.client.get(reverse("country", args=["nonexistent-slug"]))
        self.assertEqual(response.status_code, 302)


class MasteryViewTest(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user()
        self.client.force_login(self.user)
        self.country = make_country(name="Masteria")

    def test_mastery_page_renders(self):
        self.assertEqual(self.client.get(reverse("mastery")).status_code, 200)

    def test_mastered_flag_appears_in_context(self):
        self.user.mastered_flags.add(self.country)
        response = self.client.get(reverse("mastery"))
        mastered_names = {
            entry["name"] for entry in response.context["entries"] if entry["mastered"]
        }
        self.assertIn("Masteria", mastered_names)
