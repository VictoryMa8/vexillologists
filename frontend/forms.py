from django import forms
# Using Django's built-in UserCreationForm and PasswordChangeForm to inherit from
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm as DjangoPasswordChangeForm
from .models import Vexillologist

# Form for creating a new user (Vexillologist) using UserCreationForm
class VexillologistCreationForm(UserCreationForm):
    class Meta:
        model = Vexillologist
        fields = ("username", "email")

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
        return username


class PasswordChangeForm(DjangoPasswordChangeForm):
    pass
