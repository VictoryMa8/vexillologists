import os
from django import forms
# Using Django's built-in UserCreationForm and PasswordChangeForm to inherit from
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm as DjangoPasswordChangeForm
from .models import Vexillologist

# Generic impersonation defaults; sensitive terms come from BLOCKED_USERNAME_WORDS env var.
DEFAULT_BLOCKED = {"admin", "administrator", "moderator", "support", "staff", "root", "owner"}

# Set of substrings that are not allowed in usernames
BLOCKED_USERNAME_SUBSTRINGS = DEFAULT_BLOCKED | {
    w.strip().lower() for w in os.getenv("BLOCKED_USERNAME_WORDS", "").split(",") if w.strip()
}

# Map of characters that users could replace for leet speak
LEET_MAP = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i"})

def validate_username(username):
    if not username:
        return username
    normalized = username.lower().translate(LEET_MAP)
    stripped = "".join(c for c in normalized if c.isalnum())
    for term in BLOCKED_USERNAME_SUBSTRINGS:
        if term and (term in normalized or term in stripped):
            raise forms.ValidationError("That username isn't allowed. Please choose another.")
    return username

# Form for creating a new user (Vexillologist) using UserCreationForm
class VexillologistCreationForm(UserCreationForm):
    class Meta:
        model = Vexillologist
        fields = ("username", "email")

    def clean_username(self):
        username = self.cleaned_data.get("username")
        return validate_username(username)

class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

    '''
    Built-in hook used for custom validation
    Since we want to login with email instead, we have to manually check credentials
    To verify a user, we need both email and password, clean() accesses both
    Without this, form would just verify the user typed something into email/password
    It wouldn't actually verify who they are against the database
    '''

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        password = cleaned_data.get("password")

        if not email or not password:
            return cleaned_data

        user = Vexillologist.objects.filter(email__iexact=email).first()

        # check_password() hashes and compares it to stored encrypted passwords
        if not user or not user.check_password(password): 
            raise forms.ValidationError("Invalid email or password.")

        self.user = user
        return cleaned_data


class VexillologistChangeForm(forms.ModelForm):
    class Meta:
        model = Vexillologist
        fields = ('first_name', 'last_name')


class UsernameChangeForm(forms.ModelForm):
    class Meta:
        model = Vexillologist
        fields = ('username',)

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if Vexillologist.objects.exclude(pk=self.instance.pk).filter(username__iexact=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return validate_username(username)


class PasswordChangeForm(DjangoPasswordChangeForm):
    pass
