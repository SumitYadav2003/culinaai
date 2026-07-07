from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm
from django.contrib.auth.models import User

from .models import UserProfile


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


class UserAccountUpdateForm(forms.ModelForm):
    """
    Allows users to update their basic account details.
    """

    first_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "class": "profile-edit-input",
            "placeholder": "Enter your first name",
        }),
    )

    last_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "class": "profile-edit-input",
            "placeholder": "Enter your last name",
        }),
    )

    username = forms.CharField(
        widget=forms.TextInput(attrs={
            "class": "profile-edit-input",
            "placeholder": "Enter your username",
        }),
    )

    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            "class": "profile-edit-input",
            "placeholder": "Enter your email address",
        }),
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "username", "email"]

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def clean_username(self):
        username = self.cleaned_data.get("username")

        existing_user = User.objects.filter(username=username).exclude(
            id=self.user.id
        ).first()

        if existing_user:
            raise forms.ValidationError("This username is already taken.")

        return username

    def clean_email(self):
        email = self.cleaned_data.get("email")

        existing_user = User.objects.filter(email=email).exclude(
            id=self.user.id
        ).first()

        if existing_user:
            raise forms.ValidationError("This email address is already used by another account.")

        return email


class UserProfileUpdateForm(forms.ModelForm):
    """
    Allows users to upload or update their profile image.
    """

    profile_image = forms.ImageField(
    required=False,
    widget=forms.FileInput(attrs={
        "class": "profile-image-input",
        "accept": "image/*",
        "id": "id_profile_image",
    }),
)

    bio = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "profile-edit-textarea",
            "placeholder": "Write a short bio about your cooking preferences...",
            "rows": 4,
        }),
    )

    class Meta:
        model = UserProfile
        fields = ["profile_image", "bio"]























class CulinaPasswordChangeForm(PasswordChangeForm):
    """
    Allows logged-in users to change their password from the profile page.
    """

    old_password = forms.CharField(
        label="Current password",
        widget=forms.PasswordInput(attrs={
            "class": "profile-edit-input",
            "placeholder": "Enter your current password",
        }),
    )

    new_password1 = forms.CharField(
        label="New password",
        widget=forms.PasswordInput(attrs={
            "class": "profile-edit-input",
            "placeholder": "Enter your new password",
        }),
    )

    new_password2 = forms.CharField(
        label="Confirm new password",
        widget=forms.PasswordInput(attrs={
            "class": "profile-edit-input",
            "placeholder": "Confirm your new password",
        }),
    )