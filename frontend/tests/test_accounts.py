from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from frontend.forms import LoginForm, UsernameChangeForm, VexillologistCreationForm
from frontend.models import Vexillologist

from .factories import make_user


class LoginFormTest(TestCase):
    def setUp(self):
        self.user = make_user(
            email="login@example.com",
            password="correct_pass!",
        )

    def test_valid_credentials(self):
        form = LoginForm(
            data={"email": "login@example.com", "password": "correct_pass!"}
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.user, self.user)

    def test_wrong_password(self):
        form = LoginForm(
            data={"email": "login@example.com", "password": "wrong_pass!"}
        )
        self.assertFalse(form.is_valid())

    def test_nonexistent_email(self):
        form = LoginForm(
            data={"email": "nobody@example.com", "password": "any_pass!"}
        )
        self.assertFalse(form.is_valid())

    def test_case_insensitive_email(self):
        form = LoginForm(
            data={"email": "LOGIN@EXAMPLE.COM", "password": "correct_pass!"}
        )
        self.assertTrue(form.is_valid())

    def test_empty_fields_invalid(self):
        self.assertFalse(LoginForm(data={"email": "", "password": ""}).is_valid())

    def test_inactive_user_cannot_login(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        form = LoginForm(
            data={"email": "login@example.com", "password": "correct_pass!"}
        )
        self.assertFalse(form.is_valid())


class SignupFormTest(TestCase):
    def test_email_is_unique_case_insensitively(self):
        make_user(email="used@example.com")
        form = VexillologistCreationForm(
            data={
                "username": "another-user",
                "email": "USED@example.com",
                "password1": "strong-test-password!23",
                "password2": "strong-test-password!23",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)


class SignupViewTest(TestCase):
    @patch(
        "frontend.account_views.EmailAddress.send_confirmation",
        side_effect=RuntimeError("SMTP unavailable"),
    )
    @patch("frontend.account_views.requests.post")
    def test_email_failure_does_not_rollback_created_account(
        self,
        recaptcha_post,
        send_confirmation,
    ):
        recaptcha_post.return_value.json.return_value = {"success": True}
        response = self.client.post(
            reverse("signup"),
            {
                "username": "resilient-user",
                "email": "resilient@example.com",
                "password1": "strong-test-password!23",
                "password2": "strong-test-password!23",
                "g-recaptcha-response": "test-token",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Vexillologist.objects.filter(email="resilient@example.com").exists()
        )


class UsernameChangeFormTest(TestCase):
    def setUp(self):
        self.user = make_user(username="original")
        make_user(username="taken", email="other@example.com")

    def test_taken_username_rejected(self):
        form = UsernameChangeForm(data={"username": "taken"}, instance=self.user)
        self.assertFalse(form.is_valid())

    def test_own_username_allowed(self):
        form = UsernameChangeForm(data={"username": "original"}, instance=self.user)
        self.assertTrue(form.is_valid())

    def test_new_unique_username_allowed(self):
        form = UsernameChangeForm(data={"username": "brandnew"}, instance=self.user)
        self.assertTrue(form.is_valid())

    def test_case_insensitive_uniqueness(self):
        form = UsernameChangeForm(data={"username": "TAKEN"}, instance=self.user)
        self.assertFalse(form.is_valid())


class LoginRateLimitTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        make_user(email="victim@example.com", password="real_pass!")

    def test_rate_limit_blocks_after_five_attempts(self):
        url = reverse("login")
        for _ in range(5):
            self.client.post(
                url,
                {"email": "victim@example.com", "password": "bad"},
            )

        response = self.client.post(
            url,
            {"email": "victim@example.com", "password": "bad"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            any("Too many" in str(message) for message in response.context["messages"])
        )


class DeleteAccountTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)

    def test_post_deletes_user_and_redirects(self):
        user_pk = self.user.pk
        response = self.client.post(reverse("delete_account"))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Vexillologist.objects.filter(pk=user_pk).exists())

    def test_get_redirects_without_deleting_user(self):
        user_pk = self.user.pk
        response = self.client.get(reverse("delete_account"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Vexillologist.objects.filter(pk=user_pk).exists())
