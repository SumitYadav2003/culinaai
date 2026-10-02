"""
Rule-based warnings for a recipe. The AI writes none of these, so each rule
can be unit tested.

- Allergens: which of the UK's 14 declarable allergens the ingredients contain
  (FSA allergen guidance), for every user, not just those who filled in the
  allergy field.
- Hidden allergens: everyday products that usually contain an allergen their
  name doesn't mention (e.g. Worcestershire sauce and fish). Worded "usually"
  or "often", because recipes vary by brand.
- Cook thoroughly (poultry, pork, mince, burgers, sausages), raw or lightly
  cooked egg, "high in" from red traffic lights, and incomplete nutrition.
"""

import re

from nutrition.services import MINIMUM_COVERAGE_PCT

# The 14 allergens UK food businesses must declare, with words that reveal them
# in an ingredient name. Matching is on whole words, so "pea" doesn't match "peanut".
ALLERGEN_KEYWORDS = {
    "Celery": ["celery", "celeriac", "celery salt"],
    "Cereals containing gluten": [
        "wheat", "flour", "bread", "breadcrumb", "pasta", "spaghetti", "penne", "fusilli", "macaroni",
        "lasagne", "noodle", "couscous", "bulgur", "barley", "rye", "oat", "semolina", "tortilla", "wrap",
        "naan", "pitta", "chapati", "roti", "pastry", "biscuit", "cracker", "beer", "spelt", "bun", "bap",
        "bagel", "brioche", "croissant", "crumpet", "flatbread", "pizza", "gnocchi", "dumpling",
    ],
    "Crustaceans": ["prawn", "shrimp", "crab", "lobster", "crayfish", "langoustine", "scampi"],
    "Eggs": ["egg", "mayonnaise", "mayo", "meringue", "aioli"],
    "Fish": ["fish", "salmon", "tuna", "cod", "haddock", "mackerel", "sardine", "anchovy", "trout", "pollock", "hake", "sea bass"],
    "Lupin": ["lupin", "lupini"],
    "Milk": [
        "milk", "cheese", "butter", "cream", "yogurt", "yoghurt", "paneer", "ghee", "creme fraiche", "whey",
        "mozzarella", "parmesan", "cheddar", "feta", "ricotta", "mascarpone", "halloumi", "custard",
    ],
    "Molluscs": ["mussel", "oyster", "squid", "calamari", "octopus", "clam", "scallop", "cockle", "whelk", "snail"],
    "Mustard": ["mustard"],
    "Peanuts": ["peanut", "groundnut"],
    "Sesame": ["sesame", "tahini", "houmous", "hummus"],
    "Soya": ["soy", "soya", "tofu", "edamame", "tempeh", "miso"],
    "Sulphur dioxide and sulphites": ["wine", "sulphite", "dried apricot"],
    "Tree nuts": [
        "almond", "hazelnut", "walnut", "cashew", "pecan", "brazil nut", "pistachio", "macadamia", "marzipan",
        "praline",
    ],
}

# Names that contain an allergen word but not the allergen itself.
NOT_THIS_ALLERGEN = {
    "Milk": [
        "coconut milk", "oat milk", "oat drink", "soya milk", "soy milk", "almond milk", "rice milk",
        "peanut butter", "nut butter", "almond butter", "butter bean", "cocoa butter", "dairy-free", "dairy free",
        "non-dairy",
    ],
    "Cereals containing gluten": ["rice noodle", "corn tortilla", "gluten-free", "gluten free"],
    "Eggs": ["egg-free", "egg free", "eggplant"],
}

# Products whose name hides an allergen: product -> [(allergen, sentence)].
HIDDEN_ALLERGENS = {
    "worcestershire sauce": [
        ("Fish", "Worcestershire sauce usually contains anchovies (fish)."),
        ("Cereals containing gluten", "Worcestershire sauce often contains malt vinegar (barley, gluten)."),
    ],
    "malt vinegar": [("Cereals containing gluten", "Malt vinegar is made from barley (gluten).")],
    "sausage": [("Cereals containing gluten", "Sausages usually contain rusk (wheat, gluten).")],
    "pesto": [
        ("Milk", "Pesto usually contains cheese (milk)."),
        ("Tree nuts", "Many pesto jars use cashews (tree nuts). Pine nuts are not one of the 14 allergens."),
    ],
    "stock cube": [
        ("Celery", "Stock cubes often contain celery."),
        ("Cereals containing gluten", "Stock cubes often contain wheat (gluten)."),
    ],
    "stock": [
        ("Celery", "Ready-made stock often contains celery."),
        ("Cereals containing gluten", "Ready-made stock often contains wheat (gluten)."),
    ],
    "gravy granule": [
        ("Celery", "Gravy granules often contain celery."),
        ("Cereals containing gluten", "Gravy granules often contain wheat (gluten)."),
    ],
    "soy sauce": [("Cereals containing gluten", "Soy sauce is usually brewed with wheat (gluten).")],
    "oyster sauce": [("Molluscs", "Oyster sauce is made from oysters (molluscs).")],
    "curry paste": [("Crustaceans", "Thai curry pastes often contain shrimp paste (crustaceans).")],
    "fish sauce": [("Fish", "Fish sauce is made from fish.")],
    "marzipan": [("Tree nuts", "Marzipan is made from almonds (tree nuts).")],
    "caesar dressing": [("Fish", "Caesar dressing usually contains anchovies (fish).")],
    "quorn": [("Eggs", "Most Quorn products are made with egg white.")],
    "naan": [("Milk", "Naan bread often contains milk or yogurt.")],
}

# Shown as a "check the label" alert, but not banned for users with that allergy,
# because allergen-free versions are common ("gluten-free sausages", "gluten-free
# vegetable stock"). The specific "stock cube" and "gravy granule" entries are banned.
ALERT_ONLY = {"stock", "sausage"}

# Words a user might type in the allergy field, mapped to the allergens above.
USER_ALLERGY_WORDS = {
    "fish": ["Fish"],
    "anchov": ["Fish"],
    "shellfish": ["Crustaceans", "Molluscs"],
    "crustacean": ["Crustaceans"],
    "prawn": ["Crustaceans"],
    "shrimp": ["Crustaceans"],
    "mollusc": ["Molluscs"],
    "celery": ["Celery"],
    "gluten": ["Cereals containing gluten"],
    "wheat": ["Cereals containing gluten"],
    "coeliac": ["Cereals containing gluten"],
    "celiac": ["Cereals containing gluten"],
    "dairy": ["Milk"],
    "milk": ["Milk"],
    "lactose": ["Milk"],
    "cheese": ["Milk"],
    "tree nut": ["Tree nuts"],
    "nut": ["Tree nuts"],
    "almond": ["Tree nuts"],
    "cashew": ["Tree nuts"],
}

POULTRY_AND_MINCE = [
    "chicken", "turkey", "duck", "goose", "poultry", "pork", "bacon", "gammon", "sausage", "burger",
    "mince", "minced", "liver", "kebab", "meatball",
]
LIGHTLY_COOKED_EGG_WORDS = [
    "raw egg", "mousse", "tiramisu", "homemade mayonnaise", "aioli", "hollandaise", "eggnog", "runny",
    "soft-boiled", "soft boiled", "lightly cooked", "carbonara",
]

NUTRIENT_LABELS = {"fat_g": "fat", "saturates_g": "saturated fat", "sugars_g": "sugars", "salt_g": "salt"}


def has_word(text, term):
    """Whole-word match that also accepts a plural: 'egg' matches 'eggs', not 'eggplant'."""
    pattern = r"(?<![a-z])" + re.escape(term) + r"(?:s|es)?(?![a-z])"
    return re.search(pattern, text.lower()) is not None


def allergens_in(ingredient_names, food_names=None):
    """
    {allergen: [ingredient names that contain it]} for the 14 UK allergens.
    `food_names` maps an ingredient to the CoFID food it was matched to, which
    is checked too: "burger bun" says nothing about wheat, but its food,
    "Bread rolls, white, crusty", does.
    """
    food_names = food_names or {}
    found = {}
    for name in ingredient_names:
        for text in (name, food_names.get(name, "")):
            lowered = text.lower()
            for allergen, keywords in ALLERGEN_KEYWORDS.items():
                if name in found.get(allergen, []):
                    continue
                if any(phrase in lowered for phrase in NOT_THIS_ALLERGEN.get(allergen, [])):
                    continue
                if any(has_word(lowered, keyword) for keyword in keywords):
                    found.setdefault(allergen, []).append(name)
    return found


def hidden_allergen_alerts(ingredient_names):
    """[{"product", "allergen", "text"}] for products that usually hide an allergen."""
    alerts = []
    for name in ingredient_names:
        for product, entries in HIDDEN_ALLERGENS.items():
            if product == "stock" and has_word(name, "stock cube"):
                continue  # "stock cube" has its own, more specific entry
            if has_word(name, product):
                for allergen, sentence in entries:
                    alerts.append({"product": name, "allergen": allergen, "text": f"{sentence} Check the label."})
    return alerts


def allergens_for_user_allergies(allergy_text):
    """The 14-allergen names that the user's free-text allergies point to."""
    text = str(allergy_text or "").lower()
    allergens = set()
    for word, mapped in USER_ALLERGY_WORDS.items():
        # Match from the start of a word, so "peanut" is not read as "nut".
        if re.search(r"(?<![a-z])" + re.escape(word), text):
            allergens.update(mapped)
    return allergens


def hidden_products_for_allergies(allergy_text):
    """
    Products to avoid because they usually hide one of the user's allergens,
    e.g. a fish allergy adds 'worcestershire sauce'. Used by the recipe prompt
    and the allergy gate, so these products are swapped out automatically.
    """
    allergens = allergens_for_user_allergies(allergy_text)
    return sorted(
        product for product, entries in HIDDEN_ALLERGENS.items()
        if product not in ALERT_ONLY and any(allergen in allergens for allergen, _ in entries)
    )


def safety_flags(ingredient_names, recipe_text):
    """Cook-thoroughly and lightly-cooked-egg flags."""
    flags = []
    names_text = " | ".join(ingredient_names)
    if any(has_word(names_text, word) for word in POULTRY_AND_MINCE):
        flags.append({
            "code": "cook_thoroughly",
            "title": "Cook thoroughly",
            "text": "Cook poultry, pork, mince, burgers and sausages until steaming hot all the way through, "
                    "with no pink meat and clear juices (FSA advice).",
        })
    recipe_lower = str(recipe_text or "").lower()
    if any(has_word(name, "egg") for name in ingredient_names) and any(
        word in recipe_lower for word in LIGHTLY_COOKED_EGG_WORDS
    ):
        flags.append({
            "code": "lightly_cooked_egg",
            "title": "Raw or lightly cooked egg",
            "text": "This recipe uses raw or lightly cooked egg. If you are cooking for someone who is pregnant, "
                    "elderly, very young or unwell, check the NHS advice on eggs first.",
        })
    return flags


def nutrition_flags(nutrition):
    """'High in' flags from red traffic lights, and a flag when nutrition is incomplete."""
    flags = []
    if not nutrition:
        return flags
    for nutrient, colour in nutrition["traffic_lights"].items():
        if colour == "red":
            amount = nutrition["per_serving"][nutrient]
            share = nutrition["percent_reference_intake"].get(nutrient)
            flags.append({
                "code": f"high_{nutrient}",
                "title": f"High in {NUTRIENT_LABELS[nutrient]}",
                "text": f"{amount:.1f} g per serving, {share}% of an adult's reference intake.",
            })
    if nutrition["coverage_pct"] < MINIMUM_COVERAGE_PCT:
        missing = ", ".join(nutrition["unmatched"]) or "some ingredients"
        flags.append({
            "code": "nutrition_incomplete",
            "title": "Nutrition incomplete",
            "text": f"Not found in the food data: {missing}. The real dish has more than the totals show.",
        })
    return flags
