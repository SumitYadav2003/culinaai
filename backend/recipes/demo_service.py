"""
"Try the demo": a temporary account, filled with real-looking data, so a
visitor can see every page without signing up. No AI is called to make it.

- Each visitor gets their own account (so two visitors never see each other's
  changes). It is deleted when they log out, or after DEMO_HOURS.
- Demo accounts can't use the AI features (unless DEMO_DAILY_*_LIMIT says
  otherwise), send emails, share recipes publicly, rate other people's recipes
  or change their details. See ai_limits.py and demo_guard.
"""

import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from accounts.models import UserProfile

from .demo_data import DEMO_PANTRY, DEMO_PLAN, DEMO_RECIPES, NO_CLASSIC
from .meal_plan_service import week_start_for
from .models import (
    Cuisine,
    DietPreference,
    FavouriteRecipe,
    MealPlanEntry,
    MealType,
    PantryItem,
    Recipe,
    RecipeHistory,
)

logger = logging.getLogger(__name__)


def is_demo_user(user):
    if not getattr(user, "is_authenticated", False):
        return False
    profile = UserProfile.objects.filter(user=user).only("is_demo").first()
    return bool(profile and profile.is_demo)


def demo_preferences(recipe):
    """The settings the demo recipe would have been made with, for the checks and the "What you asked for" panel."""

    return {
        "ingredients": recipe["ingredients_text"],
        "cuisine": recipe["cuisine"],
        "meal_type": recipe["meal_type"],
        "diet_preferences": recipe["diets"],
        "other_diet_preference": "",
        "allergies": "None provided",
        "cooking_time_minutes": recipe["minutes"],
        "servings": recipe["servings"],
        "difficulty": recipe["difficulty"],
        "spice_level": "Mild",
        "budget_level": "Moderate Budget",
        "nutrition_goal": "Balanced",
        "meal_style": "No preference",
        "cooking_equipment": ["Stove / Hob", "Oven"],
        "other_kitchen_equipment": "",
        "utensils": [],
        "other_utensils": "",
        "additional_notes": "None provided",
    }


def worked_out(recipe, preferences):
    """Nutrition, cost, carbon and the quality checks, from the same code real recipes use."""

    from .cuisine_service import recipe_cuisine_check
    from .insight_service import build_insights
    from .recipe_quality_engine import validate_recipe_output

    structure = {
        "servings": recipe["servings"],
        "ingredients": recipe["ingredients"],
        "ai_kcal_per_serving": None,
        "classic": NO_CLASSIC,
    }
    try:
        insights = build_insights({"structure": structure, "warnings": []}, preferences, recipe["text"])
    except Exception:
        logger.exception("Couldn't work out the demo recipe %s", recipe["key"])
        insights = {"available": False}
    try:
        cuisine = recipe_cuisine_check(preferences, insights, recipe["text"])
        if cuisine:
            insights = dict(insights, cuisine=cuisine)
    except Exception:
        logger.exception("Couldn't run the cuisine check for the demo recipe %s", recipe["key"])
    try:
        report = validate_recipe_output(preferences=preferences, recipe_text=recipe["text"], insights=insights)
    except Exception:
        logger.exception("Couldn't check the demo recipe %s", recipe["key"])
        report = {}
    return insights, report


@transaction.atomic
def create_demo_user():
    """Makes a new demo account with recipes, favourites, history, a pantry and this week's plan."""

    User = get_user_model()
    username = f"demo-{secrets.token_hex(4)}"
    while User.objects.filter(username=username).exists():
        username = f"demo-{secrets.token_hex(4)}"

    user = User.objects.create_user(username=username, email=f"{username}@demo.invalid", first_name="Demo")
    user.set_unusable_password()
    user.save(update_fields=["password"])
    UserProfile.objects.update_or_create(user=user, defaults={"is_demo": True, "email_confirmed": True})

    today = timezone.localdate()
    by_key = {}
    for position, data in enumerate(DEMO_RECIPES):
        preferences = demo_preferences(data)
        insights, report = worked_out(data, preferences)
        recipe = Recipe.objects.create(
            user=user,
            title=data["title"],
            cuisine=Cuisine.objects.filter(name__iexact=data["cuisine"]).first(),
            meal_type=MealType.objects.filter(name__iexact=data["meal_type"]).first(),
            ingredients_text=data["ingredients_text"],
            instructions_text=data["text"],
            ai_response=data["text"],
            cooking_time_minutes=data["minutes"],
            difficulty=data["difficulty"],
            allergy_notes="",
            is_ai_generated=True,
            is_saved=True,
            quality_score=report.get("score"),
            validation_status=report.get("status", ""),
            validation_risk_level=report.get("risk_level", ""),
            validation_badge=report.get("badge", ""),
            validation_attempts=1 if report else 0,
            validation_report=report,
            insights=insights,
        )
        recipe.diet_preferences.set(DietPreference.objects.filter(name__in=data["diets"]))
        # Spread the "saved" dates over the last week, newest first.
        Recipe.objects.filter(id=recipe.id).update(created_at=timezone.now() - timedelta(days=position * 2, hours=3))
        RecipeHistory.objects.create(
            user=user,
            saved_recipe=recipe,
            title=data["title"],
            recipe_text=data["text"],
            ingredients_text=data["ingredients_text"],
            cuisine_name=data["cuisine"],
            meal_type_name=data["meal_type"],
            dietary_preferences=data["diets"],
            cooking_time_minutes=data["minutes"],
            servings=data["servings"],
            difficulty=data["difficulty"],
            quality_score=report.get("score"),
            validation_status=report.get("status", ""),
            validation_report=report,
            insights=insights,
        )
        if data["favourite"]:
            FavouriteRecipe.objects.create(user=user, recipe=recipe)
        by_key[data["key"]] = recipe

    for name, quantity, unit, category, days in DEMO_PANTRY:
        PantryItem.objects.create(
            user=user,
            ingredient_name=name,
            quantity=quantity,
            unit=unit,
            category=category,
            expiry_date=today + timedelta(days=days) if days is not None else None,
        )

    monday = week_start_for(today)
    for weekday, meal, key, servings in DEMO_PLAN:
        MealPlanEntry.objects.create(
            user=user, recipe=by_key[key], date=monday + timedelta(days=weekday), meal=meal, servings=servings,
        )

    return user


def delete_old_demo_users(hours=None):
    """Deletes demo accounts older than DEMO_HOURS. Returns how many went."""

    hours = hours if hours is not None else settings.DEMO_HOURS
    cutoff = timezone.now() - timedelta(hours=hours)
    old = get_user_model().objects.filter(profile__is_demo=True, date_joined__lt=cutoff)
    count = old.count()
    if count:
        old.delete()
    return count


def demo_user_count():
    return UserProfile.objects.filter(is_demo=True).count()


DEMO_NOT_ALLOWED = "That isn't available in the demo. Create a free account to use it."


def not_in_demo(message=DEMO_NOT_ALLOWED):
    """
    For views a demo account mustn't use (sending emails, sharing publicly,
    changing account details): shows a message and goes back instead.
    """

    from functools import wraps

    from django.contrib import messages
    from django.shortcuts import redirect
    from django.utils.http import url_has_allowed_host_and_scheme

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method == "POST" and is_demo_user(request.user):
                messages.info(request, message)
                back = request.META.get("HTTP_REFERER", "")
                if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}):
                    back = "dashboard"
                return redirect(back)
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
