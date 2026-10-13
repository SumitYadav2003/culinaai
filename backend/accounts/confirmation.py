"""
Email confirmation: who still has to confirm, and the rules for sending the link.
"""

from django.conf import settings

from .models import UserProfile


def needs_email_confirmation(user):
    """True when this user has to confirm their email before using the AI features."""

    if not settings.EMAIL_CONFIRMATION_REQUIRED or not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return False
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return not profile.email_confirmed


def mark_unconfirmed(user):
    """Used after signing up and after changing the email address."""

    if not settings.EMAIL_CONFIRMATION_REQUIRED:
        return
    UserProfile.objects.update_or_create(user=user, defaults={"email_confirmed": False})
    # Keep the cached profile in step, so the token made next uses the new value.
    if hasattr(user, "profile"):
        user.profile.email_confirmed = False
