"""
Everything the recipe page says about health, cost, carbon and risk, worked
out by code from the structured ingredients (structure_service.py):

- nutrition, traffic lights, cost and carbon (nutrition/services.py)
- health benefits: only claims the numbers qualify for, as fixed sentences
- "Everyday healthy" or "Treat", decided by the traffic lights, not the AI
- "Compared with the classic" (classic_service.py)
- "One dish, three ways": cheapest, healthiest and greenest versions (swap_service.py)
- whether the dish meets the meal style the user chose (everyday healthy or treat)
- allergens, hidden allergens and safety flags (risk_service.py)
- the fixed disclaimer

The result is a plain dict, so it can be kept in the session and in a JSONField.
"""

import traceback

from nutrition.services import IngredientInput, calculate_for_foods, resolve_ingredients

from .classic_service import compare_with_classic
from .risk_service import NUTRIENT_LABELS, allergens_in, hidden_allergen_alerts, nutrition_flags, safety_flags
from .swap_service import three_ways
from .swap_suggestion_service import suggest_swaps

# 2: adds meal_style and three_ways. Older insights simply don't show those parts.
INSIGHTS_VERSION = 2

DISCLAIMER = (
    "Nutrition values are estimates calculated from UK food composition data (CoFID) using raw ingredient "
    "weights. They are not medical or dietary advice. Always check the labels on the products you buy, "
    "especially for allergens. If you have a medical condition or follow a clinical diet, speak to your GP "
    "or a registered dietitian."
)
COST_NOTE = (
    "Estimated cost, from ONS average prices (August 2026) and Tesco, Sainsbury's and Morrisons prices "
    "(October 2026). Prices vary by shop and over time."
)
CARBON_NOTE = (
    "Carbon figures are global averages per kg of food from Poore & Nemecek (2018), not specific to UK "
    "farms or brands."
)

# One fixed sentence per UK nutrition claim (conditions in nutrition/services.py).
BENEFIT_SENTENCES = {
    "High protein": "Protein gives at least 20% of this dish's energy.",
    "Source of protein": "Protein gives at least 12% of this dish's energy.",
    "High fibre": "At least 6 g of fibre per 100 g, or 3 g per 100 kcal.",
    "Source of fibre": "At least 3 g of fibre per 100 g, or 1.5 g per 100 kcal.",
    "Low fat": "No more than 3 g of fat per 100 g.",
    "Low saturated fat": "No more than 1.5 g of saturated fat per 100 g, and under 10% of the energy.",
    "Low sugars": "No more than 5 g of sugars per 100 g.",
    "Low salt": "No more than 0.3 g of salt per 100 g.",
}


def nutrition_summary(result):
    """The parts of a NutritionResult the page and the dashboard need."""
    return {
        "servings": result.servings,
        "per_serving": result.per_serving,
        "per_100g": result.per_100g,
        "percent_reference_intake": result.percent_reference_intake,
        "traffic_lights": result.traffic_lights,
        "coverage_pct": result.coverage_pct,
        "is_complete": result.is_complete,
        "unmatched": result.unmatched,
        "matched": [
            {"name": m.name, "grams": m.grams, "food_name": m.food_name, "source": m.source, "method": m.method}
            for m in result.matched
        ],
    }


# Rows for the nutrition table: (label, nutrient, unit). Traffic lights and
# reference intakes only exist for some nutrients, as on UK food labels.
NUTRITION_ROWS = [
    ("Energy", "energy_kcal", "kcal"),
    ("Fat", "fat_g", "g"),
    ("Saturates", "saturates_g", "g"),
    ("Carbohydrate", "carbohydrate_g", "g"),
    ("Sugars", "sugars_g", "g"),
    ("Fibre", "fibre_g", "g"),
    ("Protein", "protein_g", "g"),
    ("Salt", "salt_g", "g"),
]
LIGHT_LABELS = {"green": "Low", "amber": "Medium", "red": "High"}

# UK traffic lights only cover fat, saturates, sugars and salt. For the other rows:
# - carbohydrate and protein: the reference intakes on UK food labels
#   (retained Regulation (EC) No 1169/2011, Annex XIII): 260 g and 50 g a day
# - fibre: the UK recommendation of 30 g a day for adults (SACN, Carbohydrates
#   and Health, 2015). It is advice, not a label reference intake, so it is marked.
EXTRA_DAILY_AMOUNTS = {"carbohydrate_g": 260, "protein_g": 50, "fibre_g": 30}
ADVICE_NOT_LABEL = {"fibre_g"}

# Protein and fibre levels come from the UK nutrition claim conditions, the same
# rules behind the health benefits. Higher is better here, so High and Good show
# in green. "Good" is the level the regulation calls "source of": the plain word
# is easier to read. Below it, the level is "Low", in grey rather than green,
# because a low amount of protein or fibre is not a good thing.
CLAIM_LEVELS = {
    "protein_g": {"High protein": "High", "Source of protein": "Good"},
    "fibre_g": {"High fibre": "High", "Source of fibre": "Good"},
}

# How the health benefit names a "source of" claim on the page.
CLAIM_NAMES = {"Source of protein": "Good source of protein", "Source of fibre": "Good source of fibre"}


def nutrition_rows(nutrition, claims=()):
    """
    Per-serving rows for the page. Each row has a level and a % of a daily amount
    wherever a UK source gives one; carbohydrate has no official level.
    """
    rows = []
    for label, nutrient, unit in NUTRITION_ROWS:
        amount = nutrition["per_serving"][nutrient]
        light = nutrition["traffic_lights"].get(nutrient)
        light_label = LIGHT_LABELS.get(light, "")
        for claim, level in CLAIM_LEVELS.get(nutrient, {}).items():
            if claim in claims:
                light, light_label = "green", level
                break
        else:
            # Only say "Low" when every ingredient was found; otherwise the level is unknown.
            if nutrient in CLAIM_LEVELS and nutrition.get("is_complete"):
                light, light_label = "grey", "Low"

        ri_pct = nutrition["percent_reference_intake"].get(nutrient)
        if ri_pct is None and nutrient in EXTRA_DAILY_AMOUNTS:
            ri_pct = round(amount / EXTRA_DAILY_AMOUNTS[nutrient] * 100)

        rows.append({
            "label": label,
            "amount": round(amount, 1 if unit == "g" else 0),
            "unit": unit,
            "light": light,
            "light_label": light_label,
            "ri_pct": ri_pct,
            "ri_mark": "*" if nutrient in ADVICE_NOT_LABEL else "",
        })
    return rows


def everyday_or_treat(nutrition):
    """No red traffic lights: everyday. Any red: treat. Unknown when nutrition is incomplete."""
    if not nutrition["is_complete"]:
        return None
    return "treat" if "red" in nutrition["traffic_lights"].values() else "everyday"


# The meal style picker on the generate form (stored in preferences by its label).
MEAL_STYLES = {"Everyday healthy": "everyday", "Treat": "treat"}


def high_nutrients(nutrition):
    """['salt', 'fat'] for the nutrients with a red traffic light."""
    return [NUTRIENT_LABELS[n] for n, light in nutrition["traffic_lights"].items() if light == "red"]


def meal_style_check(nutrition, preferences):
    """
    Did the dish come out as the meal style the user asked for? Decided by the
    same traffic lights as the Everyday healthy / Treat tag, never by the AI.
    Returns None when the user had no preference.
    """
    chosen = MEAL_STYLES.get(preferences.get("meal_style"))
    if chosen is None:
        return None

    tag = everyday_or_treat(nutrition)
    if chosen == "treat":
        text = "You asked for a treat. Enjoy it now and then; the healthiest version below shows lighter swaps."
        if tag == "everyday":
            text = "You asked for a treat, and this one is also everyday healthy."
        return {"chosen": chosen, "met": True, "text": text}

    if tag is None:
        return {
            "chosen": chosen,
            "met": None,
            "text": "You asked for everyday healthy, but some ingredients weren't found in the food data, "
                    "so this couldn't be checked.",
        }
    if tag == "everyday":
        return {
            "chosen": chosen,
            "met": True,
            "text": "You asked for everyday healthy, and this dish has no high levels of fat, saturates, sugars or salt.",
        }
    return {
        "chosen": chosen,
        "met": False,
        "text": f"You asked for everyday healthy, but this dish is high in {' and '.join(high_nutrients(nutrition))}. "
                "The healthiest version below shows swaps that bring it down.",
    }


def meal_style_correction(insights):
    """
    The correction sent back to the AI when the user asked for everyday healthy
    and the dish came out high in something. Empty when there is nothing to fix.
    """
    style = (insights or {}).get("meal_style") or {}
    if style.get("chosen") != "everyday" or style.get("met") is not False:
        return ""
    highs = " and ".join(high_nutrients(insights["nutrition"]))
    return (
        f"The user asked for an everyday healthy dish, but it came out high in {highs} on the UK "
        "front-of-pack traffic lights. Use less oil, butter, ghee, cheese, cream, sugar, salt, stock cubes "
        "and processed meat, and no deep frying, so that fat, saturated fat, sugars and salt are all below "
        "the high levels."
    )


LEVEL_ORDER = {"Low": 0, "Good": 1, "High": 2}


def claim_level_words(claims, is_complete):
    """{'protein': 'High', 'fibre': 'Low'} from the claims; {} when nutrition is incomplete."""
    if not is_complete:
        return {}
    levels = {}
    for nutrient, key in (("protein", "protein_g"), ("fibre", "fibre_g")):
        levels[nutrient] = next(
            (level for claim, level in CLAIM_LEVELS[key].items() if claim in claims), "Low"
        )
    return levels


def version_check(expected, levels):
    """
    For a cooked version: red lines for every protein or fibre level that came out
    lower than its card expected. The AI writes the final quantities, so a cooked
    version can differ a little from the card; a lower level is worth saying.
    """
    problems = []
    for nutrient, expected_level in (expected.get("levels") or {}).items():
        actual = levels.get(nutrient)
        if actual and LEVEL_ORDER[actual] < LEVEL_ORDER.get(expected_level, 0):
            problems.append(
                f"{nutrient.capitalize()} came out {actual}, not {expected_level} as the card expected, "
                "because the recipe's amounts changed when it was written."
            )
    return problems


def recipe_basis(preferences, levels=None):
    """
    What the recipe on the page is, for the line above "One dish, three ways", so
    users don't mistake it for a fourth option. Settings are only listed for
    recipes made from the generate form (they have a meal style). For a cooked
    version, also what its card expected and anything that came out worse.
    """
    settings = []
    if "meal_style" in preferences:
        settings = [
            value for value in (
                preferences.get("nutrition_goal"),
                preferences.get("budget_level"),
                preferences.get("meal_style"),
            )
            if value and value != "No preference"
        ]
    expected = preferences.get("expected") or {}
    return {
        "version": preferences.get("recipe_version") or "",
        "based_on": preferences.get("based_on_title") or "",
        "settings": settings,
        "expected": expected,
        "problems": version_check(expected, levels or {}) if expected else [],
    }


def safe_three_ways(resolved, servings, preferences, extra_swaps=()):
    """The three versions, or [] if anything goes wrong; the rest of the panel still shows."""
    try:
        return three_ways(resolved, servings, preferences, extra_swaps)
    except Exception as error:
        print("CULINAAI THREE WAYS ERROR:", repr(error))
        traceback.print_exc()
        return []


def add_ai_swaps(insights, preferences):
    """
    Adds AI-suggested swaps (checked by code) to "One dish, three ways" for the
    final recipe only, so the generation loop's retries don't each pay for an AI
    call. If the AI call fails, the versions from the fixed list stay as they are.
    """
    if not (insights or {}).get("available"):
        return insights
    try:
        ingredients = insights["ingredients"]
        resolved = resolve_ingredients([IngredientInput(item["name"], item["grams"]) for item in ingredients])
        swaps, record = suggest_swaps(ingredients, resolved, preferences)
        insights["ai_swaps"] = record
        if swaps:
            insights["three_ways"] = safe_three_ways(resolved, insights["nutrition"]["servings"], preferences, swaps)
    except Exception as error:
        print("CULINAAI AI SWAPS ERROR:", repr(error))
        traceback.print_exc()
    return insights


def build_insights(structure_result, preferences, recipe_text):
    """
    structure_result: the dict from extract_recipe_structure, or None.
    Returns the insights dict; {"available": False, ...} when there is no structure.
    """
    if not structure_result or not structure_result.get("structure", {}).get("ingredients"):
        return {"version": INSIGHTS_VERSION, "available": False, "disclaimer": DISCLAIMER}

    structure = structure_result["structure"]
    ingredients = structure["ingredients"]
    names = [item["name"] for item in ingredients]

    # The user's chosen servings when there is one; otherwise what the recipe says.
    servings = preferences.get("servings") or structure.get("servings") or 1
    resolved = resolve_ingredients([IngredientInput(item["name"], item["grams"]) for item in ingredients])
    result = calculate_for_foods(resolved, servings)
    nutrition = nutrition_summary(result)
    claims = result.claims if result.is_complete else []

    return {
        "version": INSIGHTS_VERSION,
        "available": True,
        "ingredients": ingredients,
        "weight_warnings": structure_result.get("warnings", []),
        "ai_kcal_per_serving": structure.get("ai_kcal_per_serving"),
        "nutrition": nutrition,
        "nutrition_rows": nutrition_rows(nutrition, claims),
        "energy_kj_per_serving": round(nutrition["per_serving"]["energy_kj"]),
        "benefits": [
            {"claim": claim, "name": CLAIM_NAMES.get(claim, claim), "text": BENEFIT_SENTENCES[claim]}
            for claim in claims
        ],
        "tag": everyday_or_treat(nutrition),
        "meal_style": meal_style_check(nutrition, preferences),
        "cost": {
            "per_serving": result.cost_gbp_per_serving,
            "total": result.cost_gbp_total,
            "coverage_pct": result.cost_coverage_pct,
            "unmatched": result.cost_unmatched,
            "note": COST_NOTE,
        },
        "carbon": {
            "per_serving": result.carbon_kg_per_serving,
            "coverage_pct": result.carbon_coverage_pct,
            "unmatched": result.carbon_unmatched,
            "note": CARBON_NOTE,
        },
        "classic": compare_with_classic(structure, preferences),
        "three_ways": safe_three_ways(resolved, servings, preferences),
        "basis": recipe_basis(preferences, claim_level_words(claims, result.is_complete)),
        "allergens": allergens_in(names, {m.name: m.food_name for m in result.matched}),
        "hidden_allergens": hidden_allergen_alerts(names),
        "flags": safety_flags(names, recipe_text) + nutrition_flags(nutrition),
        "disclaimer": DISCLAIMER,
    }