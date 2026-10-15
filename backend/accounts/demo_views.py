"""
"Try the demo", ending the demo, and the Sunday email on/off switch.
"""

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from recipes.demo_service import create_demo_user, delete_old_demo_users, demo_user_count, is_demo_user
from recipes.weekly_email_service import user_from_unsubscribe_token

from .models import UserProfile

logger = logging.getLogger(__name__)


def client_ip(request):
    # On Render the visitor's address is the first one in X-Forwarded-For.
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")


@require_POST
def start_demo_view(request):
    """Makes a fresh demo account and logs the visitor into it."""

    if request.user.is_authenticated and not is_demo_user(request.user):
        return redirect("dashboard")

    # A few demos an hour from one address is plenty; this stops a script making thousands.
    key = f"demo-starts:{client_ip(request)}"
    starts = cache.get(key, 0)
    if starts >= settings.DEMO_STARTS_PER_HOUR:
        messages.error(request, "You've started a lot of demos in the last hour. Please try again later, or create a free account.")
        return redirect("home")

    delete_old_demo_users()
    if demo_user_count() >= settings.DEMO_MAX_ACCOUNTS:
        messages.error(request, "The demo is busy right now. Please try again in a while, or create a free account.")
        return redirect("home")

    if request.user.is_authenticated:
        end_demo(request)

    try:
        user = create_demo_user()
    except Exception:
        logger.exception("Couldn't make a demo account")
        messages.error(request, "The demo couldn't start just now. Please try again.")
        return redirect("home")

    cache.set(key, starts + 1, 60 * 60)
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    messages.success(
        request,
        "Welcome to the demo. Look around: open a recipe, the meal plan or the shopping list. "
        f"Nothing you do here is kept after {settings.DEMO_HOURS} hours.",
    )
    return redirect("dashboard")


def end_demo(request):
    """Logs out of a demo account and deletes it."""

    user = request.user
    logout(request)
    if user.is_authenticated and UserProfile.objects.filter(user=user, is_demo=True).exists():
        user.delete()


@require_POST
def end_demo_view(request):
    """The "Create a free account" button in the demo bar."""

    if is_demo_user(request.user):
        end_demo(request)
    return redirect("signup")


@login_required
@require_POST
def weekly_email_toggle_view(request):
    back = request.POST.get("next", "")
    if not back or not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}):
        back = "profile_summary"

    if is_demo_user(request.user):
        messages.info(request, "Demo accounts can't get emails. Create a free account to turn this on.")
        return redirect(back)

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    profile.weekly_email = request.POST.get("on") == "1"
    profile.save(update_fields=["weekly_email"])
    if profile.weekly_email:
        messages.success(request, f"Done. We'll email {request.user.email} on Sunday evenings when there's something to tell you.")
    else:
        messages.info(request, "Turned off the Sunday email.")
    return redirect(back)


def weekly_email_off_view(request, token):
    """The "Turn it off" link in the email. Works without logging in; asks to confirm with a button."""

    user = user_from_unsubscribe_token(token)
    if user is None:
        return render(request, "accounts/weekly_email_off.html", {"invalid": True}, status=400)

    if request.method == "POST":
        UserProfile.objects.filter(user=user).update(weekly_email=False)
        return render(request, "accounts/weekly_email_off.html", {"done": True, "email": user.email})

    return render(request, "accounts/weekly_email_off.html", {"email": user.email})
