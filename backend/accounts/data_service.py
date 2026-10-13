"""
"Download my data" and "Delete my account".

Under UK GDPR people can ask for a copy of their data and for it to be erased.
These two functions do that without anyone having to email the site owner.
"""

import json
import logging

from django.core.files.storage import default_storage
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, transaction
from django.utils import timezone

from recipes.models import (
    AIUsage,
    CookingChatSession,
    CookingSession,
    CookingSettings,
    FavouriteRecipe,
    FridgeScan,
    PantryItem,
    Recipe,
    RecipeFeedback,
    RecipeHistory,
    RecipeRating,
)

from .models import UserProfile


logger = logging.getLogger(__name__)

# Fields that only make sense inside the database, not to the person reading the file.
SKIP_FIELDS = {"user", "session_key"}


def file_url(field_file):
    if not field_file:
        return ""
    try:
        return field_file.url
    except Exception:
        return field_file.name


def as_dict(obj):
    """One database row as plain values: dates as text, files as links, links to other rows as their name."""

    data = {}
    for field in obj._meta.concrete_fields:
        if field.name in SKIP_FIELDS:
            continue
        if isinstance(field, models.FileField):
            data[field.name] = file_url(getattr(obj, field.name))
        elif isinstance(field, models.ForeignKey):
            related = getattr(obj, field.name)
            data[field.name] = str(related) if related is not None else None
        else:
            data[field.name] = field.value_from_object(obj)
    for field in obj._meta.many_to_many:
        data[field.name] = [str(item) for item in getattr(obj, field.name).all()]
    return data


def export_user_data(user):
    """Everything CulinaAI stores about this user, as a dict ready for JSON."""

    profile = UserProfile.objects.filter(user=user).first()

    chats = []
    for chat in CookingChatSession.objects.filter(user=user).prefetch_related("messages"):
        entry = as_dict(chat)
        entry["messages"] = [as_dict(message) for message in chat.messages.all()]
        chats.append(entry)

    cooking_sessions = []
    for session in CookingSession.objects.filter(user=user).prefetch_related("steps"):
        entry = as_dict(session)
        entry["steps"] = [as_dict(step) for step in session.steps.all()]
        cooking_sessions.append(entry)

    def rows(model, **extra):
        return [as_dict(row) for row in model.objects.filter(user=user, **extra)]

    return {
        "exported_at": timezone.now(),
        "about_this_file": (
            "Everything CulinaAI stores about your account. Dates are in UTC. "
            "Image links work for as long as the image is kept."
        ),
        "account": {
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "date_joined": user.date_joined,
            "last_login": user.last_login,
            "email_confirmed": profile.email_confirmed if profile else None,
            "bio": profile.bio if profile else "",
            "profile_image": file_url(profile.profile_image) if profile else "",
        },
        "recipes": rows(Recipe),
        "favourites": rows(FavouriteRecipe),
        "ratings_given": rows(RecipeRating),
        "feedback_given": rows(RecipeFeedback),
        "recipe_history": rows(RecipeHistory),
        "pantry": rows(PantryItem),
        "fridge_scans": rows(FridgeScan),
        "cooking_assistant_chats": chats,
        "cooking_settings": rows(CookingSettings),
        "cooking_sessions": cooking_sessions,
        "ai_use": rows(AIUsage),
    }


def export_user_data_json(user):
    return json.dumps(export_user_data(user), cls=DjangoJSONEncoder, indent=2, ensure_ascii=False)


def user_file_names(user):
    """Every image file that belongs to this user and nobody else."""

    names = set()
    names.update(Recipe.objects.filter(user=user).exclude(generated_image="").values_list("generated_image", flat=True))
    names.update(
        RecipeHistory.objects.filter(user=user).exclude(generated_image="").values_list("generated_image", flat=True)
    )
    names.update(FridgeScan.objects.filter(user=user).exclude(image="").values_list("image", flat=True))
    names.update(UserProfile.objects.filter(user=user).exclude(profile_image="").values_list("profile_image", flat=True))
    names.discard(None)

    # Never delete a file another account's recipe still points at.
    shared = set(
        Recipe.objects.exclude(user=user).filter(generated_image__in=names).values_list("generated_image", flat=True)
    ) | set(
        RecipeHistory.objects.exclude(user=user)
        .filter(generated_image__in=names)
        .values_list("generated_image", flat=True)
    )
    return names - shared


def delete_files(names):
    for name in names:
        try:
            default_storage.delete(name)
        except Exception:
            logger.exception("Couldn't delete the file %s after an account was deleted", name)


def delete_account(user):
    """
    Deletes the user and everything that belongs to them: recipes (and any that
    were shared), favourites, ratings, history, pantry, fridge scans, cooking
    sessions and chats, then their images.
    """

    names = user_file_names(user)
    with transaction.atomic():
        user.delete()
        # Only delete the files once the database part has really gone through.
        transaction.on_commit(lambda: delete_files(names))
