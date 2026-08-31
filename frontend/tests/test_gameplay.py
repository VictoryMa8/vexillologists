from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from frontend.models import FlagProgress, GameResult

from .factories import make_country, make_user


class QuizTest(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user()
        self.client = Client()
        self.client.force_login(self.user)
        self.country_a = make_country(
            name="Alpha",
            region="Europe",
            flag_image_url="https://example.com/a.png",
        )
        self.country_b = make_country(
            name="Beta",
            region="Europe",
            flag_image_url="https://example.com/b.png",
        )

    def _set_session(self, **overrides):
        values = {
            "quiz_gamemode": "world_tour",
            "quiz_pool_size": 2,
            "quiz_country": {
                "name": self.country_a.name,
                "flag_image_url": self.country_a.flag_image_url,
                "flag_emoji": self.country_a.flag_emoji,
                "region": self.country_a.region,
                "entry_type": self.country_a.entry_type,
            },
            "quiz_streak": 0,
            "quiz_collected": [],
        }
        values.update(overrides)
        session = self.client.session
        session.update(values)
        session.save()

    def test_correct_guess_increments_streak(self):
        self._set_session()
        self.client.post(reverse("quiz"), {"guess": "Alpha"})
        self.assertEqual(self.client.session["quiz_streak"], 1)

    def test_wrong_guess_ends_game(self):
        self._set_session()
        self.client.post(reverse("quiz"), {"guess": "WRONG"})
        self.assertTrue(self.client.session["quiz_result"]["game_over"])
        self.assertEqual(self.client.session["quiz_streak"], 0)

    def test_correct_guess_updates_high_score(self):
        self._set_session()
        self.client.post(reverse("quiz"), {"guess": "Alpha"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.high_score, 1)

    def test_correct_guess_persists_mastery_immediately(self):
        self._set_session()
        self.client.post(reverse("quiz"), {"guess": "Alpha"})

        self.assertTrue(
            self.user.mastered_flags.filter(pk=self.country_a.pk).exists()
        )
        progress = FlagProgress.objects.get(user=self.user, country=self.country_a)
        self.assertEqual(progress.attempts, 1)
        self.assertEqual(progress.correct_answers, 1)

    def test_wrong_guess_increments_games_played(self):
        self._set_session()
        self.client.post(reverse("quiz"), {"guess": "WRONG"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.games_played, 1)

    def test_completed_flags_remain_mastered_after_a_loss(self):
        self._set_session(
            quiz_streak=1,
            quiz_collected=[
                {
                    "flag": self.country_a.flag_image_url,
                    "name": self.country_a.name,
                    "fact": self.country_a.fact,
                }
            ],
            quiz_country={
                "name": self.country_b.name,
                "flag_image_url": self.country_b.flag_image_url,
                "flag_emoji": self.country_b.flag_emoji,
                "region": self.country_b.region,
                "entry_type": self.country_b.entry_type,
            },
        )
        self.client.post(reverse("quiz"), {"guess": "WRONG"})
        self.assertTrue(self.user.mastered_flags.filter(pk=self.country_a.pk).exists())

    def test_fresh_quiz_shows_mode_picker(self):
        response = self.client.get(reverse("quiz"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("show_gamemode_select", response.context)

    def test_refresh_preserves_active_game(self):
        self._set_session(quiz_streak=1)
        response = self.client.get(reverse("quiz"))
        self.assertEqual(self.client.session["quiz_streak"], 1)
        self.assertEqual(response.context["streak"], 1)

    def test_change_gamemode_clears_session(self):
        self._set_session()
        self.client.post(reverse("change_gamemode"))
        for key in [
            "quiz_gamemode",
            "quiz_country",
            "quiz_streak",
            "quiz_collected",
        ]:
            self.assertNotIn(key, self.client.session)


class ExpandedGameModesTest(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user(username="mode-player", email="modes@example.com")
        self.client.force_login(self.user)
        self.countries = [
            make_country(
                name=f"Mode Country {index:02d}",
                region="Europe" if index % 2 else "Asia",
                flag_image_url=f"https://example.com/{index}.png",
            )
            for index in range(12)
        ]

    def _select(self, mode):
        response = self.client.post(reverse("quiz"), {"gamemode": mode})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get("quiz_gamemode"), mode)

    def test_new_modes_are_selectable(self):
        for mode in [
            "practice",
            "daily",
            "speed_round",
            "perfect_ten",
            "multiple_choice",
            "mastery_review",
        ]:
            with self.subTest(mode=mode):
                self._select(mode)

    def test_practice_uses_lives_instead_of_sudden_death(self):
        self._select("practice")
        self.client.post(reverse("quiz"), {"guess": "Definitely wrong"})

        session = self.client.session
        self.assertEqual(session["quiz_lives"], 2)
        self.assertFalse(session["quiz_result"]["game_finished"])
        self.assertEqual(FlagProgress.objects.get(user=self.user).wrong_answers, 1)

    def test_multiple_choice_builds_four_visual_options(self):
        self._select("multiple_choice")
        session = self.client.session
        self.assertEqual(len(session["quiz_choices"]), 4)
        self.assertIn(
            session["quiz_country"]["name"],
            [choice["name"] for choice in session["quiz_choices"]],
        )

    def test_perfect_ten_records_a_perfect_result(self):
        self._select("perfect_ten")
        for _ in range(10):
            truth = self.client.session["quiz_country"]["name"]
            self.client.post(reverse("quiz"), {"guess": truth})

        result = GameResult.objects.get(user=self.user, gamemode="perfect_ten")
        self.assertEqual(result.score, 10)
        self.assertEqual(result.answered, 10)
        self.assertEqual(result.incorrect, 0)

    def test_speed_round_enforces_server_deadline(self):
        self._select("speed_round")
        session = self.client.session
        session["quiz_deadline"] = 0
        session.save()
        self.client.post(reverse("quiz"), {"quiz_action": "timeout"})
        self.assertEqual(
            GameResult.objects.get(user=self.user, gamemode="speed_round").outcome,
            "timed_out",
        )

    def test_daily_pool_is_the_same_for_every_player(self):
        self._select("daily")
        first_pool = self.client.session["quiz_pool_names"]

        other = make_user(username="other-mode-player", email="other-modes@example.com")
        other_client = Client()
        other_client.force_login(other)
        other_client.post(reverse("quiz"), {"gamemode": "daily"})
        self.assertEqual(first_pool, other_client.session["quiz_pool_names"])

    def test_mastery_review_prioritizes_unmastered_flags(self):
        self.user.mastered_flags.add(*self.countries[:-1])
        self._select("mastery_review")
        self.assertEqual(
            self.client.session["quiz_country"]["name"],
            self.countries[-1].name,
        )

    def test_mode_picker_is_grouped(self):
        self.client.post(reverse("change_gamemode"))
        response = self.client.get(reverse("quiz"))
        section_names = [
            section["title"] for section in response.context["gamemode_sections"]
        ]
        self.assertEqual(
            section_names,
            ["Ways to Play", "Regional Challenges", "Special Collections"],
        )


class PerModeLeaderboardTest(TestCase):
    def setUp(self):
        self.user = make_user(username="leader", email="leader@example.com")
        self.client.force_login(self.user)

    def test_leaderboard_uses_selected_mode_scores(self):
        GameResult.objects.create(
            user=self.user,
            gamemode="perfect_ten",
            score=8,
            answered=10,
            correct=8,
            incorrect=2,
        )
        response = self.client.get(reverse("leaderboard"), {"mode": "perfect_ten"})
        self.assertEqual(response.context["selected_mode"], "perfect_ten")
        self.assertEqual(response.context["top_players"][0]["best_score"], 8)
