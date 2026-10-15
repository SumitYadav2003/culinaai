"""
The Sunday email, for people who turn it on: what in their pantry goes off in
the coming week, anything already past its date, and next week's meal plan with
a link to its shopping list. Nothing is sent when there's nothing to say.

It is sent by send_weekly_emails(), which the scheduled job calls once a week
(see accounts/task_views.py and .github/workflows/weekly-email.yml). Each
person gets at most one in 6 days, so a job that runs twice doesn't send twice.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.urls import reverse
from django.utils import timezone

from accounts.email_service import build_branded_html, send_email
from accounts.models import UserProfile

from .meal_plan_service import long_day, sort_entries, week_entries, week_label, week_start_for
from .use_soon_service import going_off, out_of_date

logger = logging.getLogger(__name__)

UNSUBSCRIBE_SALT = "culinaai.weekly-email.off"
MIN_DAYS_BETWEEN = 6


def unsubscribe_token(user):
    return signing.dumps({"u": user.pk}, salt=UNSUBSCRIBE_SALT)


def user_from_unsubscribe_token(token):
    try:
        data = signing.loads(token, salt=UNSUBSCRIBE_SALT)
    except signing.BadSignature:
        return None
    return get_user_model().objects.filter(pk=data.get("u")).first()


def build_weekly_email(user, base_url, today=None):
    """(subject, plain text, html, turn-off link) for this user, or None when there's nothing worth sending."""

    today = today or timezone.localdate()
    soon = going_off(user, days=7)
    old = out_of_date(user)

    # "Next week" is the week starting on the coming Monday (tomorrow, when sent on a Sunday).
    next_monday = week_start_for(today) + timedelta(days=7)
    planned = sort_entries(week_entries(user, next_monday))

    if not soon and not old and not planned:
        return None

    name = user.first_name or user.username
    lines = []
    paragraphs = []

    if soon:
        item_lines = [f"{entry['name']}: {entry['when']}" for entry in soon]
        lines += ["Going off this week:", *[f"- {line}" for line in item_lines], ""]
        paragraphs.append("Going off this week: " + "; ".join(item_lines) + ".")
    if old:
        names = ", ".join(item.ingredient_name for item in old[:8])
        more = f" and {len(old) - 8} more" if len(old) > 8 else ""
        lines += [f"Already past their date: {names}{more}. Check them before you use them.", ""]
        paragraphs.append(f"Already past their date: {names}{more}. Check them before you use them.")
    if planned:
        meal_lines = [f"{long_day(e.date, today)[:1].upper() + long_day(e.date, today)[1:]}, "
                      f"{e.get_meal_display().lower()}: {e.recipe.title}" for e in planned]
        shopping = f"{base_url}{reverse('shopping_list')}?week={next_monday.isoformat()}"
        lines += [f"Planned for next week ({week_label(next_monday)}):", *[f"- {line}" for line in meal_lines],
                  f"Your shopping list: {shopping}", ""]
        paragraphs.append(f"Planned for next week ({week_label(next_monday)}): " + "; ".join(meal_lines) + ".")
    else:
        lines += [f"Nothing is planned for next week yet: {base_url}{reverse('meal_plan')}", ""]

    button_url = (
        f"{base_url}{reverse('shopping_list')}?week={next_monday.isoformat()}" if planned
        else f"{base_url}{reverse('dashboard')}"
    )
    off_url = f"{base_url}{reverse('weekly_email_off', args=[unsubscribe_token(user)])}"
    footer = f"You get this because you turned on the Sunday email. Turn it off: {off_url}"

    plain = "\n".join([f"Hi {name},", "", *lines, footer, "", "CulinaAI"])
    html = build_branded_html(
        f"Your week ahead, {name}",
        paragraphs,
        "Open my shopping list" if planned else "Open CulinaAI",
        button_url,
        small_print="You get this because you turned on the Sunday email.",
        small_link=("Turn it off", off_url),
    )
    return "Your week ahead with CulinaAI", plain, html, off_url


def due_profiles(today):
    """People who asked for the email and haven't had one in the last 6 days."""

    profiles = UserProfile.objects.filter(
        weekly_email=True,
        is_demo=False,
        email_confirmed=True,
        user__is_active=True,
    ).exclude(user__email="").select_related("user")
    cutoff = today - timedelta(days=MIN_DAYS_BETWEEN)
    return [p for p in profiles if p.weekly_email_sent_on is None or p.weekly_email_sent_on <= cutoff]


def send_weekly_emails(base_url=None, today=None):
    """Sends the Sunday email to everyone it's due for. Returns counts for the log."""

    base_url = (base_url or settings.SITE_URL).rstrip("/")
    today = today or timezone.localdate()
    counts = {"sent": 0, "nothing_to_say": 0, "failed": 0}

    for profile in due_profiles(today):
        user = profile.user
        try:
            email = build_weekly_email(user, base_url, today)
        except Exception:
            logger.exception("Couldn't build the weekly email for user %s", user.pk)
            counts["failed"] += 1
            continue
        if email is None:
            counts["nothing_to_say"] += 1
            continue
        subject, plain, html, off_url = email
        # Lets mail apps show their own "Unsubscribe" button.
        headers = {"List-Unsubscribe": f"<{off_url}>"}
        if send_email(user.email, subject, plain, html, "weekly", headers=headers):
            UserProfile.objects.filter(pk=profile.pk).update(weekly_email_sent_on=today)
            counts["sent"] += 1
        else:
            counts["failed"] += 1
    return counts
