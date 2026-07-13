"""
Analytics service for CulinaAI.

This service prepares user-specific analytics for:
- total recipes generated
- favourite cuisine
- average cooking time
- favourite ingredients
- recent searches
- weekly/monthly recipe activity
- pie chart for cuisine
- bar chart for ingredients
- line chart for usage over time
"""

import json
import re
from collections import Counter, defaultdict
from datetime import timedelta

from django.utils import timezone

from .models import FavouriteRecipe, Recipe, RecipeHistory


def clean_text(value):
    """
    Safely converts text into a clean lowercase string.
    """

    if not value:
        return ""

    return str(value).strip().lower()


def split_ingredients(ingredients_text):
    """
    Splits recipe ingredient text into clean ingredient names.
    """

    if not ingredients_text:
        return []

    text = str(ingredients_text)

    separators = ["\n", ",", ";", "|"]

    for separator in separators:
        text = text.replace(separator, ",")

    ingredients = []

    for item in text.split(","):
        clean_item = item.strip()

        if not clean_item:
            continue

        clean_item = re.sub(r"^[\-\*\•]\s*", "", clean_item)
        clean_item = re.sub(r"^\d+[\.\)]\s*", "", clean_item)
        clean_item = clean_item.strip()

        if clean_item:
            ingredients.append(clean_item)

    return ingredients


def get_top_counter_label(counter, default_label="Not enough data"):
    """
    Returns the most common label from a Counter.
    """

    if not counter:
        return default_label

    most_common = counter.most_common(1)

    if not most_common:
        return default_label

    return most_common[0][0]


def build_chart_payload(labels, values):
    """
    Converts chart labels and values into JSON strings for templates.
    """

    return {
        "labels": json.dumps(labels),
        "values": json.dumps(values),
    }


def build_usage_activity(history_items, days=30):
    """
    Builds daily usage activity for the last selected number of days.
    """

    today = timezone.localdate()
    start_date = today - timedelta(days=days - 1)

    activity_map = defaultdict(int)

    for history_item in history_items:
        created_date = timezone.localtime(history_item.created_at).date()

        if start_date <= created_date <= today:
            activity_map[created_date] += 1

    labels = []
    values = []

    for day_offset in range(days):
        current_date = start_date + timedelta(days=day_offset)

        labels.append(current_date.strftime("%d %b"))
        values.append(activity_map[current_date])

    return build_chart_payload(labels, values)


def build_monthly_activity(history_items, months=6):
    """
    Builds monthly usage activity for the last selected number of months.
    """

    today = timezone.localdate()

    month_keys = []

    for offset in range(months - 1, -1, -1):
        month = today.month - offset
        year = today.year

        while month <= 0:
            month += 12
            year -= 1

        month_keys.append((year, month))

    activity_map = defaultdict(int)

    for history_item in history_items:
        created_date = timezone.localtime(history_item.created_at).date()
        key = (created_date.year, created_date.month)

        if key in month_keys:
            activity_map[key] += 1

    labels = []
    values = []

    for year, month in month_keys:
        labels.append(f"{month:02d}/{year}")
        values.append(activity_map[(year, month)])

    return build_chart_payload(labels, values)


def build_user_analytics_context(user):
    """
    Main analytics function for one logged-in user.
    """

    history_items = list(
        RecipeHistory.objects.filter(
            user=user,
        ).order_by("-created_at")
    )

    saved_recipes = list(
        Recipe.objects.filter(
            user=user,
            is_saved=True,
        )
        .select_related("cuisine", "meal_type")
        .order_by("-created_at")
    )

    favourite_recipes = list(
        FavouriteRecipe.objects.filter(
            user=user,
            recipe__is_saved=True,
        )
        .select_related(
            "recipe",
            "recipe__cuisine",
            "recipe__meal_type",
        )
        .order_by("-created_at")
    )

    total_recipes_generated = len(history_items)
    total_saved_recipes = len(saved_recipes)
    total_favourite_recipes = len(favourite_recipes)

    cuisine_counter = Counter()
    ingredient_counter = Counter()
    cooking_times = []

    for history_item in history_items:
        cuisine_name = history_item.cuisine_name

        if cuisine_name and cuisine_name != "Any cuisine":
            cuisine_counter[cuisine_name] += 1

        if history_item.cooking_time_minutes:
            cooking_times.append(history_item.cooking_time_minutes)

        for ingredient in split_ingredients(history_item.ingredients_text):
            ingredient_counter[ingredient.title()] += 1

    for recipe in saved_recipes:
        if recipe.cuisine:
            cuisine_counter[recipe.cuisine.name] += 1

        if recipe.cooking_time_minutes:
            cooking_times.append(recipe.cooking_time_minutes)

        for ingredient in split_ingredients(recipe.ingredients_text):
            ingredient_counter[ingredient.title()] += 1

    for favourite in favourite_recipes:
        recipe = favourite.recipe

        if recipe.cuisine:
            cuisine_counter[recipe.cuisine.name] += 2

        for ingredient in split_ingredients(recipe.ingredients_text):
            ingredient_counter[ingredient.title()] += 2

    favourite_cuisine = get_top_counter_label(cuisine_counter)

    if cooking_times:
        average_cooking_time = round(sum(cooking_times) / len(cooking_times))
    else:
        average_cooking_time = 0

    favourite_ingredients = [
        {
            "name": ingredient,
            "count": count,
        }
        for ingredient, count in ingredient_counter.most_common(8)
    ]

    recent_searches = history_items[:6]

    top_cuisines = cuisine_counter.most_common(6)
    cuisine_chart = build_chart_payload(
        labels=[item[0] for item in top_cuisines],
        values=[item[1] for item in top_cuisines],
    )

    top_ingredients = ingredient_counter.most_common(8)
    ingredient_chart = build_chart_payload(
        labels=[item[0] for item in top_ingredients],
        values=[item[1] for item in top_ingredients],
    )

    daily_activity_chart = build_usage_activity(
        history_items=history_items,
        days=30,
    )

    monthly_activity_chart = build_monthly_activity(
        history_items=history_items,
        months=6,
    )

    if total_recipes_generated >= 10:
        activity_label = "Highly Active"
        activity_message = "You are actively using CulinaAI for recipe discovery."
    elif total_recipes_generated >= 3:
        activity_label = "Growing Usage"
        activity_message = "Your recipe history is growing. More usage will improve recommendations."
    else:
        activity_label = "New User"
        activity_message = "Generate more recipes to unlock stronger personal analytics."

    context = {
        "total_recipes_generated": total_recipes_generated,
        "total_saved_recipes": total_saved_recipes,
        "total_favourite_recipes": total_favourite_recipes,
        "favourite_cuisine": favourite_cuisine,
        "average_cooking_time": average_cooking_time,
        "favourite_ingredients": favourite_ingredients,
        "recent_searches": recent_searches,
        "activity_label": activity_label,
        "activity_message": activity_message,
        "cuisine_chart_labels": cuisine_chart["labels"],
        "cuisine_chart_values": cuisine_chart["values"],
        "ingredient_chart_labels": ingredient_chart["labels"],
        "ingredient_chart_values": ingredient_chart["values"],
        "daily_activity_labels": daily_activity_chart["labels"],
        "daily_activity_values": daily_activity_chart["values"],
        "monthly_activity_labels": monthly_activity_chart["labels"],
        "monthly_activity_values": monthly_activity_chart["values"],
        "has_analytics_data": total_recipes_generated > 0 or total_saved_recipes > 0,
    }

    return context