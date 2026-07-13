"""
Shopping list helper service for CulinaAI.

Purpose:
- Converts saved recipe ingredients into a clean grocery-style list.
- Groups ingredients into shopping categories.
- Compares recipe ingredients with the user's Smart Pantry.
- Shows what the user already has and what they still need to buy.
"""

import re

from django.db.models import Q
from django.utils import timezone

from .models import PantryItem


CATEGORY_DEFINITIONS = [
    {
        "key": "fresh_produce",
        "title": "Fresh Produce",
        "icon": "bi-basket2-fill",
        "description": "Vegetables, fruits and fresh herbs.",
        "keywords": [
            "tomato",
            "onion",
            "garlic",
            "ginger",
            "potato",
            "carrot",
            "pepper",
            "capsicum",
            "lettuce",
            "spinach",
            "mushroom",
            "coriander",
            "cilantro",
            "parsley",
            "basil",
            "mint",
            "lemon",
            "lime",
            "apple",
            "banana",
            "avocado",
            "broccoli",
            "cucumber",
            "chilli",
            "chili",
        ],
    },
    {
        "key": "protein",
        "title": "Protein",
        "icon": "bi-egg-fried",
        "description": "Meat, eggs, tofu, paneer, beans and protein-rich items.",
        "keywords": [
            "chicken",
            "beef",
            "lamb",
            "fish",
            "salmon",
            "tuna",
            "prawn",
            "shrimp",
            "egg",
            "tofu",
            "paneer",
            "beans",
            "lentils",
            "chickpeas",
            "turkey",
            "pork",
            "mince",
        ],
    },
    {
        "key": "dairy",
        "title": "Dairy & Chilled",
        "icon": "bi-snow2",
        "description": "Milk, cheese, yoghurt, cream and chilled items.",
        "keywords": [
            "milk",
            "cheese",
            "cream",
            "yoghurt",
            "yogurt",
            "butter",
            "mozzarella",
            "parmesan",
            "cheddar",
            "feta",
            "ricotta",
        ],
    },
    {
        "key": "pantry",
        "title": "Pantry Staples",
        "icon": "bi-box-seam-fill",
        "description": "Rice, pasta, flour, oil, sauces and cupboard items.",
        "keywords": [
            "rice",
            "pasta",
            "noodle",
            "flour",
            "bread",
            "oil",
            "olive oil",
            "sauce",
            "soy sauce",
            "vinegar",
            "sugar",
            "honey",
            "stock",
            "broth",
            "oats",
            "cereal",
            "quinoa",
        ],
    },
    {
        "key": "spices",
        "title": "Spices & Seasoning",
        "icon": "bi-stars",
        "description": "Salt, spices, herbs and flavour boosters.",
        "keywords": [
            "salt",
            "pepper",
            "paprika",
            "cumin",
            "turmeric",
            "curry",
            "oregano",
            "thyme",
            "rosemary",
            "chilli powder",
            "chili powder",
            "garam masala",
            "masala",
            "seasoning",
            "flakes",
            "powder",
            "spice",
        ],
    },
    {
        "key": "other",
        "title": "Other Items",
        "icon": "bi-bag-check-fill",
        "description": "Everything else needed for the recipe.",
        "keywords": [],
    },
]


STOP_WORDS = {
    "fresh",
    "chopped",
    "diced",
    "sliced",
    "minced",
    "grated",
    "crushed",
    "small",
    "medium",
    "large",
    "optional",
    "to",
    "taste",
    "of",
    "and",
    "or",
    "for",
    "the",
    "a",
    "an",
}

MEASUREMENT_WORDS = {
    "g",
    "gram",
    "grams",
    "kg",
    "kilogram",
    "kilograms",
    "ml",
    "l",
    "litre",
    "litres",
    "liter",
    "liters",
    "cup",
    "cups",
    "tbsp",
    "tablespoon",
    "tablespoons",
    "tsp",
    "teaspoon",
    "teaspoons",
    "piece",
    "pieces",
    "pcs",
    "pack",
    "packet",
    "pinch",
    "handful",
}


def clean_ingredient_line(line):
    """
    Cleans one ingredient line from recipe.ingredients_text.

    Handles:
    - bullet points
    - numbered lists
    - extra spaces
    """

    cleaned_line = str(line).strip()

    # Remove bullet symbols from the start.
    cleaned_line = re.sub(r"^[\-\*\•]\s*", "", cleaned_line)

    # Remove numbered list prefixes such as "1." or "2)".
    cleaned_line = re.sub(r"^\d+[\.\)]\s*", "", cleaned_line)

    return cleaned_line.strip()


def extract_ingredient_items(ingredients_text):
    """
    Converts saved recipe ingredient text into individual shopping items.
    """

    if not ingredients_text:
        return []

    raw_lines = str(ingredients_text).splitlines()

    # If ingredients are stored as one comma-separated line, split by comma.
    if len(raw_lines) <= 1 and "," in str(ingredients_text):
        raw_lines = str(ingredients_text).split(",")

    items = []

    for raw_line in raw_lines:
        item_name = clean_ingredient_line(raw_line)

        if item_name:
            items.append(item_name)

    return items


def normalise_for_matching(value):
    """
    Converts recipe ingredient text and pantry ingredient names into comparable tokens.

    Example:
    '500g chopped fresh tomatoes' -> 'tomatoes'
    'Tomato' -> 'tomato'
    """

    if not value:
        return ""

    text = str(value).lower().strip()

    # Remove quantities and common fractions.
    text = re.sub(r"\b\d+(\.\d+)?\b", " ", text)
    text = re.sub(r"[½¼¾⅓⅔⅛⅜⅝⅞]", " ", text)

    # Replace punctuation with spaces.
    text = re.sub(r"[^a-zA-Z\s]", " ", text)

    words = []

    for word in text.split():
        clean_word = word.strip()

        if not clean_word:
            continue

        if clean_word in STOP_WORDS:
            continue

        if clean_word in MEASUREMENT_WORDS:
            continue

        # Simple singular handling.
        if clean_word.endswith("es") and len(clean_word) > 4:
            clean_word = clean_word[:-2]
        elif clean_word.endswith("s") and len(clean_word) > 3:
            clean_word = clean_word[:-1]

        words.append(clean_word)

    return " ".join(words)


def choose_category_key(item_name):
    """
    Chooses the best shopping category for one ingredient item.
    """

    lower_item_name = str(item_name).lower()

    for category in CATEGORY_DEFINITIONS:
        if category["key"] == "other":
            continue

        for keyword in category["keywords"]:
            if keyword in lower_item_name:
                return category["key"]

    return "other"


def get_available_pantry_lookup(user):
    """
    Returns non-expired available pantry ingredients for comparison.

    Expired pantry items are not counted as available.
    """

    if not user or not user.is_authenticated:
        return []

    today = timezone.localdate()

    pantry_items = (
        PantryItem.objects.filter(
            user=user,
            is_available=True,
        )
        .filter(
            Q(expiry_date__isnull=True) | Q(expiry_date__gte=today)
        )
        .order_by("ingredient_name")
    )

    pantry_lookup = []

    for pantry_item in pantry_items:
        clean_key = normalise_for_matching(pantry_item.ingredient_name)

        if clean_key:
            pantry_lookup.append(
                {
                    "name": pantry_item.ingredient_name,
                    "key": clean_key,
                    "item": pantry_item,
                }
            )

    return pantry_lookup


def find_pantry_match(recipe_ingredient, pantry_lookup):
    """
    Checks whether a recipe ingredient exists in the user's Smart Pantry.
    """

    recipe_key = normalise_for_matching(recipe_ingredient)

    if not recipe_key:
        return None

    recipe_tokens = set(recipe_key.split())

    for pantry_entry in pantry_lookup:
        pantry_key = pantry_entry["key"]
        pantry_tokens = set(pantry_key.split())

        if recipe_key == pantry_key:
            return pantry_entry

        if pantry_key in recipe_key or recipe_key in pantry_key:
            return pantry_entry

        if recipe_tokens and pantry_tokens and recipe_tokens.intersection(pantry_tokens):
            return pantry_entry

    return None


def build_pantry_comparison(ingredient_items, user=None):
    """
    Compares recipe ingredients with Smart Pantry.

    Returns:
    - available ingredients already in pantry
    - missing ingredients to buy
    - pantry match score
    """

    pantry_lookup = get_available_pantry_lookup(user)

    available_items = []
    missing_items = []

    for index, item_name in enumerate(ingredient_items, start=1):
        pantry_match = find_pantry_match(item_name, pantry_lookup)

        item_data = {
            "name": item_name,
            "checkbox_id": f"shopping-item-{index}",
            "pantry_match": pantry_match["name"] if pantry_match else "",
            "pantry_status": "available" if pantry_match else "missing",
            "pantry_badge": "In Pantry" if pantry_match else "Need to Buy",
        }

        if pantry_match:
            available_items.append(item_data)
        else:
            missing_items.append(item_data)

    total_items = len(ingredient_items)
    available_count = len(available_items)

    pantry_match_score = 0

    if total_items:
        pantry_match_score = round((available_count / total_items) * 100)

    return {
        "pantry_available_items": available_items,
        "pantry_missing_items": missing_items,
        "pantry_available_count": available_count,
        "pantry_missing_count": len(missing_items),
        "pantry_match_score": pantry_match_score,
        "pantry_has_matches": available_count > 0,
    }


def build_shopping_categories(ingredient_items, user=None):
    """
    Groups ingredient items into shopping categories and adds pantry status.
    """

    pantry_lookup = get_available_pantry_lookup(user)

    category_lookup = {}

    for category in CATEGORY_DEFINITIONS:
        category_lookup[category["key"]] = {
            "key": category["key"],
            "title": category["title"],
            "icon": category["icon"],
            "description": category["description"],
            "items": [],
        }

    for index, item_name in enumerate(ingredient_items, start=1):
        category_key = choose_category_key(item_name)
        pantry_match = find_pantry_match(item_name, pantry_lookup)

        category_lookup[category_key]["items"].append(
            {
                "name": item_name,
                "checkbox_id": f"shopping-item-{index}",
                "pantry_match": pantry_match["name"] if pantry_match else "",
                "pantry_status": "available" if pantry_match else "missing",
                "pantry_badge": "In Pantry" if pantry_match else "Need to Buy",
            }
        )

    visible_categories = [
        category_lookup[category["key"]]
        for category in CATEGORY_DEFINITIONS
        if category_lookup[category["key"]]["items"]
    ]

    return visible_categories


def build_shopping_list_context(recipe, user=None):
    """
    Builds all shopping list context values used by the saved recipe detail template.

    Keeps old keys:
    - shopping_categories
    - shopping_total_items
    - shopping_total_categories

    Adds new pantry-aware keys:
    - pantry_available_items
    - pantry_missing_items
    - pantry_available_count
    - pantry_missing_count
    - pantry_match_score
    """

    ingredient_items = extract_ingredient_items(recipe.ingredients_text)
    shopping_categories = build_shopping_categories(
        ingredient_items=ingredient_items,
        user=user,
    )

    pantry_context = build_pantry_comparison(
        ingredient_items=ingredient_items,
        user=user,
    )

    return {
        "shopping_categories": shopping_categories,
        "shopping_total_items": len(ingredient_items),
        "shopping_total_categories": len(shopping_categories),
        **pantry_context,
    }