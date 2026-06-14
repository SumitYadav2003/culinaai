from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class SignUpForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            "class": "form-control auth-input",
            "placeholder": "Enter your email address",
        })
    )

    username = forms.CharField(
        widget=forms.TextInput(attrs={
            "class": "form-control auth-input",
            "placeholder": "Choose a username",
        })
    )

    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "form-control auth-input",
            "placeholder": "Create a password",
        })
    )

    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "form-control auth-input",
            "placeholder": "Confirm your password",
        })
    )

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]



# Login form
from django.contrib.auth.forms import AuthenticationForm


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            "class": "form-control auth-input",
            "placeholder": "Enter your username",
        })
    )

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "form-control auth-input",
            "placeholder": "Enter your password",
        })
    )