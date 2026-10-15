"""
Daily limits on the AI features, so one account (or a bot) can't run up the
OpenAI bill.

Two allowances, both reset at midnight UK time:
- "recipe": new recipes, changes, versions and fridge scans
  (AI_DAILY_RECIPE_LIMIT, 20 by default). Each can make several AI calls and an image.
- "question": cooking assistant questions (AI_DAILY_QUESTION_LIMIT, 50 by default).

Staff accounts have no limit. People who signed up and haven't confirmed their
email can't use the AI features until they do.

Use in a view, just before the AI is called:

    blocked = use_ai(request.user, "recipe", "generate")
    if blocked:
        messages.error(request, blocked)
        return redirect(...)
"""

from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from accounts.confirmation import needs_email_confirmation

from .models import AIUsage

UK = ZoneInfo("Europe/London")


def is_demo(user):
    from accounts.models import UserProfile

    return UserProfile.objects.filter(user=user, is_demo=True).exists()


def daily_limit(kind, demo=False):
    if demo:
        return settings.DEMO_DAILY_QUESTION_LIMIT if kind == AIUsage.KIND_QUESTION else settings.DEMO_DAILY_RECIPE_LIMIT
    if kind == AIUsage.KIND_QUESTION:
        return settings.AI_DAILY_QUESTION_LIMIT
    return settings.AI_DAILY_RECIPE_LIMIT


def start_of_today():
    """Midnight today, UK time."""

    today = timezone.now().astimezone(UK).date()
    return datetime.combine(today, time.min, tzinfo=UK)


def is_unlimited(user):
    return user.is_staff or user.is_superuser


def used_today(user, kind):
    return AIUsage.objects.filter(user=user, kind=kind, created_at__gte=start_of_today()).count()


def allowance(user, kind):
    """What the page shows: the limit, how many are used and left today, and whether the user has no limit."""

    demo = is_demo(user)
    limit = daily_limit(kind, demo)
    if is_unlimited(user):
        return {"unlimited": True, "limit": limit, "used": 0, "left": limit, "demo": False}
    used = used_today(user, kind)
    return {"unlimited": False, "limit": limit, "used": used, "left": max(limit - used, 0), "demo": demo}


def blocked_reason(user, kind):
    """Why this user can't use the AI right now, in words for the page, or None if they can."""

    if needs_email_confirmation(user):
        return (
            f"Confirm your email first. We sent a link to {user.email}. "
            "Open it, then try again. You can send it again from the bar at the top of the page."
        )
    if is_unlimited(user):
        return None

    demo = is_demo(user)
    limit = daily_limit(kind, demo)
    if demo and used_today(user, kind) >= limit:
        return (
            "The demo shows recipes that are already made, so it doesn't use the AI. "
            "Create a free account to make your own recipes."
        )
    if used_today(user, kind) >= limit:
        if kind == AIUsage.KIND_QUESTION:
            return (
                f"You've asked {limit} questions today, which is the daily limit. "
                "You can ask more after midnight (UK time)."
            )
        return (
            f"You've used all {limit} of today's AI recipes and changes. "
            "You can make more after midnight (UK time). Your saved recipes still work as normal."
        )
    return None


def use_ai(user, kind, action):
    """
    Checks the user may use the AI and, if so, counts this use. Returns None when
    they can go ahead, or the reason they can't.

    The use is counted before the AI is called, because the call costs money
    even if it fails.
    """

    reason = blocked_reason(user, kind)
    if reason:
        return reason
    AIUsage.objects.create(user=user, kind=kind, action=action)
    return None
