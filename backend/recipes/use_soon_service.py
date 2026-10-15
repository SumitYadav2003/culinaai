"""
"Use it before it goes off": pantry items whose use-by date is close, and
saved recipes that would use them up. Used by the dashboard and the Sunday
email. No AI is used.
"""

from datetime import timedelta
from urllib.parse import urlencode

from django.urls import reverse
from django.utils import timezone

from .meal_plan_service import structured_ingredients
from .models import PantryItem, Recipe
from .shopping_service import extract_ingredient_items, normalise_for_matching

SOON_DAYS = 3


def when_label(days_left):
    if days_left < 0:
        return "past its date" if days_left == -1 else f"{-days_left} days past its date"
    if days_left == 0:
        return "use today"
    if days_left == 1:
        return "use by tomorrow"
    return f"use within {days_left} days"


def going_off(user, days=SOON_DAYS):
    """Available pantry items with a use-by date from today to `days` from now, soonest first."""

    today = timezone.localdate()
    items = PantryItem.objects.filter(
        user=user,
        is_available=True,
        expiry_date__gte=today,
        expiry_date__lte=today + timedelta(days=days),
    ).order_by("expiry_date", "ingredient_name")
    return [
        {"item": item, "name": item.ingredient_name, "days_left": (item.expiry_date - today).days,
         "when": when_label((item.expiry_date - today).days)}
        for item in items
    ]


def out_of_date(user):
    today = timezone.localdate()
    return list(
        PantryItem.objects.filter(user=user, is_available=True, expiry_date__lt=today).order_by("expiry_date")
    )


def recipe_ingredient_keys(recipe):
    structured = structured_ingredients(recipe)
    names = [item["name"] for item in structured] or extract_ingredient_items(recipe.ingredients_text)
    return {normalise_for_matching(name) for name in names} - {""}


def matches(pantry_key, ingredient_keys):
    """Same rule as the shopping list: all the words of one name are in the other."""

    pantry_tokens = set(pantry_key.split())
    for key in ingredient_keys:
        tokens = set(key.split())
        if pantry_tokens and tokens and (pantry_tokens <= tokens or tokens <= pantry_tokens):
            return True
    return False


def recipes_using(user, soon, limit=3):
    """Saved recipes that use the most of the items going off: [{"recipe", "uses": [names]}]."""

    if not soon:
        return []
    soon_keys = [(entry["name"], normalise_for_matching(entry["name"])) for entry in soon]
    found = []
    for recipe in Recipe.objects.filter(user=user, is_saved=True).order_by("-created_at")[:200]:
        keys = recipe_ingredient_keys(recipe)
        uses = [name for name, key in soon_keys if key and matches(key, keys)]
        if uses:
            found.append({"recipe": recipe, "uses": uses})
    found.sort(key=lambda entry: -len(entry["uses"]))
    return found[:limit]


def new_recipe_url(soon):
    """The New recipe form with the items going off already filled in."""

    names = ", ".join(entry["name"] for entry in soon)
    return f"{reverse('generate_recipe')}?{urlencode({'use_up': names})}"


def use_soon_context(user):
    """Everything the dashboard card needs."""

    soon = going_off(user)
    old = out_of_date(user)
    return {
        "soon": soon,
        "out_of_date": old,
        "suggestions": recipes_using(user, soon),
        "new_recipe_url": new_recipe_url(soon) if soon else "",
        "has_dates": PantryItem.objects.filter(user=user, expiry_date__isnull=False).exists(),
        "has_pantry": PantryItem.objects.filter(user=user).exists(),
    }
