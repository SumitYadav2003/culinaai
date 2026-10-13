import time

from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.encoding import force_str
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme, urlsafe_base64_decode
from django.views.decorators.http import require_POST

from recipes.models import FavouriteRecipe, Recipe, RecipeFeedback, RecipeRating

from .forms import (
    CulinaPasswordChangeForm,
    LoginForm,
    SignUpForm,
    UserAccountUpdateForm,
    UserProfileUpdateForm,
)
from .confirmation import mark_unconfirmed, needs_email_confirmation
from .data_service import delete_account, export_user_data_json
from .email_service import send_confirmation_email, send_welcome_email
from .models import UserProfile
from .tokens import email_confirm_token

# How long someone must wait before asking for another confirmation email.
RESEND_WAIT_SECONDS = 60


def signup_view(request):
    """
    Create a new account, log the person in and send the welcome email, which
    carries the link to confirm their email address. They can look around
    straight away; the AI features open once the email is confirmed.
    """

    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = SignUpForm(request.POST)

        if form.is_valid():
            user = form.save()
            mark_unconfirmed(user)
            confirm = needs_email_confirmation(user)

            email_sent = send_welcome_email(request, user, confirm=confirm)
            request.session["confirmation_sent_at"] = time.time()
            login(request, user)

            if confirm and email_sent:
                messages.success(
                    request,
                    f"Welcome to CulinaAI. We've sent a link to {user.email}. "
                    "Open it to confirm your email, then you can make your first recipe.",
                )
            elif confirm:
                messages.warning(
                    request,
                    "Welcome to CulinaAI. We couldn't send the email to confirm your address just now. "
                    "Use Send the link again at the top of the page in a minute.",
                )
            else:
                messages.success(request, "Welcome to CulinaAI. Your account is ready.")

            return redirect("dashboard")

        messages.error(request, "Something needs fixing. Check the form below.")
    else:
        form = SignUpForm()

    return render(request, "accounts/signup.html", {"form": form})


def confirm_email_view(request, uidb64, token):
    """Opened from the link in the email. Works whether or not the person is logged in."""

    User = get_user_model()
    try:
        user = User.objects.select_related("profile").get(pk=force_str(urlsafe_base64_decode(uidb64)))
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and getattr(user, "profile", None) and user.profile.email_confirmed:
        messages.info(request, "Your email is already confirmed.")
    elif user is not None and email_confirm_token.check_token(user, token):
        UserProfile.objects.filter(user=user).update(email_confirmed=True)
        messages.success(request, "Thanks, your email is confirmed. You can make recipes now.")
    else:
        messages.error(
            request,
            "That link has expired or was already used. "
            + ("Use Send the link again at the top of the page." if request.user.is_authenticated
               else "Log in and ask for a new one."),
        )

    if request.user.is_authenticated:
        return redirect("dashboard")
    return redirect("login")


@login_required
@require_POST
def resend_confirmation_view(request):
    """The Send the link again button. Allowed once a minute."""

    back = request.POST.get("next", "")
    if not back or not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}):
        back = reverse("dashboard")

    if not needs_email_confirmation(request.user):
        messages.info(request, "Your email is already confirmed.")
        return redirect(back)

    last_sent = request.session.get("confirmation_sent_at") or 0
    wait = int(RESEND_WAIT_SECONDS - (time.time() - last_sent))
    if wait > 0:
        messages.info(request, f"We've just sent one. Check your inbox and spam folder, or try again in {wait} seconds.")
        return redirect(back)

    if send_confirmation_email(request, request.user):
        request.session["confirmation_sent_at"] = time.time()
        messages.success(request, f"Sent. Check {request.user.email} for the link (and your spam folder).")
    else:
        messages.error(request, "We couldn't send the email just now. Please try again in a few minutes.")
    return redirect(back)


@login_required
def download_my_data_view(request):
    """A JSON file of everything CulinaAI stores about the user."""

    data = export_user_data_json(request.user)
    filename = f"culinaai-data-{request.user.username}-{timezone.localdate():%Y-%m-%d}.json"
    response = HttpResponse(data, content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def delete_account_view(request):
    """Asks for the password, then deletes the account and everything in it."""

    error = ""
    if request.method == "POST":
        if request.user.check_password(request.POST.get("password", "")):
            user = request.user
            logout(request)
            delete_account(user)
            messages.success(request, "Your account and everything in it has been deleted.")
            return redirect("home")
        error = "That password isn't right."

    counts = {
        "recipes": Recipe.objects.filter(user=request.user, is_saved=True).count(),
        "shared": Recipe.objects.filter(user=request.user, is_saved=True, is_public=True).count(),
        "history": request.user.recipe_history.count(),
        "pantry": request.user.pantry_items.count(),
    }
    return render(request, "accounts/delete_account.html", {"error": error, "counts": counts})


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
    messages.success(request, "You're logged out. See you next time.")
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
                    "Password changed. Use the new one next time you log in.",
                )

                return redirect("profile_summary")

            messages.error(
                request,
                "Your password wasn't changed. Check the form below.",
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

            old_email = request.user.email

            if account_form.is_valid() and profile_form.is_valid():
                user = account_form.save()
                profile_form.save()

                if user.email.lower() != (old_email or "").lower() and not (user.is_staff or user.is_superuser):
                    # A new address has to be confirmed again before the AI features work.
                    mark_unconfirmed(user)
                    if needs_email_confirmation(user) and send_confirmation_email(request, user):
                        request.session["confirmation_sent_at"] = time.time()
                        messages.success(
                            request,
                            f"Saved your details. We've sent a link to {user.email} to confirm the new address.",
                        )
                    else:
                        messages.success(request, "Saved your details.")
                    return redirect("profile_summary")

                messages.success(
                    request,
                    "Saved your details.",
                )

                return redirect("profile_summary")

            messages.error(
                request,
                "Your details weren't saved. Check the form below.",
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
        "email_unconfirmed": needs_email_confirmation(request.user),
    }

    return render(request, "accounts/profile_summary.html", context)