from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm
from django.contrib.auth.models import User
from django.utils.text import slugify

from .models import UserProfile


class SignUpForm(UserCreationForm):
    full_name = forms.CharField(
        required=True,
        label="Full name",
        widget=forms.TextInput(attrs={
            "class": "form-control auth-input",
            "placeholder": "Enter your full name, e.g. Sumit Yadav",
        })
    )

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            "class": "form-control auth-input",
            "placeholder": "Enter your email address",
        })
    )

    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "form-control auth-input password-toggle-input",
            "placeholder": "Create a password",
        })
    )

    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "form-control auth-input password-toggle-input",
            "placeholder": "Confirm your password",
        })
    )

    class Meta:
        model = User
        fields = ["full_name", "email", "password1", "password2"]

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("This email address is already used by another account.")

        return email

    def generate_unique_username(self, full_name, email):
        base_username = slugify(full_name).replace("-", "")

        if not base_username:
            base_username = slugify(email.split("@")[0]).replace("-", "")

        if not base_username:
            base_username = "user"

        username = base_username[:140]
        counter = 1

        while User.objects.filter(username=username).exists():
            username = f"{base_username[:135]}{counter}"
            counter += 1

        return username

    def save(self, commit=True):
        user = super().save(commit=False)

        full_name = self.cleaned_data.get("full_name", "").strip()
        email = self.cleaned_data.get("email", "").strip().lower()

        name_parts = full_name.split()

        if name_parts:
            user.first_name = name_parts[0]
            user.last_name = " ".join(name_parts[1:])

        user.email = email

        # Django needs username internally, but user will never see it.
        user.username = self.generate_unique_username(full_name, email)

        # Public signup must always create normal users only.
        user.is_staff = False
        user.is_superuser = False

        if commit:
            user.save()

        return user


class LoginForm(AuthenticationForm):
    username = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(attrs={
            "class": "form-control auth-input",
            "placeholder": "Enter your email address",
        })
    )

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "form-control auth-input password-toggle-input",
            "placeholder": "Enter your password",
        })
    )

    def clean(self):
        email = self.cleaned_data.get("username", "").strip().lower()

        if email:
            user = User.objects.filter(email__iexact=email).first()

            if user:
                # Django internally authenticates by username.
                self.cleaned_data["username"] = user.username
            else:
                raise forms.ValidationError("No account found with this email address.")

        return super().clean()


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
            "class": "profile-edit-input password-toggle-input",
            "placeholder": "Enter your current password",
        }),
    )

    new_password1 = forms.CharField(
        label="New password",
        widget=forms.PasswordInput(attrs={
            "class": "profile-edit-input password-toggle-input",
            "placeholder": "Enter your new password",
        }),
    )

    new_password2 = forms.CharField(
        label="Confirm new password",
        widget=forms.PasswordInput(attrs={
            "class": "profile-edit-input password-toggle-input",
            "placeholder": "Confirm your new password",
        }),
    )