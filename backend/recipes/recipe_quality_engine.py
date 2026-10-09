import copy
import re
from typing import Any, Dict, List, Set

from .risk_service import hidden_products_for_allergies


TARGET_VALIDATION_SCORE = 85
MINIMUM_DISPLAY_SCORE = 70

NO_VALUE_MARKERS = {
    "",
    "none",
    "none provided",
    "n/a",
    "na",
    "any cuisine",
    "any meal type",
}


ALLERGY_SYNONYMS = {
    "peanut": [
        "peanut",
        "peanuts",
        "groundnut",
        "groundnuts",
        "peanut butter",
        "peanut oil",
        "satay",
        "arachis",
    ],
    "nut": [
        "nut",
        "nuts",
        "almond",
        "almonds",
        "cashew",
        "cashews",
        "walnut",
        "walnuts",
        "hazelnut",
        "hazelnuts",
        "pistachio",
        "pistachios",
        "pecan",
        "pecans",
    ],
    "dairy": [
        "milk",
        "cheese",
        "butter",
        "cream",
        "yogurt",
        "yoghurt",
        "paneer",
        "ghee",
        "whey",
        "curd",
    ],
    "gluten": [
        "wheat",
        "flour",
        "bread",
        "pasta",
        "barley",
        "rye",
        "semolina",
        "soy sauce",
        "breadcrumbs",
    ],
    "egg": [
        "egg",
        "eggs",
        "mayonnaise",
        "mayo",
        "omelette",
        "omelet",
    ],
    "fish": [
        "fish",
        "salmon",
        "tuna",
        "cod",
        "mackerel",
        "anchovy",
        "anchovies",
    ],
    "shellfish": [
        "shellfish",
        "prawn",
        "prawns",
        "shrimp",
        "crab",
        "lobster",
        "mussels",
        "oyster",
        "oysters",
    ],
    "soy": [
        "soy",
        "soya",
        "tofu",
        "tempeh",
        "soy sauce",
        "edamame",
    ],
    "sesame": [
        "sesame",
        "tahini",
        "sesame oil",
    ],
    "mustard": [
        "mustard",
        "mustard seeds",
        "mustard powder",
    ],
}


DIET_RESTRICTED_TERMS = {
    "vegetarian": [
        "chicken",
        "beef",
        "pork",
        "lamb",
        "mutton",
        "turkey",
        "bacon",
        "ham",
        "fish",
        "salmon",
        "tuna",
        "prawn",
        "shrimp",
        "crab",
        "lobster",
        "anchovy",
        "gelatin",
        "gelatine",
    ],
    "vegan": [
        "chicken",
        "beef",
        "pork",
        "lamb",
        "mutton",
        "turkey",
        "bacon",
        "ham",
        "fish",
        "salmon",
        "tuna",
        "prawn",
        "shrimp",
        "crab",
        "lobster",
        "milk",
        "cheese",
        "butter",
        "cream",
        "yogurt",
        "yoghurt",
        "paneer",
        "ghee",
        "egg",
        "eggs",
        "honey",
        "whey",
        "curd",
    ],
    "halal": [
        "pork",
        "bacon",
        "ham",
        "pepperoni",
        "prosciutto",
        "alcohol",
        "wine",
        "beer",
        "rum",
        "vodka",
        "whisky",
        "whiskey",
    ],
    "gluten": [
        "wheat",
        "flour",
        "bread",
        "pasta",
        "barley",
        "rye",
        "semolina",
        "soy sauce",
        "breadcrumbs",
    ],
    "dairy": [
        "milk",
        "cheese",
        "butter",
        "cream",
        "yogurt",
        "yoghurt",
        "paneer",
        "ghee",
        "whey",
        "curd",
    ],
    "egg": [
        "egg",
        "eggs",
        "omelette",
        "omelet",
        "mayonnaise",
        "mayo",
    ],
    "nut": [
        "peanut",
        "peanuts",
        "almond",
        "cashew",
        "walnut",
        "hazelnut",
        "pistachio",
        "pecan",
        "nut butter",
    ],
}


EQUIPMENT_KEYWORDS = {
    "stove": [
        "stove",
        "hob",
        "pan",
        "skillet",
        "saucepan",
        "pot",
        "kadai",
        "tawa",
        "frying pan",
        "cooktop",
    ],
    "gas burner": [
        "gas burner",
        "gas stove",
        "gas hob",
        "burner",
        "open flame",
    ],
    "induction hob": [
        "induction",
        "induction hob",
        "induction cooktop",
        "induction stove",
    ],
    "portable camping stove": [
        "portable stove",
        "camping stove",
        "camp stove",
        "trekking stove",
        "portable gas stove",
        "small gas stove",
    ],
    "electric hot plate": [
        "electric hot plate",
        "hot plate",
        "electric stove",
        "single electric burner",
    ],
    "traditional chulha": [
        "chulha",
        "clay stove",
        "traditional stove",
        "wood-fired stove",
        "wood fire",
        "charcoal stove",
    ],
    "oven": [
        "oven",
        "bake",
        "baked",
        "baking tray",
        "roast in the oven",
    ],
    "microwave": [
        "microwave",
    ],
    "air fryer": [
        "air fryer",
        "air-fryer",
        "airfryer",
    ],
    "blender": [
        "blender",
        "using a blender",
        "in a blender",
        "food processor",
        "mixer grinder",
        "spice grinder",
        "grind into a paste",
        "blend into a paste",
        "blend until smooth",
        # The verb only: "tomato puree" and "garlic puree" are shop-bought, and a
        # pepper grinder or mashing garlic "to a smooth paste" needs no blender.
        "puree the",
        "puree it",
        "puree until",
        "puree everything",
        "blitz",
    ],
    "pressure cooker": [
        "pressure cooker",
        "instant pot",
        "pressure-cook",
        "pressure cook",
    ],
}


COMPLEX_METHOD_TERMS = [
    "sous-vide",
    "ferment",
    "fermentation",
    "overnight",
    "dehydrate",
    "smoke for",
    "tempering chocolate",
    "double boiler",
    "proof for",
    "marinate overnight",
    "rest for 12 hours",
]


# Headings that come after STEPS in a CulinaAI recipe (ai_service.py).
STEPS_END_HEADINGS = (
    "allergy", "nutrition", "estimated cost", "pairing", "chef tips", "storage", "substitution",
)

# "marinate for 20 minutes, or overnight" / "up to overnight": the long time is optional.
OPTIONAL_TIME = r"\b(?:or|up to|or even|ideally|preferably)\s+overnight\b|\bovernight if you (?:have|like|can)\b"


CUISINE_KEYWORDS = {
    "indian": [
        "masala",
        "turmeric",
        "cumin",
        "coriander",
        "garam masala",
        "tadka",
        "curry",
        "paneer",
        "jeera",
        "dal",
        "chapati",
        "roti",
    ],
    "italian": [
        "pasta",
        "basil",
        "oregano",
        "parmesan",
        "mozzarella",
        "olive oil",
        "risotto",
        "tomato sauce",
        "italian herbs",
    ],
    "chinese": [
        "soy sauce",
        "ginger",
        "spring onion",
        "stir-fry",
        "sesame oil",
        "noodles",
        "wok",
    ],
    "mexican": [
        "tortilla",
        "beans",
        "salsa",
        "jalapeno",
        "cumin",
        "lime",
        "taco",
        "burrito",
    ],
    "thai": [
        "coconut milk",
        "lemongrass",
        "thai basil",
        "fish sauce",
        "lime",
        "curry paste",
    ],
}


NUTRITION_GOAL_KEYWORDS = {
    "high protein": [
        "protein",
        "paneer",
        "tofu",
        "lentil",
        "lentils",
        "beans",
        "chickpeas",
        "egg",
        "eggs",
        "greek yogurt",
        "soy",
    ],
    "high_protein": [
        "protein",
        "paneer",
        "tofu",
        "lentil",
        "lentils",
        "beans",
        "chickpeas",
        "egg",
        "eggs",
        "greek yogurt",
        "soy",
    ],
    "low calorie": [
        "low calorie",
        "light",
        "steamed",
        "grilled",
        "less oil",
        "minimal oil",
    ],
    "low_calorie": [
        "low calorie",
        "light",
        "steamed",
        "grilled",
        "less oil",
        "minimal oil",
    ],
    "low carb": [
        "low carb",
        "cauliflower rice",
        "lettuce",
        "zucchini",
        "reduced rice",
        "no bread",
    ],
    "low_carb": [
        "low carb",
        "cauliflower rice",
        "lettuce",
        "zucchini",
        "reduced rice",
        "no bread",
    ],
    "comfort food": [
        "comfort",
        "creamy",
        "warm",
        "hearty",
        "cozy",
        "rich",
    ],
    "comfort_food": [
        "comfort",
        "creamy",
        "warm",
        "hearty",
        "cozy",
        "rich",
    ],
    "balanced": [
        "balanced",
        "vegetables",
        "protein",
        "carbohydrate",
        "fiber",
        "fibre",
        "egg",
        "bread",
    ],
}


COOKING_ACTION_WORDS = [
    "chop",
    "slice",
    "dice",
    "boil",
    "cook",
    "fry",
    "saute",
    "sauté",
    "mix",
    "stir",
    "bake",
    "roast",
    "grill",
    "simmer",
    "season",
    "serve",
    "heat",
    "add",
    "combine",
]


QUANTITY_PATTERN = re.compile(
    r"(\d+(/\d+)?|\d+\.\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s?"
    r"(cup|cups|slice|slices|tbsp|tablespoon|tablespoons|tsp|teaspoon|teaspoons|"
    r"g|kg|gram|grams|ml|l|liter|litre|pinch|handful|piece|pieces|small|medium|large)",
    re.IGNORECASE,
)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value).lower()
    text = text.replace("_", " ")
    text = re.sub(r"[^a-z0-9\s\-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def split_items(value: Any) -> List[str]:
    if value is None:
        return []

    if isinstance(value, (list, tuple, set)):
        items = []

        for item in value:
            items.extend(split_items(item))

        return items

    text = str(value)
    text = re.sub(r"\band\b", ",", text, flags=re.IGNORECASE)
    text = re.sub(r"[\n;|/]+", ",", text)

    items = []

    for item in text.split(","):
        clean_item = normalize_text(item)

        if clean_item and clean_item not in NO_VALUE_MARKERS:
            items.append(clean_item)

    return items


def contains_term(text: str, term: str) -> bool:
    clean_text = normalize_text(text)
    clean_term = normalize_text(term)

    if not clean_term:
        return False

    pattern = r"(?<![a-z0-9])" + re.escape(clean_term) + r"(?![a-z0-9])"
    return re.search(pattern, clean_text) is not None


def find_matching_terms(text: str, terms: List[str]) -> List[str]:
    found_terms = []

    for term in terms:
        if contains_term(text, term):
            found_terms.append(term)

    return sorted(set(found_terms))


def build_check(
    name: str,
    category: str,
    passed: bool,
    score: int,
    max_score: int,
    severity: str,
    message: str,
    details: Dict[str, Any] = None,
) -> Dict[str, Any]:
    return {
        "name": name,
        "category": category,
        "passed": passed,
        "score": max(0, min(score, max_score)),
        "max_score": max_score,
        "severity": severity,
        "message": message,
        "details": details or {},
    }


def expand_allergy_terms(allergies: List[str]) -> List[str]:
    expanded_terms: Set[str] = set()

    for allergy in allergies:
        clean_allergy = normalize_text(allergy)

        if not clean_allergy:
            continue

        expanded_terms.add(clean_allergy)

        if clean_allergy.endswith("s"):
            expanded_terms.add(clean_allergy[:-1])
        else:
            expanded_terms.add(f"{clean_allergy}s")
            expanded_terms.add(f"{clean_allergy}es")

        for allergy_key, synonyms in ALLERGY_SYNONYMS.items():
            if allergy_key in clean_allergy or clean_allergy in allergy_key:
                expanded_terms.update(synonyms)

                for synonym in synonyms:
                    clean_synonym = normalize_text(synonym)

                    if clean_synonym.endswith("s"):
                        expanded_terms.add(clean_synonym[:-1])
                    else:
                        expanded_terms.add(f"{clean_synonym}s")
                        expanded_terms.add(f"{clean_synonym}es")

    return sorted(expanded_terms)


# Phrases that say an ingredient is NOT in the dish ("no", "free of", "skips",
# "instead of"). Only a short list of the excluded foods may follow them, so
# "instead of yoghurt, use cashews" still counts cashews as used.
NEGATION_CUES = [
    "no", "not", "without", "free of", "free from", "avoid", "avoids", "avoided", "avoiding",
    "does not contain", "doesn t contain", "contains no", "do not include", "does not include",
    "not include", "exclude", "excludes", "excluded", "excluding", "skip", "skips", "skipped",
    "skipping", "omit", "omits", "omitted", "omitting", "leave out", "leaves out", "left out",
    "leaving out", "instead of", "in place of", "rather than", "replaces", "replaced", "replacing",
    "swaps out", "swapped out", "removed", "removes", "allergic to", "allergy to", "allergies to",
    "intolerant to", "never use", "not use", "not used", "no need for", "any trace of",
]

# Words that may sit between a cue and the excluded food: "free of any tree nuts or peanuts".
NEGATION_FILLER = {
    "a", "an", "the", "any", "all", "of", "or", "and", "nor", "such", "as", "like", "including",
    "usual", "traditional", "classic", "typical", "common", "other", "added", "extra", "whole",
    "ground", "chopped", "toasted", "flaked", "roasted", "raw", "fresh", "dried", "tree", "nut",
    "nuts", "type", "types", "kind", "kinds", "form", "forms",
    # Allergen groups, so "no dairy products or nuts" reads as one list.
    "dairy", "gluten", "wheat", "egg", "eggs", "soy", "soya", "sesame", "peanut", "peanuts", "fish",
    "shellfish", "seafood", "meat", "mustard", "celery", "lupin", "sulphites", "molluscs",
    "crustaceans", "products", "ingredients", "traces", "items", "foods", "allergens", "seeds",
}

# After the food: "tree nut-free", "a tree nut allergy", "nut allergies".
SAFE_AFTER = r"(?:\s*-?\s*free\b|\s+allerg\w*|\s+intoleran\w*)"


def is_safe_allergy_context(recipe_text: str, term: str, other_terms: List[str] = None) -> bool:
    """
    True only when every mention of an allergy term says it is NOT in the dish:
    "no tomato", "free of tree nuts", "it skips cashews and almonds",
    "tree nut-free", "suitable for a tree nut allergy", "instead of cashews".

    Each mention is judged on its own words, so "Garnish with almonds (nut-free
    option: leave them out)" still fails, and so does "instead of yoghurt, use
    cashews". Added after the Phase 5 benchmark, where natural wording like
    "respects your tree nut allergy" failed a safe Indian recipe three times.
    """

    clean_text = normalize_text(recipe_text)
    clean_term = normalize_text(term)

    if not clean_term:
        return True

    pattern = r"(?<![a-z0-9])" + re.escape(clean_term) + r"(?![a-z0-9])"
    matches = list(re.finditer(pattern, clean_text))

    if not matches:
        return True

    # Other excluded foods can be listed together: "skips cashews and almonds".
    filler = set(NEGATION_FILLER)
    for other in other_terms or []:
        filler.update(normalize_text(other).split())

    for match in matches:
        after = clean_text[match.end():match.end() + 20]
        if re.match(SAFE_AFTER, after):
            continue

        # Walk back over filler words (at most 6) looking for a cue.
        before_words = clean_text[:match.start()].replace("-", " ").split()[-12:]
        safe = False
        skipped = 0
        while before_words and skipped <= 6:
            for cue in NEGATION_CUES:
                cue_words = cue.split()
                if before_words[-len(cue_words):] == cue_words:
                    safe = True
                    break
            if safe or before_words[-1] not in filler:
                break
            before_words.pop()
            skipped += 1

        if not safe:
            return False

    return True


def find_unsafe_allergy_terms(recipe_text: str, allergy_terms: List[str]) -> List[str]:
    unsafe_terms = []

    for term in allergy_terms:
        if contains_term(recipe_text, term) and not is_safe_allergy_context(
            recipe_text,
            term,
            allergy_terms,
        ):
            unsafe_terms.append(term)

    return sorted(set(unsafe_terms))


def check_allergy_safety(
    preferences: Dict[str, Any],
    recipe_text: str,
) -> Dict[str, Any]:
    allergies = split_items(preferences.get("allergies"))

    if not allergies:
        return build_check(
            name="Allergy Safety",
            category="Safety",
            passed=True,
            score=20,
            max_score=20,
            severity="critical",
            message="No allergy restrictions were provided by the user.",
        )

    # Products that usually hide one of the user's allergens count too,
    # e.g. Worcestershire sauce for a fish allergy (risk_service.py).
    allergy_terms = sorted(
        set(expand_allergy_terms(allergies))
        | set(hidden_products_for_allergies(preferences.get("allergies")))
    )
    conflicts = find_unsafe_allergy_terms(recipe_text, allergy_terms)

    if conflicts:
        return build_check(
            name="Allergy Safety",
            category="Safety",
            passed=False,
            score=0,
            max_score=20,
            severity="critical",
            message="Unsafe allergy conflict detected. The recipe must be regenerated before being shown.",
            details={
                "user_allergies": allergies,
                "conflicting_terms": conflicts,
            },
        )

    return build_check(
        name="Allergy Safety",
        category="Safety",
        passed=True,
        score=20,
        max_score=20,
        severity="critical",
        message="No unsafe allergy conflict was detected in the generated recipe.",
        details={
            "user_allergies": allergies,
        },
    )


def get_restricted_diet_terms(diet_preferences: List[str]) -> List[str]:
    """
    Converts user diet preferences into ingredients that must not appear.

    Important:
    - Eggetarian / Ovo-vegetarian allows eggs.
    - Egg-free means eggs are restricted.
    - We avoid simple substring matching because 'eggetarian' contains 'egg'.
    """

    restricted_terms: Set[str] = set()

    for diet in diet_preferences:
        clean_diet = normalize_text(diet)

        if clean_diet in [
            "eggetarian",
            "eggitarian",
            "eggeterian",
            "egg vegetarian",
            "egg-vegetarian",
            "ovo vegetarian",
            "ovo-vegetarian",
            "ovo vegetarian diet",
        ]:
            restricted_terms.update(DIET_RESTRICTED_TERMS.get("vegetarian", []))
            continue

        if clean_diet == "vegetarian" or clean_diet.endswith(" vegetarian"):
            restricted_terms.update(DIET_RESTRICTED_TERMS.get("vegetarian", []))
            continue

        if clean_diet == "vegan" or "vegan" in clean_diet:
            restricted_terms.update(DIET_RESTRICTED_TERMS.get("vegan", []))
            continue

        if clean_diet == "halal" or "halal" in clean_diet:
            restricted_terms.update(DIET_RESTRICTED_TERMS.get("halal", []))

        if (
            clean_diet == "gluten free"
            or clean_diet == "gluten-free"
            or "gluten free" in clean_diet
            or "coeliac" in clean_diet
            or "celiac" in clean_diet
        ):
            restricted_terms.update(DIET_RESTRICTED_TERMS.get("gluten", []))

        if (
            clean_diet == "dairy free"
            or clean_diet == "dairy-free"
            or "dairy free" in clean_diet
            or "lactose free" in clean_diet
        ):
            restricted_terms.update(DIET_RESTRICTED_TERMS.get("dairy", []))

        if (
            clean_diet == "egg free"
            or clean_diet == "egg-free"
            or "egg free" in clean_diet
        ):
            restricted_terms.update(DIET_RESTRICTED_TERMS.get("egg", []))

        if (
            clean_diet == "nut free"
            or clean_diet == "nut-free"
            or "nut free" in clean_diet
        ):
            restricted_terms.update(DIET_RESTRICTED_TERMS.get("nut", []))

    return sorted(restricted_terms)


def find_unsafe_diet_terms(recipe_text: str, restricted_terms: List[str]) -> List[str]:
    """
    Finds diet-restricted terms only when they appear in an unsafe context.

    This prevents false failures when the recipe says:
    'This recipe does not include fish'
    or
    'No chicken is used'.
    """

    unsafe_terms = []

    for term in restricted_terms:
        if contains_term(recipe_text, term) and not is_safe_allergy_context(
            recipe_text,
            term,
        ):
            unsafe_terms.append(term)

    return sorted(set(unsafe_terms))


def check_diet_compliance(
    preferences: Dict[str, Any],
    recipe_text: str,
) -> Dict[str, Any]:
    diet_preferences = split_items(preferences.get("diet_preferences"))

    if not diet_preferences:
        return build_check(
            name="Diet Compliance",
            category="Safety",
            passed=True,
            score=20,
            max_score=20,
            severity="critical",
            message="No diet preference was selected, so no diet conflict was detected.",
        )

    restricted_terms = get_restricted_diet_terms(diet_preferences)

    if not restricted_terms:
        return build_check(
            name="Diet Compliance",
            category="Safety",
            passed=True,
            score=20,
            max_score=20,
            severity="critical",
            message="The selected diet preference does not create any restricted ingredient conflict.",
            details={
                "diet_preferences": diet_preferences,
            },
        )

    conflicts = find_unsafe_diet_terms(recipe_text, restricted_terms)

    if conflicts:
        return build_check(
            name="Diet Compliance",
            category="Safety",
            passed=False,
            score=0,
            max_score=20,
            severity="critical",
            message="Unsafe diet conflict detected. The recipe must be regenerated.",
            details={
                "diet_preferences": diet_preferences,
                "conflicting_terms": conflicts,
            },
        )

    return build_check(
        name="Diet Compliance",
        category="Safety",
        passed=True,
        score=20,
        max_score=20,
        severity="critical",
        message="The recipe follows the selected diet preferences.",
        details={
            "diet_preferences": diet_preferences,
        },
    )


def ingredient_variants(ingredient: str) -> List[str]:
    """
    Builds alternative names for an ingredient so validation does not fail
    because of plural/singular words or common UK/Indian/US ingredient names.

    Important fix:
    ingredient_synonyms must be defined before it is used. Earlier it was
    accidentally inside the else block, so ingredients ending with "s" caused
    UnboundLocalError.
    """

    ingredient = normalize_text(ingredient)
    variants = set()

    if not ingredient:
        return []

    variants.add(ingredient)

    if ingredient.endswith("s"):
        variants.add(ingredient[:-1])
    else:
        variants.add(f"{ingredient}s")

    ingredient_synonyms = {
        "chickpea": ["chickpea", "chickpeas", "chana", "garbanzo"],
        "aubergine": ["aubergine", "eggplant", "brinjal"],
        "coriander": ["coriander", "cilantro"],
        "spring onion": ["spring onion", "scallion"],
        "paneer": ["paneer", "cottage cheese", "indian cottage cheese"],
        "yogurt": ["yogurt", "yoghurt", "curd", "dahi"],
        "bell pepper": ["bell pepper", "capsicum", "pepper"],
        "egg": ["egg", "eggs", "omelette", "omelet"],
        "bread": ["bread", "toast", "sourdough", "slice"],
        "rice": ["rice", "basmati rice", "white rice", "brown rice"],
        "lentil": ["lentil", "lentils", "dal", "daal"],
        "soy": ["soy", "soya", "soya chunks", "soy chunks"],
        "tofu": ["tofu", "bean curd"],

        "avocado": ["avocado", "avocados", "avacado", "avacados"],
        "cucumber": ["cucumber", "cucumbers", "cumcumber", "cumcumbers"],
        "beetroot": ["beetroot", "beetroots", "beet root", "beet roots", "beets"],
        "tomato": ["tomato", "tomatoes", "tomatos", "tamato"],
        "potato": ["potato", "potatoes", "potatos", "patato"],
        "mango": ["mango", "mangoes", "mangos", "raw mango", "raw mangoes"],
    }

    for key, synonyms in ingredient_synonyms.items():
        synonym_set = {normalize_text(item) for item in [key] + synonyms}

        if ingredient == key or ingredient in synonym_set:
            variants.update(synonym_set)

    return sorted(variant for variant in variants if variant)

def check_ingredient_match(
    preferences: Dict[str, Any],
    recipe_text: str,
) -> Dict[str, Any]:
    user_ingredients = split_items(preferences.get("ingredients"))

    if not user_ingredients:
        return build_check(
            name="Ingredient Match",
            category="Constraint Match",
            passed=False,
            score=0,
            max_score=15,
            severity="major",
            message="No usable ingredients were found from the user input.",
        )

    matched_ingredients = []
    missing_ingredients = []

    for ingredient in user_ingredients:
        variants = ingredient_variants(ingredient)

        if find_matching_terms(recipe_text, variants):
            matched_ingredients.append(ingredient)
        else:
            missing_ingredients.append(ingredient)

    match_ratio = len(matched_ingredients) / len(user_ingredients)
    score = round(match_ratio * 15)
    passed = match_ratio >= 0.6

    return build_check(
        name="Ingredient Match",
        category="Constraint Match",
        passed=passed,
        score=score,
        max_score=15,
        severity="major",
        message=f"The recipe uses {len(matched_ingredients)} out of {len(user_ingredients)} user-provided ingredients.",
        details={
            "matched_ingredients": matched_ingredients,
            "missing_ingredients": missing_ingredients,
            "match_percentage": round(match_ratio * 100),
        },
    )


def extract_recipe_minutes(recipe_text: str) -> int:
    clean_text = normalize_text(recipe_text)
    durations = []

    combined_matches = re.findall(
        r"(\d+)\s*(?:hour|hours|hr|hrs)\s*(?:and\s*)?(\d+)?\s*(?:minute|minutes|min|mins)?",
        clean_text,
    )

    for hours, minutes in combined_matches:
        total = int(hours) * 60

        if minutes:
            total += int(minutes)

        durations.append(total)

    minute_matches = re.findall(r"(\d+)\s*(?:minute|minutes|min|mins)\b", clean_text)

    for minutes in minute_matches:
        durations.append(int(minutes))

    if not durations:
        return 0

    return max(durations)


def check_time_match(
    preferences: Dict[str, Any],
    recipe_text: str,
) -> Dict[str, Any]:
    requested_minutes = preferences.get("cooking_time_minutes") or 0
    detected_minutes = extract_recipe_minutes(recipe_text)

    if not requested_minutes:
        return build_check(
            name="Cooking Time Match",
            category="Constraint Match",
            passed=True,
            score=10,
            max_score=10,
            severity="minor",
            message="No requested cooking time was provided.",
        )

    if not detected_minutes:
        return build_check(
            name="Cooking Time Match",
            category="Constraint Match",
            passed=False,
            score=3,
            max_score=10,
            severity="minor",
            message="The recipe does not clearly mention total cooking time.",
            details={
                "requested_minutes": requested_minutes,
                "detected_minutes": detected_minutes,
            },
        )

    allowed_minutes = round((requested_minutes * 1.25) + 5)

    if detected_minutes <= allowed_minutes:
        score = 10
        passed = True
        message = "The detected cooking time is within the accepted range."
    elif detected_minutes <= requested_minutes * 1.75:
        score = 6
        passed = True
        message = "The recipe is slightly above the requested cooking time."
    else:
        score = 2
        passed = False
        message = "The recipe cooking time is too high compared to the user's request."

    return build_check(
        name="Cooking Time Match",
        category="Constraint Match",
        passed=passed,
        score=score,
        max_score=10,
        severity="minor",
        message=message,
        details={
            "requested_minutes": requested_minutes,
            "detected_minutes": detected_minutes,
            "allowed_minutes": allowed_minutes,
        },
    )


def get_selected_equipment_keys(selected_equipment: List[str]) -> Set[str]:
    """
    Converts selected equipment labels into validation keys.

    Important:
    If the user selects any direct heat source such as induction hob,
    gas burner, portable camping stove, electric hot plate or chulha,
    then normal pan/pot/frying-pan cooking should be allowed.
    """

    selected_equipment_text = normalize_text(" ".join(selected_equipment))
    selected_keys = set()

    for equipment_key in EQUIPMENT_KEYWORDS:
        if equipment_key in selected_equipment_text:
            selected_keys.add(equipment_key)

    direct_heat_sources = {
        "stove",
        "gas burner",
        "induction hob",
        "portable camping stove",
        "electric hot plate",
        "traditional chulha",
    }

    if selected_keys.intersection(direct_heat_sources):
        selected_keys.update(direct_heat_sources)

    return selected_keys


def check_equipment_match(
    preferences: Dict[str, Any],
    recipe_text: str,
) -> Dict[str, Any]:
    selected_equipment = split_items(preferences.get("cooking_equipment"))

    if not selected_equipment:
        return build_check(
            name="Equipment Compatibility",
            category="Practicality",
            passed=True,
            score=10,
            max_score=10,
            severity="major",
            message="No equipment restriction was provided by the user.",
        )

    selected_keys = get_selected_equipment_keys(selected_equipment)
    unavailable_equipment_found = []

    for equipment_key, keywords in EQUIPMENT_KEYWORDS.items():
        if equipment_key not in selected_keys:
            matched_terms = find_matching_terms(recipe_text, keywords)

            if matched_terms:
                unavailable_equipment_found.extend(matched_terms)

    if unavailable_equipment_found:
        return build_check(
            name="Equipment Compatibility",
            category="Practicality",
            passed=False,
            score=3,
            max_score=10,
            severity="major",
            message="The recipe appears to require equipment not selected by the user.",
            details={
                "selected_equipment": selected_equipment,
                "selected_equipment_keys": sorted(selected_keys),
                "unavailable_equipment_found": sorted(
                    set(unavailable_equipment_found)
                ),
            },
        )

    return build_check(
        name="Equipment Compatibility",
        category="Practicality",
        passed=True,
        score=10,
        max_score=10,
        severity="major",
        message="No unavailable cooking equipment was detected.",
        details={
            "selected_equipment": selected_equipment,
            "selected_equipment_keys": sorted(selected_keys),
        },
    )


def check_recipe_structure(recipe_text: str) -> Dict[str, Any]:
    clean_text = normalize_text(recipe_text)
    original_lines = [
        line.strip()
        for line in recipe_text.splitlines()
        if line.strip()
    ]

    has_title = len(original_lines) > 0
    has_ingredients = "ingredient" in clean_text
    has_steps = any(
        word in clean_text
        for word in ["step", "method", "instruction", "directions"]
    )
    has_time = any(
        word in clean_text
        for word in ["time", "minute", "minutes", "min", "hour"]
    )
    has_servings = any(
        word in clean_text
        for word in ["serving", "servings", "serves"]
    )
    has_quantity = QUANTITY_PATTERN.search(recipe_text) is not None
    has_actions = any(
        contains_term(recipe_text, action)
        for action in COOKING_ACTION_WORDS
    )

    score = 0
    score += 2 if has_title else 0
    score += 3 if has_ingredients else 0
    score += 3 if has_steps else 0
    score += 2 if has_time else 0
    score += 2 if has_servings else 0
    score += 2 if has_quantity else 0
    score += 1 if has_actions else 0

    passed = score >= 11 and has_ingredients and has_steps

    return build_check(
        name="Recipe Structure",
        category="Output Quality",
        passed=passed,
        score=score,
        max_score=15,
        severity="critical" if not has_ingredients or not has_steps else "major",
        message="The recipe structure is complete."
        if passed
        else "The recipe is missing important recipe sections.",
        details={
            "has_title": has_title,
            "has_ingredients_section": has_ingredients,
            "has_steps_section": has_steps,
            "has_time": has_time,
            "has_servings": has_servings,
            "has_quantities": has_quantity,
            "has_cooking_actions": has_actions,
        },
    )


def check_difficulty_match(
    preferences: Dict[str, Any],
    recipe_text: str,
) -> Dict[str, Any]:
    """
    Checks whether the generated recipe matches the requested difficulty.

    This version counts only real numbered cooking steps, not ingredient quantities
    such as '1 cup bread' or '2 eggs'.
    """

    difficulty = normalize_text(preferences.get("difficulty"))

    step_count = 0
    step_lines = []

    in_steps_section = False

    for line in recipe_text.splitlines():
        clean_line = line.strip().lower()

        if clean_line.startswith("steps"):
            in_steps_section = True
            continue

        if clean_line.startswith(STEPS_END_HEADINGS):
            in_steps_section = False

        if in_steps_section:
            step_lines.append(clean_line)

        if in_steps_section and re.match(r"^(step\s*)?\d+[\).\s-]+", clean_line):
            step_count += 1

    # Only the method counts: "keeps in the fridge overnight" in the storage
    # advice doesn't make a dish hard, and nor does an optional "or overnight".
    method_text = normalize_text("\n".join(step_lines) if step_lines else recipe_text)
    method_text = re.sub(OPTIONAL_TIME, " ", method_text)
    complex_terms_found = find_matching_terms(method_text, COMPLEX_METHOD_TERMS)

    if step_count == 0:
        for line in recipe_text.splitlines():
            clean_line = line.strip().lower()

            if re.match(r"^(step\s*)?\d+[\).\s-]+", clean_line):
                step_count += 1

    if difficulty == "easy":
        if complex_terms_found or step_count > 9:
            return build_check(
                name="Difficulty Match",
                category="Practicality",
                passed=False,
                score=1,
                max_score=5,
                severity="minor",
                message="The recipe may be too complex for an easy difficulty request.",
                details={
                    "difficulty": difficulty,
                    "complex_terms_found": complex_terms_found,
                    "estimated_step_count": step_count,
                },
            )

    if difficulty == "medium":
        if step_count > 14:
            return build_check(
                name="Difficulty Match",
                category="Practicality",
                passed=False,
                score=3,
                max_score=5,
                severity="minor",
                message="The recipe may be too long for a medium difficulty request.",
                details={
                    "difficulty": difficulty,
                    "estimated_step_count": step_count,
                },
            )

    return build_check(
        name="Difficulty Match",
        category="Practicality",
        passed=True,
        score=5,
        max_score=5,
        severity="minor",
        message="The recipe difficulty appears suitable for the user's selected level.",
        details={
            "difficulty": difficulty,
            "estimated_step_count": step_count,
        },
    )


def check_cuisine_and_nutrition_relevance(
    preferences: Dict[str, Any],
    recipe_text: str,
) -> Dict[str, Any]:
    cuisine = normalize_text(preferences.get("cuisine"))
    nutrition_goal = normalize_text(preferences.get("nutrition_goal"))

    score = 0
    messages = []
    details = {}

    if cuisine and cuisine not in NO_VALUE_MARKERS:
        cuisine_keywords = []

        for cuisine_key, keywords in CUISINE_KEYWORDS.items():
            if cuisine_key in cuisine:
                cuisine_keywords = keywords
                break

        if cuisine_keywords:
            cuisine_matches = find_matching_terms(recipe_text, cuisine_keywords)
            details["cuisine_matches"] = cuisine_matches

            if cuisine_matches:
                score += 2
                messages.append("Cuisine relevance detected.")
            else:
                messages.append("Cuisine relevance is weak.")
        else:
            score += 2
            messages.append(
                "Cuisine check skipped because no keyword dictionary exists for this cuisine."
            )
    else:
        score += 2
        messages.append("Cuisine check skipped because user selected any cuisine.")

    nutrition_keywords = (
        NUTRITION_GOAL_KEYWORDS.get(nutrition_goal)
        or NUTRITION_GOAL_KEYWORDS.get(nutrition_goal.replace(" ", "_"))
        or []
    )

    if nutrition_keywords:
        nutrition_matches = find_matching_terms(recipe_text, nutrition_keywords)
        details["nutrition_matches"] = nutrition_matches

        if nutrition_matches:
            score += 3
            messages.append("Nutrition goal relevance detected.")
        elif nutrition_goal == "balanced":
            score += 2
            messages.append("Balanced goal accepted with partial evidence.")
        else:
            messages.append("Nutrition goal relevance is weak.")
    else:
        score += 3
        messages.append(
            "Nutrition check skipped because no recognised nutrition goal was provided."
        )

    passed = score >= 3

    return build_check(
        name="Cuisine and Nutrition Relevance",
        category="Personalisation",
        passed=passed,
        score=score,
        max_score=5,
        severity="minor",
        message=" ".join(messages),
        details=details,
    )


# Gate 9 looks for medical or unsupported health claims. Cooking words such as
# "prevent sticking" or "a sweet treat" are deliberately not on this list.
HEALTH_CLAIM_PATTERNS = [
    r"\bcur(?:e|es|ed|ing)\b",
    r"\bdetox\w*",
    r"\bboost(?:s|ing)?\s+(?:your\s+)?(?:immun\w*|metabolism)",
    r"\bimmune system\b",
    r"\bburns?\s+fat\b",
    r"\bfat[- ]burning\b",
    r"\bsuperfoods?\b",
    r"\bheal(?:s|ing)?\b",
    r"\banti[- ]inflammatory\b",
    r"\bclinically proven\b",
    r"\blowers?\s+(?:your\s+)?(?:cholesterol|blood pressure|blood sugar)",
    r"\b(?:cancer|diabetes|heart disease|cardiovascular disease|dementia|alzheimer\w*|arthritis|hypertension)\b",
]


def find_health_claims(text: str) -> List[str]:
    """Medical or unsupported health phrases found in the text."""
    clean_text = normalize_text(text)
    found = []

    for pattern in HEALTH_CLAIM_PATTERNS:
        match = re.search(pattern, clean_text)

        if match:
            found.append(match.group(0))

    return sorted(set(found))


def check_health_claims(recipe_text: str, insights: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Gate 9: no medical or unsupported health claims anywhere the user reads:
    the recipe text and the "Compared with the classic" reasons. Health
    benefit lines are written by code from the claims the numbers qualify
    for (insight_service.py), so they cannot overstate.
    """

    classic_text = " ".join(
        item.get("detail", "")
        for item in ((insights or {}).get("classic") or {}).get("items", [])
    )
    claims = find_health_claims(f"{recipe_text}\n{classic_text}")

    if claims:
        return build_check(
            name="Health Claims",
            category="Safety",
            passed=False,
            score=0,
            max_score=5,
            severity="critical",
            message="The recipe makes medical or unsupported health claims. They must be removed.",
            details={"health_claims_found": claims},
        )

    return build_check(
        name="Health Claims",
        category="Safety",
        passed=True,
        score=5,
        max_score=5,
        severity="critical",
        message="No medical or unsupported health claims were found.",
    )


def check_explanation_consistency(insights: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Gate 10: every classic ingredient this version leaves out has a reason that
    passes its rule (classic_service.py). A failed reason lowers the score but
    is not an automatic hard fail; the page only shows reasons code can prove.
    """

    classic = (insights or {}).get("classic") or {}

    if not (insights or {}).get("available") or not classic.get("is_classic"):
        return build_check(
            name="Explanation Consistency",
            category="Output Quality",
            passed=True,
            score=5,
            max_score=5,
            severity="major",
            message="Not a recognised classic dish, so there is nothing to explain."
            if (insights or {}).get("available")
            else "No structured data for this recipe, so this check was not applied.",
        )

    issues = classic.get("issues") or []

    if issues:
        return build_check(
            name="Explanation Consistency",
            category="Output Quality",
            passed=False,
            score=0,
            max_score=5,
            severity="major",
            message="Some reasons for leaving out classic ingredients could not be confirmed.",
            details={"explanation_issues": [issue["problem"] for issue in issues]},
        )

    return build_check(
        name="Explanation Consistency",
        category="Output Quality",
        passed=True,
        score=5,
        max_score=5,
        severity="major",
        message="Every classic ingredient left out has a confirmed reason.",
    )


# How much each gate counts towards the 100-point score. With gates 9 and 10
# added, ingredient match and recipe structure went from 15 to 10 each; the
# others are unchanged from the 8-gate version.
GATE_WEIGHTS = {
    "Allergy Safety": 20,
    "Diet Compliance": 20,
    "Ingredient Match": 10,
    "Recipe Structure": 10,
    "Cooking Time Match": 10,
    "Equipment Compatibility": 10,
    "Difficulty Match": 5,
    "Cuisine and Nutrition Relevance": 5,
    "Health Claims": 5,
    "Explanation Consistency": 5,
}


def apply_gate_weight(check: Dict[str, Any]) -> Dict[str, Any]:
    """Rescales a gate's own score to its weight, keeping the raw score for the record."""
    weight = GATE_WEIGHTS[check["name"]]
    raw_score, raw_max = check["score"], check["max_score"]
    check["raw_score"], check["raw_max_score"] = raw_score, raw_max
    check["score"] = round(raw_score / raw_max * weight) if raw_max else 0
    check["max_score"] = weight
    return check


def calculate_validation_status(score: int, hard_fail: bool) -> Dict[str, str]:
    if hard_fail:
        return {
            "status": "Failed Safety Validation",
            "risk_level": "High",
            "badge": "Regeneration Required",
        }

    if score >= 90:
        return {
            "status": "Excellent / Verified",
            "risk_level": "Low",
            "badge": "Verified",
        }

    if score >= 85:
        return {
            "status": "Verified",
            "risk_level": "Low",
            "badge": "Verified",
        }

    if score >= 75:
        return {
            "status": "Accepted with Minor Warnings",
            "risk_level": "Medium",
            "badge": "Accepted",
        }

    return {
        "status": "Needs Correction",
        "risk_level": "Medium",
        "badge": "Regeneration Required",
    }


def build_correction_prompt(validation_report: Dict[str, Any]) -> str:
    failed_checks = validation_report.get("failed_checks", [])

    if not failed_checks:
        return "Improve the recipe quality while keeping all user constraints unchanged."

    issue_lines = []

    for check in failed_checks:
        issue_lines.append(f"- {check.get('name')}: {check.get('message')}")

        details = check.get("details") or {}

        if details.get("conflicting_terms"):
            issue_lines.append(
                f"  Conflicting terms: {', '.join(details['conflicting_terms'])}"
            )

        if details.get("missing_ingredients"):
            issue_lines.append(
                f"  Missing user ingredients: {', '.join(details['missing_ingredients'])}"
            )

        if details.get("unavailable_equipment_found"):
            issue_lines.append(
                f"  Unavailable equipment detected: {', '.join(details['unavailable_equipment_found'])}"
            )

        if details.get("health_claims_found"):
            issue_lines.append(
                f"  Remove these health claims: {', '.join(details['health_claims_found'])}"
            )

        if details.get("explanation_issues"):
            issue_lines.append(
                "  Only leave out a classic ingredient for a real reason: "
                + " ".join(details["explanation_issues"])
            )

    return "\n".join(issue_lines)


def validate_recipe_output(
    preferences: Dict[str, Any],
    recipe_text: str,
    attempt_number: int = 1,
    insights: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Runs the 10 quality gates. `insights` (insight_service.build_insights) is
    optional: without it, gate 10 is marked not applicable.
    """
    checks = [
        check_allergy_safety(preferences, recipe_text),
        check_diet_compliance(preferences, recipe_text),
        check_ingredient_match(preferences, recipe_text),
        check_recipe_structure(recipe_text),
        check_time_match(preferences, recipe_text),
        check_equipment_match(preferences, recipe_text),
        check_difficulty_match(preferences, recipe_text),
        check_cuisine_and_nutrition_relevance(preferences, recipe_text),
        check_health_claims(recipe_text, insights),
        check_explanation_consistency(insights),
    ]
    checks = [apply_gate_weight(check) for check in checks]

    hard_fail = any(
        not check["passed"] and check["severity"] == "critical"
        for check in checks
    )

    raw_score = sum(check["score"] for check in checks)

    if hard_fail:
        final_score = min(raw_score, 59)
    else:
        final_score = raw_score

    failed_checks = [check for check in checks if not check["passed"]]
    passed_checks = [check for check in checks if check["passed"]]

    status_data = calculate_validation_status(final_score, hard_fail)
    should_regenerate = hard_fail or final_score < TARGET_VALIDATION_SCORE

    return {
        "attempt_number": attempt_number,
        "score": final_score,
        "max_score": 100,
        "status": status_data["status"],
        "risk_level": status_data["risk_level"],
        "badge": status_data["badge"],
        "hard_fail": hard_fail,
        "should_regenerate": should_regenerate,
        "target_score": TARGET_VALIDATION_SCORE,
        "checks": checks,
        "passed_checks": passed_checks,
        "failed_checks": failed_checks,
        "passed_count": len(passed_checks),
        "failed_count": len(failed_checks),
        "correction_prompt": build_correction_prompt(
            {
                "failed_checks": failed_checks,
            }
        ),
    }


def build_regeneration_preferences(
    original_preferences: Dict[str, Any],
    validation_report: Dict[str, Any],
    attempt_number: int,
) -> Dict[str, Any]:
    regeneration_preferences = copy.deepcopy(original_preferences)

    existing_notes = regeneration_preferences.get("additional_notes", "")
    correction_prompt = validation_report.get("correction_prompt", "")

    strict_instruction = f"""
STRICT CULINAAI VALIDATION CORRECTION REQUEST

The previous generated recipe failed CulinaAI's validation engine.

Validation attempt: {attempt_number}
Previous score: {validation_report.get("score")}/100
Status: {validation_report.get("status")}

You must regenerate the recipe and fix these validation issues:
{correction_prompt}

Important rules:
- Do not include any ingredient that conflicts with allergies.
- Do not include any ingredient that violates diet preferences.
- Use the user's available ingredients as much as possible.
- Keep the cooking time close to the requested cooking time.
- Do not require equipment that the user did not select.
- Include clear sections: Recipe Title, Ingredients with quantities, Cooking Time, Servings, Difficulty, Steps, and Allergy/Safety Notes.
- Do not mention restricted, allergy, or diet-conflicting ingredients anywhere in the final recipe output.
- Do not repeat the conflicting terms in title, ingredients, steps, notes, tips, substitutions, or safety notes.
- In allergy/safety notes, write only: "The user-provided restricted ingredients have been excluded from this recipe."
- Return only the corrected recipe.
"""

    regeneration_preferences["additional_notes"] = (
        f"{existing_notes}\n\n{strict_instruction}"
    )

    return regeneration_preferences


def remove_restricted_ingredients_from_list(
    ingredients: List[str],
    preferences: Dict[str, Any],
) -> List[str]:
    """
    Removes ingredients that conflict with user allergies or restricted diet terms.
    This is used by the deterministic fallback recipe builder.
    """

    allergies = split_items(preferences.get("allergies"))
    allergy_terms = expand_allergy_terms(allergies)

    diet_preferences = split_items(preferences.get("diet_preferences"))
    diet_restricted_terms = get_restricted_diet_terms(diet_preferences)

    restricted_terms = set(allergy_terms + diet_restricted_terms)
    safe_ingredients = []

    for ingredient in ingredients:
        unsafe = False

        for restricted_term in restricted_terms:
            if contains_term(ingredient, restricted_term):
                unsafe = True
                break

        if not unsafe:
            safe_ingredients.append(ingredient)

    return safe_ingredients


def format_fallback_ingredient_quantity(ingredient: str) -> str:
    clean_ingredient = normalize_text(ingredient)

    if "egg" in clean_ingredient:
        return f"- 2 {ingredient}"

    if "bread" in clean_ingredient:
        return f"- 2 slices {ingredient}"

    if "onion" in clean_ingredient:
        return f"- 1 small {ingredient}, finely chopped"

    if "coriander" in clean_ingredient or "cilantro" in clean_ingredient:
        return f"- 2 tablespoons chopped {ingredient}"

    if "rice" in clean_ingredient:
        return f"- 1 cup cooked {ingredient}"

    if "paneer" in clean_ingredient:
        return f"- 100g {ingredient}, cubed"

    if "potato" in clean_ingredient:
        return f"- 1 medium {ingredient}, diced"

    return f"- 1 cup {ingredient}"


def build_safe_fallback_recipe(preferences: Dict[str, Any]) -> Dict[str, str]:
    """
    Builds a deterministic safe recipe when AI regeneration still fails.

    This prevents the user from seeing only a blocking message.
    It uses safe user ingredients, avoids allergy/diet conflicts,
    and keeps the recipe simple enough for validation.
    """

    user_ingredients = split_items(preferences.get("ingredients"))

    safe_ingredients = remove_restricted_ingredients_from_list(
        ingredients=user_ingredients,
        preferences=preferences,
    )

    if not safe_ingredients:
        safe_ingredients = ["rice", "mixed vegetables", "basic seasoning"]

    cooking_time = preferences.get("cooking_time_minutes") or 30
    servings = preferences.get("servings") or 2
    difficulty = preferences.get("difficulty") or "easy"
    cuisine = preferences.get("cuisine") or "Any cuisine"
    meal_type = preferences.get("meal_type") or "Meal"
    nutrition_goal = normalize_text(preferences.get("nutrition_goal"))
    cuisine_clean = normalize_text(cuisine)

    safe_ingredient_text = " ".join(safe_ingredients)

    if "egg" in safe_ingredient_text and "bread" in safe_ingredient_text:
        title = f"{cuisine} Style Egg and Bread {meal_type}".replace(
            "Any cuisine Style ",
            "",
        )
    else:
        main_ingredient = safe_ingredients[0].title()
        title = f"{cuisine} Style {main_ingredient} {meal_type}".replace(
            "Any cuisine Style ",
            "",
        )

    ingredient_lines = [
        format_fallback_ingredient_quantity(ingredient)
        for ingredient in safe_ingredients
    ]

    ingredient_lines.extend(
        [
            "- 1 tablespoon olive oil",
            "- 1/2 teaspoon salt",
            "- 1/2 teaspoon black pepper",
        ]
    )

    if "italian" in cuisine_clean:
        ingredient_lines.extend(
            [
                "- 1/2 teaspoon dried oregano",
                "- 1 teaspoon fresh herbs",
            ]
        )

    if nutrition_goal == "balanced":
        nutrition_note = (
            "This recipe includes a balance of carbohydrates, protein and flavour "
            "from the selected safe ingredients."
        )
    elif nutrition_goal == "high protein":
        nutrition_note = (
            "This recipe keeps the protein-focused ingredients where available."
        )
    else:
        nutrition_note = (
            "This recipe follows the selected nutrition goal as closely as possible "
            "using the safe available ingredients."
        )

    recipe_text = f"""
RECIPE TITLE:
{title}

INGREDIENTS WITH QUANTITIES:
{chr(10).join(ingredient_lines)}

COOKING TIME:
{cooking_time} minutes

SERVINGS:
{servings}

DIFFICULTY:
{difficulty.title()}

STEPS:
1. Prepare all safe ingredients before cooking.
2. Heat olive oil in a pan on medium heat.
3. Add onion or other firm ingredients first and cook for 2 to 3 minutes.
4. Add the remaining safe ingredients and stir gently.
5. If using egg, add it to the pan and cook until fully set.
6. Season with salt, black pepper and herbs.
7. Serve warm as a simple personalised {meal_type.lower()}.

ALLERGY AND SAFETY NOTES:
This fallback recipe excludes the restricted ingredients provided by the user.
Please check packaged ingredients manually before cooking.

NUTRITION NOTE:
{nutrition_note}
""".strip()

    return {
        "recipe_text": recipe_text,
        "prompt": "Deterministic CulinaAI fallback recipe generated after AI validation failure.",
    }