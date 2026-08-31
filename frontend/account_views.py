"""Authentication and account-management views."""

import hashlib
import logging

import requests
from allauth.account.models import EmailAddress
from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth import login as auth_login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render

from .forms import (
    LoginForm,
    PasswordChangeForm,
    UsernameChangeForm,
    VexillologistChangeForm,
    VexillologistCreationForm,
)


logger = logging.getLogger(__name__)


def _client_ip(request):
    fly_ip = request.META.get("HTTP_FLY_CLIENT_IP")
    if fly_ip:
        return fly_ip.strip()

    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _login_attempt_key(request):
    digest = hashlib.sha256(_client_ip(request).encode()).hexdigest()
    return f"login_attempts:{digest}"


def _captcha_is_valid(token):
    try:
        response = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={
                "secret": django_settings.RECAPTCHA_SECRET_KEY,
                "response": token,
            },
            timeout=(5, 10),
        )
        return response.json().get("success", False)
    except requests.exceptions.RequestException:
        return False


def signup(request):
    form = VexillologistCreationForm(request.POST or None)
    if request.method == "POST":
        token = request.POST.get("g-recaptcha-response", "")
        if not _captcha_is_valid(token):
            messages.error(request, "Please complete the CAPTCHA.")
        elif form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save()
                    email_address = EmailAddress.objects.create(
                        user=user,
                        email=user.email,
                        primary=True,
                        verified=False,
                    )
            except IntegrityError:
                form.add_error("email", "An account with that email already exists.")
            else:
                auth_login(
                    request,
                    user,
                    backend="django.contrib.auth.backends.ModelBackend",
                )
                _send_signup_confirmation(request, email_address)
                return redirect("index")

    return render(
        request,
        "signup.html",
        {
            "form": form,
            "recaptcha_site_key": django_settings.RECAPTCHA_SITE_KEY,
        },
    )


def _send_signup_confirmation(request, email_address):
    try:
        email_address.send_confirmation(request, signup=True)
    except Exception:
        # The account exists even when the external email service is unavailable.
        logger.exception("Unable to send signup confirmation email")
        messages.warning(
            request,
            "Your account was created, but the confirmation email could not be sent. "
            "You can resend it from Settings.",
        )


def login_view(request):
    form = LoginForm(request.POST or None)
    if request.method == "POST":
        cache_key = _login_attempt_key(request)
        attempts = cache.get(cache_key, 0)
        if attempts >= 5:
            messages.error(
                request,
                "Too many login attempts. Please wait a minute and try again.",
            )
            return render(request, "login.html", {"form": LoginForm()})

        if form.is_valid():
            cache.delete(cache_key)
            auth_login(
                request,
                form.user,
                backend="django.contrib.auth.backends.ModelBackend",
            )
            return redirect("index")
        cache.set(cache_key, attempts + 1, 60)

    return render(request, "login.html", {"form": form})


@login_required
def settings(request):
    profile_form = VexillologistChangeForm(instance=request.user)
    username_form = UsernameChangeForm(instance=request.user)
    password_form = PasswordChangeForm(user=request.user)

    if request.method == "POST":
        form_type = request.POST.get("form_type")
        if form_type == "profile":
            profile_form = VexillologistChangeForm(request.POST, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Profile updated!")
                return redirect("settings")
        elif form_type == "username":
            username_form = UsernameChangeForm(request.POST, instance=request.user)
            if username_form.is_valid():
                username_form.save()
                messages.success(request, "Username updated!")
                return redirect("settings")
        elif form_type == "password":
            password_form = PasswordChangeForm(user=request.user, data=request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)
                messages.success(request, "Password updated!")
                return redirect("settings")

    email_record = EmailAddress.objects.filter(user=request.user, primary=True).first()
    return render(
        request,
        "settings.html",
        {
            "profile_form": profile_form,
            "username_form": username_form,
            "password_form": password_form,
            "email_verified": bool(email_record and email_record.verified),
        },
    )


@login_required
def resend_confirmation(request):
    if request.method == "POST":
        email_record, _ = EmailAddress.objects.get_or_create(
            user=request.user,
            defaults={
                "email": request.user.email,
                "primary": True,
                "verified": False,
            },
        )
        if email_record.verified:
            messages.info(request, "Your email is already confirmed.")
        else:
            email_record.send_confirmation(request)
            messages.success(request, "Confirmation email sent! Check your inbox.")
    return redirect("settings")


@login_required
def delete_account(request):
    if request.method == "POST":
        request.user.delete()
        messages.success(request, "Your account has been successfully deleted.")
        return redirect("index")
    return redirect("settings")
