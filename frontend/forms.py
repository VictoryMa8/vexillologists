import os

from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import (
    PasswordChangeForm as DjangoPasswordChangeForm,
    UserCreationForm,
)

from .models import Vexillologist

DEFAULT_BLOCKED = {
    "admin",
    "administrator",
    "moderator",
    "support",
    "staff",
    "root",
    "owner",
}
BLOCKED_USERNAME_SUBSTRINGS = DEFAULT_BLOCKED | {
    word.strip().lower()
    for word in os.getenv("BLOCKED_USERNAME_WORDS", "").split(",")
    if word.strip()
}
LEET_MAP = str.maketrans(
    {
        "0": "o",
        "1": "i",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
        "@": "a",
        "$": "s",
        "!": "i",
    }
)
FORM_INPUT_CLASSES = "input input-bordered w-full focus:outline-primary"


class StyledFieldsMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {FORM_INPUT_CLASSES}".strip()


def validate_username(username):
    if not username:
        return username
    normalized = username.lower().translate(LEET_MAP)
    stripped = "".join(c for c in normalized if c.isalnum())
    for term in BLOCKED_USERNAME_SUBSTRINGS:
        if term and (term in normalized or term in stripped):
            raise forms.ValidationError("That username isn't allowed. Please choose another.")
    return username


class VexillologistCreationForm(StyledFieldsMixin, UserCreationForm):
    class Meta:
        model = Vexillologist
        fields = ("username", "email")

    def clean_username(self):
        username = self.cleaned_data.get("username")
        if Vexillologist.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return validate_username(username)

    def clean_email(self):
        email = Vexillologist.objects.normalize_email(
            self.cleaned_data.get("email", "")
        ).strip()
        if Vexillologist.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with that email already exists.")
        return email


class LoginForm(StyledFieldsMixin, forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        password = cleaned_data.get("password")

        if not email or not password:
            return cleaned_data

        user_record = Vexillologist.objects.filter(email__iexact=email).first()
        user = None
        if user_record:
            # authenticate() also enforces backend policy, including inactive users.
            user = authenticate(username=user_record.get_username(), password=password)

        if not user:
            raise forms.ValidationError("Invalid email or password.")

        self.user = user
        return cleaned_data


class VexillologistChangeForm(StyledFieldsMixin, forms.ModelForm):
    class Meta:
        model = Vexillologist
        fields = ('first_name', 'last_name')


class UsernameChangeForm(StyledFieldsMixin, forms.ModelForm):
    class Meta:
        model = Vexillologist
        fields = ('username',)

    def clean_username(self):
        username = self.cleaned_data.get('username')
        username_exists = Vexillologist.objects.exclude(pk=self.instance.pk).filter(
            username__iexact=username
        ).exists()
        if username_exists:
            raise forms.ValidationError("That username is already taken.")
        return validate_username(username)


class PasswordChangeForm(StyledFieldsMixin, DjangoPasswordChangeForm):
    """Django's password-change behavior with the shared input styling."""
