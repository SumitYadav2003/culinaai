from collections import Counter
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta

from .models import FavouriteRecipe, PantryItem, Recipe, RecipeHistory


def normalise_text(value):
    """
    Converts text into a clean lowercase format for safer comparison.
    """

    if not value:
        return ""

    return str(value).strip().lower()


def split_ingredient_text(ingredient_text):
    """
    Converts stored ingredient text into a simple list of ingredient keywords.

    Example:
    'paneer, rice, tomato' -> ['paneer', 'rice', 'tomato']
    """

    if not ingredient_text:
        return []

    separators = [",", "\n", ";", "|"]

    clean_text = str(ingredient_text)

    for separator in separators:
        clean_text = clean_text.replace(separator, ",")

    ingredients = []

    for item in clean_text.split(","):
        clean_item = normalise_text(item)

        if clean_item:
            ingredients.append(clean_item)

    return ingredients


def get_available_pantry_items(user):
    """
    Returns pantry items that are available and not expired.

    Expired ingredients are not used for recipe recommendations.
    """

    today = timezone.localdate()

    return (
        PantryItem.objects.filter(
            user=user,
            is_available=True,
        )
        .filter(
            Q(expiry_date__isnull=True) | Q(expiry_date__gte=today)
        )
        .order_by("expiry_date", "ingredient_name")
    )


def get_expiring_soon_pantry_items(user):
    """
    Returns available pantry items expiring within 3 days.
    """

    today = timezone.localdate()
    soon_date = today + timedelta(days=3)

    return PantryItem.objects.filter(
        user=user,
        is_available=True,
        expiry_date__gte=today,
        expiry_date__lte=soon_date,
    ).order_by("expiry_date", "ingredient_name")


def build_user_preference_profile(user):
    """
    Builds a simple preference profile from:
    - saved recipes
    - favourite recipes
    - recipe history
    - pantry ingredients

    This is a lightweight ML-style profile using frequency-based scoring.
    """

    saved_recipes = (
        Recipe.objects.filter(
            user=user,
            is_saved=True,
        )
        .select_related("cuisine", "meal_type")
        .prefetch_related("diet_preferences")
        .order_by("-created_at")
    )

    favourite_recipes = (
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

    history_items = RecipeHistory.objects.filter(
        user=user,
    ).order_by("-created_at")[:30]

    available_pantry_items = get_available_pantry_items(user)
    expiring_soon_items = get_expiring_soon_pantry_items(user)

    cuisine_counter = Counter()
    meal_type_counter = Counter()
    difficulty_counter = Counter()
    ingredient_counter = Counter()

    for recipe in saved_recipes:
        if recipe.cuisine:
            cuisine_counter[recipe.cuisine.name] += 2

        if recipe.meal_type:
            meal_type_counter[recipe.meal_type.name] += 2

        if recipe.difficulty:
            difficulty_counter[recipe.difficulty] += 1

        for ingredient in split_ingredient_text(recipe.ingredients_text):
            ingredient_counter[ingredient] += 1

    for favourite in favourite_recipes:
        recipe = favourite.recipe

        if recipe.cuisine:
            cuisine_counter[recipe.cuisine.name] += 4

        if recipe.meal_type:
            meal_type_counter[recipe.meal_type.name] += 4

        if recipe.difficulty:
            difficulty_counter[recipe.difficulty] += 2

        for ingredient in split_ingredient_text(recipe.ingredients_text):
            ingredient_counter[ingredient] += 2

    for history_item in history_items:
        if history_item.cuisine_name:
            cuisine_counter[history_item.cuisine_name] += 1

        if history_item.meal_type_name:
            meal_type_counter[history_item.meal_type_name] += 1

        if history_item.difficulty:
            difficulty_counter[history_item.difficulty] += 1

        for ingredient in split_ingredient_text(history_item.ingredients_text):
            ingredient_counter[ingredient] += 1

    pantry_ingredients = [
        item.ingredient_name.strip()
        for item in available_pantry_items
        if item.ingredient_name.strip()
    ]

    expiring_soon_ingredients = [
        item.ingredient_name.strip()
        for item in expiring_soon_items
        if item.ingredient_name.strip()
    ]

    profile = {
        "preferred_cuisines": cuisine_counter,
        "preferred_meal_types": meal_type_counter,
        "preferred_difficulties": difficulty_counter,
        "frequent_ingredients": ingredient_counter,
        "pantry_ingredients": pantry_ingredients,
        "expiring_soon_ingredients": expiring_soon_ingredients,
        "saved_recipe_count": saved_recipes.count(),
        "favourite_recipe_count": favourite_recipes.count(),
        "history_count": RecipeHistory.objects.filter(user=user).count(),
    }

    return profile


def get_top_counter_value(counter, default_value):
    """
    Returns the most common value from a Counter.
    """

    if not counter:
        return default_value

    most_common = counter.most_common(1)

    if not most_common:
        return default_value

    return most_common[0][0]


def build_pantry_based_recommendations(profile):
    """
    Builds recommendation ideas from available pantry ingredients.
    """

    recommendations = []

    pantry_ingredients = profile.get("pantry_ingredients", [])
    expiring_soon_ingredients = profile.get("expiring_soon_ingredients", [])

    preferred_cuisine = get_top_counter_value(
        profile.get("preferred_cuisines"),
        "Personalised",
    )

    preferred_meal_type = get_top_counter_value(
        profile.get("preferred_meal_types"),
        "Meal",
    )

    preferred_difficulty = get_top_counter_value(
        profile.get("preferred_difficulties"),
        "easy",
    )

    if not pantry_ingredients:
        return recommendations

    # 1. Highest priority: expiring soon ingredients
    for index, ingredient in enumerate(expiring_soon_ingredients[:3]):
        supporting_ingredients = [
            item for item in pantry_ingredients if item != ingredient
        ][:3]

        ingredient_list = [ingredient] + supporting_ingredients

        recommendations.append(
            {
                "title": f"Use-First {ingredient.title()} {preferred_meal_type}",
                "reason": (
                    f"{ingredient.title()} is expiring soon, so CulinaAI recommends "
                    "using it first to reduce food waste."
                ),
                "ingredients": ", ".join(ingredient_list),
                "score": 95 - index,
                "badge": "Use First",
                "source": "Smart Pantry",
                "difficulty": preferred_difficulty,
                "query": ", ".join(ingredient_list),
            }
        )

    # 2. General pantry recommendation
    pantry_main_items = pantry_ingredients[:5]

    recommendations.append(
        {
            "title": f"{preferred_cuisine} Smart Pantry Recipe",
            "reason": (
                "This recommendation is based on ingredients currently available "
                "in your Smart Pantry."
            ),
            "ingredients": ", ".join(pantry_main_items),
            "score": 84,
            "badge": "Pantry Match",
            "source": "Smart Pantry",
            "difficulty": preferred_difficulty,
            "query": ", ".join(pantry_main_items),
        }
    )

    # 3. Quick meal idea
    quick_items = pantry_ingredients[:4]

    recommendations.append(
        {
            "title": f"Quick {preferred_cuisine} Pantry Bowl",
            "reason": (
                "A quick recipe idea using your available pantry ingredients and "
                "your previous recipe preferences."
            ),
            "ingredients": ", ".join(quick_items),
            "score": 80,
            "badge": "Quick Idea",
            "source": "Preference Engine",
            "difficulty": preferred_difficulty,
            "query": ", ".join(quick_items),
        }
    )

    return recommendations


def build_saved_recipe_matches(user, profile):
    """
    Finds saved recipes that match the user's current pantry ingredients.
    """

    recommendations = []

    pantry_ingredients = [
        normalise_text(item)
        for item in profile.get("pantry_ingredients", [])
    ]

    if not pantry_ingredients:
        return recommendations

    saved_recipes = (
        Recipe.objects.filter(
            user=user,
            is_saved=True,
        )
        .select_related("cuisine", "meal_type")
        .order_by("-created_at")[:30]
    )

    favourite_recipe_ids = set(
        FavouriteRecipe.objects.filter(
            user=user,
            recipe__is_saved=True,
        ).values_list("recipe_id", flat=True)
    )

    for recipe in saved_recipes:
        recipe_ingredients = split_ingredient_text(recipe.ingredients_text)

        matched_ingredients = []

        for pantry_ingredient in pantry_ingredients:
            for recipe_ingredient in recipe_ingredients:
                if pantry_ingredient in recipe_ingredient or recipe_ingredient in pantry_ingredient:
                    matched_ingredients.append(pantry_ingredient)
                    break

        matched_ingredients = list(dict.fromkeys(matched_ingredients))

        if not matched_ingredients:
            continue

        score = 65 + (len(matched_ingredients) * 5)

        if recipe.id in favourite_recipe_ids:
            score += 10

        recommendations.append(
            {
                "title": recipe.title,
                "reason": (
                    "This saved recipe matches ingredients currently available "
                    "in your Smart Pantry."
                ),
                "ingredients": ", ".join(matched_ingredients),
                "score": min(score, 92),
                "badge": "Saved Match",
                "source": "Saved Recipes",
                "difficulty": recipe.difficulty,
                "saved_recipe": recipe,
                "query": ", ".join(matched_ingredients),
            }
        )

    return recommendations


def get_personalised_recommendations(user, limit=6):
    """
    Main recommendation engine function.

    Returns a ranked list of recommendation dictionaries.

    Scoring is based on:
    - pantry ingredient availability
    - expiring soon ingredients
    - saved recipes
    - favourite recipes
    - recipe history
    - cuisine and meal-type frequency
    """

    profile = build_user_preference_profile(user)

    recommendations = []

    recommendations.extend(
        build_pantry_based_recommendations(profile)
    )

    recommendations.extend(
        build_saved_recipe_matches(user, profile)
    )

    # Remove duplicate titles while keeping the highest scored item.
    unique_recommendations = {}

    for recommendation in recommendations:
        title_key = normalise_text(recommendation.get("title"))

        if not title_key:
            continue

        existing = unique_recommendations.get(title_key)

        if not existing or recommendation.get("score", 0) > existing.get("score", 0):
            unique_recommendations[title_key] = recommendation

    ranked_recommendations = sorted(
        unique_recommendations.values(),
        key=lambda item: item.get("score", 0),
        reverse=True,
    )

    return ranked_recommendations[:limit]