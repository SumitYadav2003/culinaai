from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from recipes.models import FavouriteRecipe, Recipe, RecipeFeedback, RecipeRating

from .forms import (
    CulinaPasswordChangeForm,
    LoginForm,
    SignUpForm,
    UserAccountUpdateForm,
    UserProfileUpdateForm,
)
from .models import UserProfile
from .email_service import send_welcome_email


def signup_view(request):
    """
    Create a new user account.

    After successful signup:
    - user account is created
    - welcome email is sent
    - user is redirected to login page with registered flag
    - user is not automatically logged in
    """

    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = SignUpForm(request.POST)

        if form.is_valid():
            user = form.save()

            email_sent = send_welcome_email(request, user)

            if email_sent:
                messages.success(
                    request,
                    "Your CulinaAI account has been created successfully. A welcome email has been sent to your inbox.",
                )
            else:
                messages.success(
                    request,
                    "Your CulinaAI account has been created successfully. Please log in to continue.",
                )

            login_url = reverse("login") + "?registered=1"
            return redirect(login_url)

        messages.error(request, "Please correct the errors below.")
    else:
        form = SignUpForm()

    return render(request, "accounts/signup.html", {"form": form})


def login_view(request):
    """
    Log in an existing user.

    Role-based redirect:
    - Normal users go to the user dashboard.
    - Staff/admin users go directly to the CulinaAI Quality Dashboard.
    - Safe next URLs are still respected when present.
    """

    if request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            return redirect("quality_dashboard")

        return redirect("dashboard")

    next_url = request.GET.get("next") or request.POST.get("next")
    just_registered = request.GET.get("registered") == "1"

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)

        if form.is_valid():
            user = form.get_user()
            login(request, user)

            if next_url and url_has_allowed_host_and_scheme(
                url=next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)

            if user.is_staff or user.is_superuser:
                return redirect("quality_dashboard")

            return redirect("dashboard")

        messages.error(request, "Invalid username or password.")
    else:
        form = LoginForm()

    return render(
    request,
    "accounts/login.html",
    {
        "form": form,
        "next": next_url,
        "just_registered": just_registered,
    },
)


def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect("home")


@login_required
def profile_summary_view(request):
    """
    Display and update the logged-in user's professional profile page.

    This page allows users to:
    - view account details
    - upload a profile image
    - update name, username and email
    - directly change password from profile page
    - view recipe activity statistics
    """

    profile, created = UserProfile.objects.get_or_create(user=request.user)

    account_form = UserAccountUpdateForm(
        instance=request.user,
        user=request.user,
    )

    profile_form = UserProfileUpdateForm(instance=profile)

    password_form = CulinaPasswordChangeForm(request.user)

    if request.method == "POST":
        form_type = request.POST.get("form_type")

        if form_type == "password_change":
            password_form = CulinaPasswordChangeForm(
                request.user,
                request.POST,
            )

            if password_form.is_valid():
                user = password_form.save()

                update_session_auth_hash(request, user)

                messages.success(
                    request,
                    "Your password has been changed successfully. Please use your new password next time you log in.",
                )

                return redirect("profile_summary")

            messages.error(
                request,
                "Please correct the password errors below.",
            )

        else:
            account_form = UserAccountUpdateForm(
                request.POST,
                instance=request.user,
                user=request.user,
            )

            profile_form = UserProfileUpdateForm(
                request.POST,
                request.FILES,
                instance=profile,
            )

            if account_form.is_valid() and profile_form.is_valid():
                account_form.save()
                profile_form.save()

                messages.success(
                    request,
                    "Your profile has been updated successfully.",
                )

                return redirect("profile_summary")

            messages.error(
                request,
                "Please correct the errors below before saving your profile.",
            )

    saved_recipes = Recipe.objects.filter(
        user=request.user,
        is_saved=True,
    )

    favourite_recipes = FavouriteRecipe.objects.filter(
        user=request.user,
        recipe__is_saved=True,
    )

    ratings = RecipeRating.objects.filter(user=request.user)
    feedback_entries = RecipeFeedback.objects.filter(user=request.user)

    total_saved_recipes = saved_recipes.count()
    total_favourite_recipes = favourite_recipes.count()
    total_ratings = ratings.count()
    total_feedback = feedback_entries.count()

    original_recipe_count = saved_recipes.filter(
        original_recipe__isnull=True,
    ).count()

    modified_recipe_count = saved_recipes.filter(
        original_recipe__isnull=False,
    ).count()

    public_recipe_count = saved_recipes.filter(
        is_public=True,
    ).count()

    recent_recipes = saved_recipes.order_by("-created_at")[:4]

    profile_completion_items = [
        bool(request.user.username),
        bool(request.user.email),
        bool(request.user.first_name),
        bool(request.user.last_name),
        bool(profile.profile_image),
    ]

    profile_completion = int(
        (sum(profile_completion_items) / len(profile_completion_items)) * 100
    )

    context = {
        "profile": profile,
        "account_form": account_form,
        "profile_form": profile_form,
        "password_form": password_form,
        "total_saved_recipes": total_saved_recipes,
        "total_favourite_recipes": total_favourite_recipes,
        "total_ratings": total_ratings,
        "total_feedback": total_feedback,
        "original_recipe_count": original_recipe_count,
        "modified_recipe_count": modified_recipe_count,
        "public_recipe_count": public_recipe_count,
        "recent_recipes": recent_recipes,
        "profile_completion": profile_completion,
    }

    return render(request, "accounts/profile_summary.html", context)