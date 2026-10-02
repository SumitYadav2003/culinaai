"""
Nutrition engine for CulinaAI.

Turns a list of recipe ingredients (name + grams) into calories and nutrients
using the UK government's CoFID 2021 food data (plus a few USDA foods that
CoFID doesn't cover, each labelled with its source), then applies:

- FSA front-of-pack traffic lights (Department of Health and FSA guidance, 2016)
- UK nutrition claim conditions (retained Regulation (EC) No 1924/2006, Annex)
- a carbon footprint from Poore & Nemecek (2018), global averages per kg of food
- a cost estimate from ONS average prices and UK supermarket shelf prices

Nothing here asks the AI for numbers. The AI only supplies ingredient names and
weights; every figure shown to the user is calculated in this file.
"""

import re
from dataclasses import dataclass, field

from .models import CofidFood, IngredientAlias

NUTRIENTS = [
    "energy_kcal",
    "energy_kj",
    "protein_g",
    "fat_g",
    "saturates_g",
    "carbohydrate_g",
    "sugars_g",
    "fibre_g",
    "salt_g",
]

# Below this share of the recipe's weight matched to CoFID, the totals are shown
# with an "incomplete" note instead of being presented as the full picture.
MINIMUM_COVERAGE_PCT = 85.0

# FSA traffic lights for foods, per 100 g: (green up to, amber up to, red per portion above).
# The per-portion red rule only applies when a portion is over 100 g.
TRAFFIC_LIGHT_THRESHOLDS = {
    "fat_g": (3.0, 17.5, 21.0),
    "saturates_g": (1.5, 5.0, 6.0),
    "sugars_g": (5.0, 22.5, 27.0),
    "salt_g": (0.3, 1.5, 1.8),
}

# Adult reference intakes used on UK food labels.
REFERENCE_INTAKES = {
    "energy_kcal": 2000,
    "energy_kj": 8400,
    "fat_g": 70,
    "saturates_g": 20,
    "sugars_g": 90,
    "salt_g": 6,
}

# Words that describe a cooking state. When the recipe doesn't say "cooked",
# we prefer the raw form, because recipes list raw weights.
COOKED_WORDS = {"boiled", "fried", "grilled", "roasted", "baked", "stewed", "steamed", "cooked", "microwaved", "poached"}

# Tap water and salt have no Poore & Nemecek category, but their footprint is
# tiny, so they count as zero rather than as "no figure".
WATER_CODE = "17-377"
NEGLIGIBLE_CARBON_CODES = {WATER_CODE, "17-367"}  # water, salt


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@dataclass
class IngredientInput:
    name: str
    grams: float


@dataclass
class MatchedIngredient:
    name: str
    grams: float
    food_code: str
    food_name: str
    method: str  # "alias" or "fuzzy"
    nutrients: dict  # this ingredient's contribution, e.g. {"energy_kcal": 495.0, ...}
    source: str = "CoFID 2021"  # where the per-100 g values come from
    carbon_kg: float | None = None  # kg CO2e for the grams used; None when there is no figure
    carbon_category: str = ""
    cost_gbp: float | None = None  # cost of the grams used; None when there is no price


@dataclass
class NutritionResult:
    servings: int
    total_grams: float
    matched: list = field(default_factory=list)
    unmatched: list = field(default_factory=list)
    coverage_pct: float = 0.0
    totals: dict = field(default_factory=dict)
    per_serving: dict = field(default_factory=dict)
    per_100g: dict = field(default_factory=dict)
    percent_reference_intake: dict = field(default_factory=dict)
    traffic_lights: dict = field(default_factory=dict)
    claims: list = field(default_factory=list)

    # Carbon and cost are None when no ingredient has a figure, so a dish is never
    # shown as "0 kg" or "£0.00" just because nothing could be looked up.
    # Coverage is the share of the recipe's weight with a figure, leaving out
    # water, which would otherwise make almost any soup or dal look fully covered.
    carbon_kg_total: float | None = None
    carbon_kg_per_serving: float | None = None
    carbon_coverage_pct: float = 0.0
    carbon_unmatched: list = field(default_factory=list)  # ingredients with no carbon figure

    cost_gbp_total: float | None = None
    cost_gbp_per_serving: float | None = None
    cost_coverage_pct: float = 0.0
    cost_unmatched: list = field(default_factory=list)  # ingredients with no price

    @property
    def is_complete(self):
        return self.coverage_pct >= MINIMUM_COVERAGE_PCT


# ---------------------------------------------------------------------------
# Matching ingredient names to CoFID foods
# ---------------------------------------------------------------------------

def singular(word):
    """Very small plural rule: tomatoes -> tomato, onions -> onion, berries -> berry."""
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("oes") and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def words_of(text):
    """'Chicken, breast, raw' -> {'chicken', 'breast', 'raw'}"""
    return {singular(w) for w in re.findall(r"[a-z]+", text.lower())}


def normalise_name(name):
    """' Red Onions ' -> 'red onion' (used for alias lookup)."""
    return " ".join(singular(w) for w in re.findall(r"[a-z]+", name.lower()))


def find_by_alias(name):
    normalised = normalise_name(name)
    for candidate in (name.strip().lower(), normalised):
        alias = IngredientAlias.objects.select_related("food__carbon_category").filter(alias=candidate).first()
        if alias:
            return alias.food
    return None


def find_by_words(name, foods):
    """
    Fuzzy match that is easy to explain: every word of the ingredient must appear
    in the CoFID food name. Among those, prefer the raw form (unless the ingredient
    itself says it is cooked), then the shortest, most general name.
    Composite dishes ("Burger, beef, with bun") are skipped unless the ingredient
    itself says "with", so "burger bun" never matches a whole burger.
    Returns None rather than guessing.
    """
    wanted = words_of(name)
    if not wanted:
        return None

    wants_cooked = bool(wanted & COOKED_WORDS)
    allow_composite = "with" in wanted
    candidates = [
        food for food, food_words in foods
        if wanted <= food_words and (allow_composite or "with" not in food_words)
    ]
    if not candidates:
        return None

    def preference(food):
        food_words = words_of(food.name)
        is_raw = "raw" in food_words
        return (
            0 if (is_raw and not wants_cooked) else 1,
            len(food_words),
            food.name,
        )

    return sorted(candidates, key=preference)[0]


def load_foods_for_matching():
    """All CoFID foods with their word sets, built once per calculation."""
    return [(food, words_of(food.name)) for food in CofidFood.objects.select_related("carbon_category")]


# ---------------------------------------------------------------------------
# Calculation
# ---------------------------------------------------------------------------

def nutrients_for(food, grams):
    """Scale a food's per-100 g values to the grams used. Missing values count as 0."""
    factor = grams / 100.0
    return {n: (getattr(food, n) or 0.0) * factor for n in NUTRIENTS}


def carbon_for(food, grams):
    """kg CO2e for the grams used, or None when the food has no carbon category."""
    if food.food_code in NEGLIGIBLE_CARBON_CODES:
        return 0.0
    if food.carbon_category is None:
        return None
    return food.carbon_category.kg_co2e_per_kg * grams / 1000.0


def cost_for(food, grams):
    """Cost in pounds for the grams used, or None when the food has no price."""
    if food.price_per_kg_gbp is None:
        return None
    return food.price_per_kg_gbp * grams / 1000.0


def traffic_light(nutrient, per_100g, per_portion, portion_grams):
    green_max, amber_max, portion_red = TRAFFIC_LIGHT_THRESHOLDS[nutrient]
    if portion_grams > 100 and per_portion > portion_red:
        return "red"
    if per_100g <= green_max:
        return "green"
    if per_100g <= amber_max:
        return "amber"
    return "red"


def nutrition_claims(per_100g):
    """
    Claims the dish qualifies for, using the UK nutrition claim conditions
    for solid foods, applied to the finished dish per 100 g.
    """
    claims = []
    energy = per_100g["energy_kcal"]
    protein_share = (per_100g["protein_g"] * 4 / energy) if energy else 0
    saturates_share = (per_100g["saturates_g"] * 9 / energy) if energy else 0
    fibre_per_100kcal = (per_100g["fibre_g"] / energy * 100) if energy else 0

    if protein_share >= 0.20:
        claims.append("High protein")
    elif protein_share >= 0.12:
        claims.append("Source of protein")

    if per_100g["fibre_g"] >= 6 or fibre_per_100kcal >= 3:
        claims.append("High fibre")
    elif per_100g["fibre_g"] >= 3 or fibre_per_100kcal >= 1.5:
        claims.append("Source of fibre")

    if per_100g["fat_g"] <= 3:
        claims.append("Low fat")
    if per_100g["saturates_g"] <= 1.5 and saturates_share <= 0.10:
        claims.append("Low saturated fat")
    if per_100g["sugars_g"] <= 5:
        claims.append("Low sugars")
    if per_100g["salt_g"] <= 0.3:
        claims.append("Low salt")
    return claims


def calculate_nutrition(ingredients, servings):
    """
    ingredients: list of IngredientInput (name, grams of the raw ingredient)
    servings:    how many people the recipe serves

    Returns a NutritionResult. Unmatched ingredients are listed, never guessed.
    """
    servings = max(int(float(servings or 1)), 1)
    foods = load_foods_for_matching()
    result = NutritionResult(servings=servings, total_grams=0.0)
    totals = {n: 0.0 for n in NUTRIENTS}
    matched_grams = 0.0
    carbon_total, carbon_grams = 0.0, 0.0
    cost_total, cost_grams = 0.0, 0.0
    non_water_grams = 0.0
    has_carbon = has_cost = False  # True once an ingredient other than water has a figure

    for item in ingredients:
        grams = max(float(item.grams or 0), 0.0)
        result.total_grams += grams

        food, method = find_by_alias(item.name), "alias"
        if food is None:
            food, method = find_by_words(item.name, foods), "fuzzy"
        is_water = food is not None and food.food_code == WATER_CODE
        if not is_water:
            non_water_grams += grams
        if food is None:
            result.unmatched.append(item.name)
            result.carbon_unmatched.append(item.name)
            result.cost_unmatched.append(item.name)
            continue

        contribution = nutrients_for(food, grams)
        for n in NUTRIENTS:
            totals[n] += contribution[n]
        matched_grams += grams

        carbon = carbon_for(food, grams)
        if carbon is None:
            result.carbon_unmatched.append(item.name)
        else:
            carbon_total += carbon
            if not is_water:
                carbon_grams += grams
                has_carbon = True

        cost = cost_for(food, grams)
        if cost is None:
            result.cost_unmatched.append(item.name)
        else:
            cost_total += cost
            if not is_water:
                cost_grams += grams
                has_cost = True

        result.matched.append(
            MatchedIngredient(
                item.name, grams, food.food_code, food.name, method, contribution, food.source,
                carbon_kg=None if carbon is None else round(carbon, 3),
                carbon_category=food.carbon_category.name if food.carbon_category else "",
                cost_gbp=None if cost is None else round(cost, 3),
            )
        )

    result.totals = {n: round(v, 2) for n, v in totals.items()}
    result.coverage_pct = round(matched_grams / result.total_grams * 100, 1) if result.total_grams else 0.0
    result.per_serving = {n: round(v / servings, 2) for n, v in totals.items()}

    # Per 100 g of the dish is based on matched weight, so unmatched items don't dilute it.
    result.per_100g = {n: round(v / matched_grams * 100, 2) if matched_grams else 0.0 for n, v in totals.items()}

    result.percent_reference_intake = {
        n: round(result.per_serving[n] / ri * 100) for n, ri in REFERENCE_INTAKES.items()
    }

    portion_grams = result.total_grams / servings
    result.traffic_lights = {
        n: traffic_light(n, result.per_100g[n], result.per_serving[n], portion_grams)
        for n in TRAFFIC_LIGHT_THRESHOLDS
    }
    result.claims = nutrition_claims(result.per_100g) if matched_grams else []

    def share(grams):
        return round(grams / non_water_grams * 100, 1) if non_water_grams else 0.0

    result.carbon_coverage_pct = share(carbon_grams)
    if has_carbon:
        result.carbon_kg_total = round(carbon_total, 3)
        result.carbon_kg_per_serving = round(carbon_total / servings, 3)

    result.cost_coverage_pct = share(cost_grams)
    if has_cost:
        result.cost_gbp_total = round(cost_total, 2)
        result.cost_gbp_per_serving = round(cost_total / servings, 2)
    return result
