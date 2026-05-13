"""
Predeploy test suite for vexillologists.com.

Run with: python manage.py test frontend

These tests are intentionally broad — they cover the most important paths
that would break the site for all users if deployed broken:

  - Model integrity and signals
  - Core utility functions (caching, filtering)
  - HTTP status codes for every URL
  - Auth gate (login required on protected views)
  - Game logic (correct/incorrect guesses, streak, win condition)
  - Form validation (login, username uniqueness, profile update)
  
"""

from django.test import TestCase, Client
from django.core.cache import cache
from django.urls import reverse

from .models import Country, Vexillologist
from .forms import LoginForm, UsernameChangeForm
from .views import filter_countries, COUNTRIES_CACHE_KEY


# ---------------------------------------------------------------------------
# Helpers


def make_user(username="testuser", email="test@example.com", password="pass1234!"):
    """Create and return a Vexillologist with a confirmed password."""
    user = Vexillologist.objects.create_user(
        username=username,
        email=email,
        password=password,
    )
    return user


def make_country(**kwargs):
    """
    Create a Country with sensible defaults so tests only have to specify
    the fields they actually care about.
    """
    defaults = dict(
        name="Testland",
        flag_emoji="🏳",
        flag_image_url="https://example.com/flag.png",
        capital="Testville",
        population=1_000_000,
        area_km2=50_000,
        official_language="Testish",
        region="Europe",
        entry_type="Country",
        fact="A fun fact.",
    )
    defaults.update(kwargs)
    return Country.objects.create(**defaults)



# Model Tests
class CountryModelTest(TestCase):
    def test_str_returns_name(self):
        """Country.__str__ is used in admin dropdowns — must return the name."""
        c = make_country(name="Flagtopia")
        self.assertEqual(str(c), "Flagtopia")

    def test_name_is_unique(self):
        """Duplicate country names must be rejected at the DB level."""
        from django.db import IntegrityError
        make_country(name="Uniqueland")
        with self.assertRaises(IntegrityError):
            make_country(name="Uniqueland")

    def test_optional_fields_can_be_null(self):
        """All nullable fields should save without error when omitted."""
        c = Country.objects.create(name="Minimalia")
        self.assertIsNone(c.capital)
        self.assertIsNone(c.population)


class VexillologistModelTest(TestCase):
    def test_str_returns_username(self):
        """Vexillologist.__str__ is displayed on the leaderboard."""
        user = make_user(username="flagfan")
        self.assertEqual(str(user), "flagfan")

    def test_defaults(self):
        """New users start with zero stats — anything else would corrupt the leaderboard."""
        user = make_user()
        self.assertEqual(user.high_score, 0)
        self.assertEqual(user.games_played, 0)
        self.assertEqual(user.mastered_flags.count(), 0)

    def test_mastered_flags_many_to_many(self):
        """mastered_flags.add() should work and be queryable."""
        user = make_user()
        country = make_country(name="Masteria")
        user.mastered_flags.add(country)
        self.assertIn(country, user.mastered_flags.all())


# Cache / Signal Tests
class CountriesCacheTest(TestCase):
    """
    The in-memory cache is the primary performance lever.
    If signals stop firing or the cache key drifts, admins editing countries
    in production would see stale data for up to an hour.
    """

    def setUp(self):
        # Always start with a cold cache so tests are independent.
        cache.clear()

    def test_cache_populated_after_get_countries(self):
        """get_countries() should warm the cache on first call."""
        from .views import get_countries
        make_country(name="Cacheland")
        get_countries()
        self.assertIsNotNone(cache.get(COUNTRIES_CACHE_KEY))

    def test_save_signal_invalidates_cache(self):
        """Saving a Country must clear the cache so the next request picks up the change."""
        from .views import get_countries
        c = make_country(name="Signalia")
        get_countries()  # prime the cache
        self.assertIsNotNone(cache.get(COUNTRIES_CACHE_KEY))

        c.name = "Signalia Renamed"
        c.save()  # post_save signal fires here

        self.assertIsNone(cache.get(COUNTRIES_CACHE_KEY))

    def test_delete_signal_invalidates_cache(self):
        """Deleting a Country must also clear the cache."""
        from .views import get_countries
        c = make_country(name="Deletia")
        get_countries()
        c.delete()  # post_delete signal fires here
        self.assertIsNone(cache.get(COUNTRIES_CACHE_KEY))


# filter_countries() Unit Tests
class FilterCountriesTest(TestCase):
    """
    filter_countries() powers both the explorer page and HTMX search.
    These tests run against in-memory dicts, no DB needed.
    """

    SAMPLE = [
        {"name": "Argentina",  "region": "South America", "entry_type": "Country",   "area_km2": 2_780_400, "population_2024": 46_000_000},
        {"name": "Australia",  "region": "Oceania",       "entry_type": "Country",   "area_km2": 7_692_024, "population_2024": 26_000_000},
        {"name": "Austria",    "region": "Europe",        "entry_type": "Country",   "area_km2": 83_871,    "population_2024": 9_000_000},
        {"name": "Gibraltar",  "region": "Europe",        "entry_type": "Territory", "area_km2": 6,         "population_2024": 34_000},
    ]

    def test_query_prefix_match(self):
        """Name filter uses startswith — 'Ar' should return Argentina only."""
        result = filter_countries(self.SAMPLE, query="Ar")
        self.assertEqual([c["name"] for c in result], ["Argentina"])

    def test_query_case_insensitive(self):
        """Searches from the explorer are case-insensitive."""
        result = filter_countries(self.SAMPLE, query="AU")
        names = [c["name"] for c in result]
        self.assertIn("Australia", names)
        self.assertIn("Austria", names)

    def test_continent_filter(self):
        result = filter_countries(self.SAMPLE, continent="Europe")
        self.assertTrue(all(c["region"] == "Europe" for c in result))
        self.assertEqual(len(result), 2)

    def test_entry_type_filter(self):
        result = filter_countries(self.SAMPLE, entry_type="Territory")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Gibraltar")

    def test_min_area_filter(self):
        """Only countries with area >= threshold should be returned."""
        result = filter_countries(self.SAMPLE, min_area=1_000_000)
        names = [c["name"] for c in result]
        self.assertIn("Argentina", names)
        self.assertIn("Australia", names)
        self.assertNotIn("Austria", names)
        self.assertNotIn("Gibraltar", names)

    def test_min_population_filter(self):
        result = filter_countries(self.SAMPLE, min_population=20_000_000)
        names = [c["name"] for c in result]
        self.assertIn("Argentina", names)
        self.assertIn("Australia", names)
        self.assertNotIn("Austria", names)

    def test_empty_query_returns_all(self):
        """Passing no filters should return every entry unchanged."""
        result = filter_countries(self.SAMPLE)
        self.assertEqual(len(result), len(self.SAMPLE))

    def test_combined_filters(self):
        """Filters compose correctly — Europe + Territory should yield only Gibraltar."""
        result = filter_countries(self.SAMPLE, continent="Europe", entry_type="Territory")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Gibraltar")


# Public URL Smoke Tests
class PublicViewsTest(TestCase):
    """
    Every public page must return 200.  A 500 on the index at deploy time
    means the site is completely down.
    """

    def setUp(self):
        self.client = Client()

    def test_index_page(self):
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)

    def test_leaderboard_page(self):
        response = self.client.get(reverse("leaderboard"))
        self.assertEqual(response.status_code, 200)

    def test_about_page(self):
        response = self.client.get(reverse("about"))
        self.assertEqual(response.status_code, 200)

    def test_privacy_page(self):
        response = self.client.get(reverse("privacy"))
        self.assertEqual(response.status_code, 200)

    def test_contact_page(self):
        response = self.client.get(reverse("contact"))
        self.assertEqual(response.status_code, 200)

    def test_release_notes_page(self):
        response = self.client.get(reverse("release_notes"))
        self.assertEqual(response.status_code, 200)

    def test_login_page(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)

    def test_signup_page(self):
        response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 200)


# Auth Gate Tests
class AuthGateTest(TestCase):
    """
    @login_required views must redirect anonymous visitors to the login page.
    If this breaks, private data becomes publicly accessible.
    """

    def setUp(self):
        self.client = Client()

    def _assert_redirects_to_login(self, url):
        response = self.client.get(url)
        # Django redirects to /accounts/login/?next=<url> by default
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_quiz_requires_login(self):
        self._assert_redirects_to_login(reverse("quiz"))

    def test_mastery_requires_login(self):
        self._assert_redirects_to_login(reverse("mastery"))

    def test_settings_requires_login(self):
        self._assert_redirects_to_login(reverse("settings"))

    def test_country_detail_requires_login(self):
        # country() takes a slug — any slug triggers the auth gate
        self._assert_redirects_to_login(reverse("country", args=["testland"]))

    def test_search_guesses_requires_login(self):
        self._assert_redirects_to_login(reverse("search_guesses"))


# Login Form Tests
class LoginFormTest(TestCase):
    """LoginForm does credential checking in clean(), must reject bad creds."""

    def setUp(self):
        self.user = make_user(email="login@example.com", password="correct_pass!")

    def test_valid_credentials(self):
        form = LoginForm(data={"email": "login@example.com", "password": "correct_pass!"})
        self.assertTrue(form.is_valid())
        # The form attaches the authenticated user object so the view can call auth_login()
        self.assertEqual(form.user, self.user)

    def test_wrong_password(self):
        form = LoginForm(data={"email": "login@example.com", "password": "wrong_pass!"})
        self.assertFalse(form.is_valid())

    def test_nonexistent_email(self):
        form = LoginForm(data={"email": "nobody@example.com", "password": "any_pass!"})
        self.assertFalse(form.is_valid())

    def test_case_insensitive_email(self):
        """Email lookup uses iexact — LOGIN@EXAMPLE.COM must work."""
        form = LoginForm(data={"email": "LOGIN@EXAMPLE.COM", "password": "correct_pass!"})
        self.assertTrue(form.is_valid())

    def test_empty_fields_invalid(self):
        form = LoginForm(data={"email": "", "password": ""})
        self.assertFalse(form.is_valid())


# Username Uniqueness Form Tests
class UsernameChangeFormTest(TestCase):
    def setUp(self):
        self.user = make_user(username="original")
        self.other = make_user(username="taken", email="other@example.com")

    def test_taken_username_rejected(self):
        """Attempting to claim another user's handle must fail validation."""
        form = UsernameChangeForm(data={"username": "taken"}, instance=self.user)
        self.assertFalse(form.is_valid())

    def test_own_username_allowed(self):
        """Saving the same username back (no change) must pass validation."""
        form = UsernameChangeForm(data={"username": "original"}, instance=self.user)
        self.assertTrue(form.is_valid())

    def test_new_unique_username_allowed(self):
        form = UsernameChangeForm(data={"username": "brandnew"}, instance=self.user)
        self.assertTrue(form.is_valid())

    def test_case_insensitive_uniqueness(self):
        """Username check uses iexact — 'TAKEN' should conflict with 'taken'."""
        form = UsernameChangeForm(data={"username": "TAKEN"}, instance=self.user)
        self.assertFalse(form.is_valid())


# Quiz Game Logic Tests
class QuizTest(TestCase):
    """
    These tests exercise the POST handler in quiz(), the core game loop.
    We set session state directly (the same keys the view reads/writes) so
    we don't have to go through the gamemode picker screen.
    """

    def setUp(self):
        cache.clear()
        self.user = make_user()
        self.client = Client()
        self.client.force_login(self.user)

        # Create enough countries for multi-country scenarios
        self.country_a = make_country(name="Alpha", region="Europe", flag_image_url="https://example.com/a.png")
        self.country_b = make_country(name="Beta",  region="Europe", flag_image_url="https://example.com/b.png")

    def _set_session(self, extra=None):
        """
        Seed session state so the POST handler sees a game already in progress.
        This mirrors exactly what the GET handler writes before a player guesses.
        """
        session = self.client.session
        session["quiz_gamemode"] = "world_tour"
        session["quiz_pool_size"] = 2
        session["quiz_country"] = {
            "name": self.country_a.name,
            "flag_image_url": self.country_a.flag_image_url,
            "flag_emoji": self.country_a.flag_emoji,
            "region": self.country_a.region,
            "entry_type": self.country_a.entry_type,
        }
        session["quiz_streak"] = 0
        session["quiz_collected_flags"] = []
        session["quiz_collected_names"] = []
        if extra:
            session.update(extra)
        session.save()

    def test_correct_guess_increments_streak(self):
        """A right answer must increase the streak by exactly 1."""
        self._set_session()
        self.client.post(reverse("quiz"), {"guess": "Alpha"})

        # After POST the session is updated — read it back
        session = self.client.session
        self.assertEqual(session["quiz_streak"], 1)

    def test_wrong_guess_ends_game(self):
        """A wrong answer must set game_over in the flash result stored in the session."""
        self._set_session()
        self.client.post(reverse("quiz"), {"guess": "WRONG"})

        session = self.client.session
        result = session.get("quiz_result", {})
        self.assertTrue(result.get("game_over"))
        # Streak resets to 0 after a loss
        self.assertEqual(session["quiz_streak"], 0)

    def test_correct_guess_updates_high_score(self):
        """The user's high_score must be persisted when the streak exceeds it."""
        self._set_session()
        self.client.post(reverse("quiz"), {"guess": "Alpha"})

        self.user.refresh_from_db()
        self.assertEqual(self.user.high_score, 1)

    def test_wrong_guess_increments_games_played(self):
        """Every completed game (win or loss) must increment games_played."""
        self._set_session()
        self.client.post(reverse("quiz"), {"guess": "WRONG"})

        self.user.refresh_from_db()
        self.assertEqual(self.user.games_played, 1)

    def test_wrong_guess_adds_mastered_flags(self):
        """
        Any flags correctly identified before the loss should be added
        to mastered_flags so the player keeps progress.
        """
        # Seed as if the player already correctly guessed Alpha
        self._set_session(extra={
            "quiz_streak": 1,
            "quiz_collected_flags": [self.country_a.flag_image_url],
            "quiz_collected_names": [self.country_a.name],
            "quiz_country": {
                "name": self.country_b.name,
                "flag_image_url": self.country_b.flag_image_url,
                "flag_emoji": self.country_b.flag_emoji,
                "region": self.country_b.region,
                "entry_type": self.country_b.entry_type,
            },
        })
        self.client.post(reverse("quiz"), {"guess": "WRONG"})

        self.user.refresh_from_db()
        mastered_names = list(self.user.mastered_flags.values_list("name", flat=True))
        self.assertIn(self.country_a.name, mastered_names)

    def test_quiz_get_redirects_to_gamemode_if_no_session(self):
        """
        A fresh GET with no gamemode in the session must render the
        gamemode selection screen, not crash.
        """
        response = self.client.get(reverse("quiz"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("show_gamemode_select", response.context)

    def test_change_gamemode_clears_session(self):
        """
        change_gamemode() must wipe all quiz keys so the player starts fresh.
        Leftover keys from a previous game would corrupt the new game's state.
        """
        self._set_session()
        self.client.get(reverse("change_gamemode"))

        session = self.client.session
        for key in ["quiz_gamemode", "quiz_country", "quiz_streak",
                    "quiz_collected_flags", "quiz_collected_names"]:
            self.assertNotIn(key, session)


# Rate Limiting Tests
class LoginRateLimitTest(TestCase):
    """
    The login view applies a 5-attempt-per-minute cap per IP.
    If the cap is broken, brute-force attacks become trivially easy.
    """

    def setUp(self):
        cache.clear()
        self.client = Client()
        make_user(email="victim@example.com", password="real_pass!")

    def test_rate_limit_blocks_after_five_attempts(self):
        """The 6th failed login from the same IP must be rejected with an error message."""
        url = reverse("login")
        for _ in range(5):
            self.client.post(url, {"email": "victim@example.com", "password": "bad"})

        response = self.client.post(url, {"email": "victim@example.com", "password": "bad"})
        # The view re-renders the login page (200) with an error, not a redirect
        self.assertEqual(response.status_code, 200)
        messages = list(response.context["messages"])
        self.assertTrue(any("Too many" in str(m) for m in messages))


# Country Detail View Tests
class CountryDetailViewTest(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user()
        self.client = Client()
        self.client.force_login(self.user)
        self.country = make_country(name="Detail Country", region="Asia")

    def test_known_country_returns_200(self):
        from django.utils.text import slugify
        slug = slugify(self.country.name)
        response = self.client.get(reverse("country", args=[slug]))
        self.assertEqual(response.status_code, 200)

    def test_unknown_country_redirects(self):
        """A slug that matches no country should redirect to the index rather than 404/500."""
        response = self.client.get(reverse("country", args=["nonexistent-slug"]))
        self.assertEqual(response.status_code, 302)


# Mastery View Tests
class MasteryViewTest(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user()
        self.client = Client()
        self.client.force_login(self.user)
        self.country = make_country(name="Masteria")

    def test_mastery_page_renders(self):
        response = self.client.get(reverse("mastery"))
        self.assertEqual(response.status_code, 200)

    def test_mastered_flag_appears_in_context(self):
        """Countries the user has mastered must be marked in the context entries."""
        self.user.mastered_flags.add(self.country)
        response = self.client.get(reverse("mastery"))
        mastered_entries = [e for e in response.context["entries"] if e["mastered"]]
        self.assertTrue(any(e["name"] == "Masteria" for e in mastered_entries))


# Delete Account Tests
class DeleteAccountTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = Client()
        self.client.force_login(self.user)

    def test_post_deletes_user_and_redirects(self):
        """POSTing to delete_account must remove the user and redirect to index."""
        user_pk = self.user.pk
        response = self.client.post(reverse("delete_account"))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Vexillologist.objects.filter(pk=user_pk).exists())

    def test_get_redirects_to_settings(self):
        """A GET (e.g. opening the URL in a new tab) must not delete anything."""
        user_pk = self.user.pk
        response = self.client.get(reverse("delete_account"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Vexillologist.objects.filter(pk=user_pk).exists())
