"""
Shopping list helper service for CulinaAI.

Purpose:
- Keeps shopping list parsing and grouping logic out of views.py.
- Converts saved recipe ingredients into a clean grocery-style list.
- Groups ingredients into shopping categories for a better user experience.
"""

import re


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
        "description": "Meat, eggs, tofu, beans and protein-rich items.",
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
            "tortilla",
            "oil",
            "olive oil",
            "soy sauce",
            "vinegar",
            "stock",
            "broth",
            "sugar",
            "honey",
            "oats",
            "quinoa",
            "couscous",
            "can",
            "canned",
        ],
    },
    {
        "key": "spices",
        "title": "Spices & Seasoning",
        "icon": "bi-stars",
        "description": "Spices, herbs, salt and flavour boosters.",
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


def clean_ingredient_line(line):
    """
    Cleans one ingredient line from recipe.ingredients_text.

    Handles:
    - bullet points
    - numbered lists
    - extra spaces
    """

    cleaned_line = line.strip()

    # Remove bullet symbols from the start of the line.
    cleaned_line = re.sub(r"^[\-\*\•]\s*", "", cleaned_line)

    # Remove numbered list prefixes such as "1." or "2)".
    cleaned_line = re.sub(r"^\d+[\.\)]\s*", "", cleaned_line)

    return cleaned_line.strip()


def extract_ingredient_items(ingredients_text):
    """
    Converts the saved recipe ingredient text into individual shopping items.
    """

    if not ingredients_text:
        return []

    # Most AI recipe outputs are line-based.
    raw_lines = ingredients_text.splitlines()

    # If the recipe only has one long comma-separated line, split by comma.
    if len(raw_lines) <= 1 and "," in ingredients_text:
        raw_lines = ingredients_text.split(",")

    items = []

    for raw_line in raw_lines:
        item_name = clean_ingredient_line(raw_line)

        if item_name:
            items.append(item_name)

    return items


def choose_category_key(item_name):
    """
    Chooses the best shopping category for one ingredient item.
    """

    lower_item_name = item_name.lower()

    for category in CATEGORY_DEFINITIONS:
        if category["key"] == "other":
            continue

        for keyword in category["keywords"]:
            if keyword in lower_item_name:
                return category["key"]

    return "other"


def build_shopping_categories(ingredient_items):
    """
    Groups ingredient items into shopping categories.
    """

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

        category_lookup[category_key]["items"].append(
            {
                "name": item_name,
                "checkbox_id": f"shopping-item-{index}",
            }
        )

    # Only show categories that actually contain items.
    visible_categories = [
        category_lookup[category["key"]]
        for category in CATEGORY_DEFINITIONS
        if category_lookup[category["key"]]["items"]
    ]

    return visible_categories


def build_shopping_list_context(recipe):
    """
    Builds all shopping list context values used by the template.
    """

    ingredient_items = extract_ingredient_items(recipe.ingredients_text)
    shopping_categories = build_shopping_categories(ingredient_items)

    return {
        "shopping_categories": shopping_categories,
        "shopping_total_items": len(ingredient_items),
        "shopping_total_categories": len(shopping_categories),
    }