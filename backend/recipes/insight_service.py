"""
Everything the recipe page says about health, cost, carbon and risk, worked
out by code from the structured ingredients (structure_service.py):

- nutrition, traffic lights, cost and carbon (nutrition/services.py)
- health benefits: only claims the numbers qualify for, as fixed sentences
- "Everyday healthy" or "Treat", decided by the traffic lights, not the AI
- "Compared with the classic" (classic_service.py)
- allergens, hidden allergens and safety flags (risk_service.py)
- the fixed disclaimer

The result is a plain dict, so it can be kept in the session and in a JSONField.
"""

from nutrition.services import IngredientInput, calculate_nutrition

from .classic_service import compare_with_classic
from .risk_service import allergens_in, hidden_allergen_alerts, nutrition_flags, safety_flags

INSIGHTS_VERSION = 1

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
    "About this figure: global averages per kg of food from Poore & Nemecek (2018), not specific to UK "
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


def nutrition_rows(nutrition):
    """Per-serving rows for the page, each with its traffic light and % reference intake where one exists."""
    rows = []
    for label, nutrient, unit in NUTRITION_ROWS:
        light = nutrition["traffic_lights"].get(nutrient)
        rows.append({
            "label": label,
            "amount": round(nutrition["per_serving"][nutrient], 1 if unit == "g" else 0),
            "unit": unit,
            "light": light,
            "light_label": LIGHT_LABELS.get(light, ""),
            "ri_pct": nutrition["percent_reference_intake"].get(nutrient),
        })
    return rows


def everyday_or_treat(nutrition):
    """No red traffic lights: everyday. Any red: treat. Unknown when nutrition is incomplete."""
    if not nutrition["is_complete"]:
        return None
    return "treat" if "red" in nutrition["traffic_lights"].values() else "everyday"


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
    result = calculate_nutrition(
        [IngredientInput(item["name"], item["grams"]) for item in ingredients],
        servings,
    )
    nutrition = nutrition_summary(result)
    claims = result.claims if result.is_complete else []

    return {
        "version": INSIGHTS_VERSION,
        "available": True,
        "ingredients": ingredients,
        "weight_warnings": structure_result.get("warnings", []),
        "ai_kcal_per_serving": structure.get("ai_kcal_per_serving"),
        "nutrition": nutrition,
        "nutrition_rows": nutrition_rows(nutrition),
        "energy_kj_per_serving": round(nutrition["per_serving"]["energy_kj"]),
        "benefits": [{"claim": claim, "text": BENEFIT_SENTENCES[claim]} for claim in claims],
        "tag": everyday_or_treat(nutrition),
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
        "allergens": allergens_in(names, {m.name: m.food_name for m in result.matched}),
        "hidden_allergens": hidden_allergen_alerts(names),
        "flags": safety_flags(names, recipe_text) + nutrition_flags(nutrition),
        "disclaimer": DISCLAIMER,
    }
