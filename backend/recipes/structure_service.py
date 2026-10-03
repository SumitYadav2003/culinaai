"""
Structured data for a finished recipe.

The recipe itself is still written as plain text (the 8-gate engine checks that
text). This module makes one extra, small AI call that reads the finished recipe
and returns JSON in a fixed shape (OpenAI structured outputs):

- every ingredient with a weight in grams, so code can calculate nutrition,
  cost and carbon (the AI never supplies those numbers itself)
- whether the dish is a recognised classic, its core ingredients, and a
  suggested reason for each classic ingredient that is missing

Nothing here is trusted as it arrives. `clean_structure` checks every field, and
the reasons are verified later by code (classic_service.py).
"""

import json

from django.conf import settings
from openai import OpenAI

MODEL = "gpt-4.1-mini"
MAX_INGREDIENTS = 30
MAX_CLASSIC_ITEMS = 10
MAX_GRAMS = 5000  # a single ingredient above 5 kg is treated as a mistake

# The reasons the AI may suggest. Code decides which ones stand (classic_service.py).
REASON_CODES = [
    "allergy_diet",
    "not_in_your_ingredients",
    "equipment",
    "time_limit",
    "budget",
    "healthier_swap",
    "style_choice",
    "none_given",
]

STRUCTURE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ingredients", "servings", "ai_kcal_per_serving", "classic"],
    "properties": {
        "servings": {"type": "integer"},
        "ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "display", "grams"],
                "properties": {
                    "name": {"type": "string"},
                    "display": {"type": "string"},
                    "grams": {"type": "number"},
                },
            },
        },
        "ai_kcal_per_serving": {"type": "number"},
        "classic": {
            "type": "object",
            "additionalProperties": False,
            "required": ["is_classic", "classic_name", "core_ingredients", "usual_minutes", "missing"],
            "properties": {
                "is_classic": {"type": "boolean"},
                "classic_name": {"type": "string"},
                "core_ingredients": {"type": "array", "items": {"type": "string"}},
                "usual_minutes": {"type": ["integer", "null"]},
                "missing": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["ingredient", "reason", "replaced_with", "equipment", "note"],
                        "properties": {
                            "ingredient": {"type": "string"},
                            "reason": {"type": "string", "enum": REASON_CODES},
                            "replaced_with": {"type": "string"},
                            "equipment": {"type": "string"},
                            "note": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
}


def build_structure_prompt(recipe_text, preferences):
    """The extraction prompt: the finished recipe plus the user's constraints."""
    return f"""
You read a finished recipe and return its data as JSON. Do not change the recipe.

USER CONSTRAINTS (for the reasons below):
- Ingredients the user has: {preferences.get("ingredients") or "not given"}
- Allergies or ingredients to avoid: {preferences.get("allergies") or "none"}
- Diet: {", ".join(preferences.get("diet_preferences") or []) or "none"}
- Cooking equipment: {", ".join(preferences.get("cooking_equipment") or []) or "not given"}
- Time limit: {preferences.get("cooking_time_minutes") or "not given"} minutes
- Budget: {preferences.get("budget_level") or "not given"}

INGREDIENTS:
- List every ingredient in the recipe once.
- name: the plain everyday name, singular, lower case, no quantity or preparation
  (e.g. "chicken breast", "red onion", "olive oil", "chopped tomato").
- display: the quantity as the recipe writes it (e.g. "2 fillets", "1 tbsp").
- grams: the weight in grams for the WHOLE recipe, as bought and raw. Liquids: 1 ml = 1 g.
  Tins of beans or fish: the drained weight. "To taste" items: a small realistic amount
  (salt 2, pepper 1). Be realistic: 1 medium onion is about 150 g, 1 garlic clove about 5 g,
  1 tbsp oil about 14 g, 1 tsp ground spice about 2 g, 1 egg about 58 g.

servings: the number of servings the recipe states.

ai_kcal_per_serving: your own estimate of the calories in one serving.

CLASSIC DISH:
- is_classic: true only if this is a version of a widely recognised named dish
  (e.g. spaghetti bolognese, chicken tikka masala, chicken burger, carbonara).
  "Whatever's in the fridge" dishes are not classics.
- classic_name: the classic dish's usual name, or "" if not a classic.
- core_ingredients: the classic version's core ingredients only (no optional garnish),
  at most 10, plain names. [] if not a classic.
- usual_minutes: the usual total time of the classic method, or null.
- missing: for each core ingredient that is NOT in this recipe, one entry:
  - reason: one of allergy_diet, not_in_your_ingredients, equipment, time_limit, budget,
    healthier_swap, style_choice, none_given
  - replaced_with: the ingredient used instead, or "" if none
  - equipment: the equipment it would need, or ""
  - note: a short plain reason, at most 15 words. No health or medical claims.

RECIPE:
{recipe_text}
""".strip()


def clean_text(value, limit):
    return " ".join(str(value or "").split())[:limit]


def clean_structure(raw):
    """
    Checks and tidies the AI's JSON. Returns (structure, warnings).
    Anything malformed is dropped with a warning rather than guessed.
    """
    warnings = []
    raw = raw if isinstance(raw, dict) else {}

    ingredients = []
    for item in (raw.get("ingredients") or [])[:MAX_INGREDIENTS]:
        if not isinstance(item, dict):
            continue
        name = clean_text(item.get("name"), 60).lower()
        if not name:
            continue
        try:
            grams = float(item.get("grams"))
        except (TypeError, ValueError):
            grams = 0.0
        if grams <= 0 or grams > MAX_GRAMS:
            warnings.append(f"Weight for '{name}' looked wrong ({item.get('grams')} g) and was not used.")
            grams = 0.0
        ingredients.append({"name": name, "display": clean_text(item.get("display"), 40), "grams": round(grams, 1)})

    classic_raw = raw.get("classic") if isinstance(raw.get("classic"), dict) else {}
    is_classic = classic_raw.get("is_classic") is True
    core = [clean_text(c, 60).lower() for c in (classic_raw.get("core_ingredients") or []) if clean_text(c, 60)]
    usual_minutes = classic_raw.get("usual_minutes")
    usual_minutes = usual_minutes if isinstance(usual_minutes, int) and 0 < usual_minutes < 24 * 60 else None

    missing = []
    for item in classic_raw.get("missing") or []:
        if not isinstance(item, dict):
            continue
        ingredient = clean_text(item.get("ingredient"), 60).lower()
        if not ingredient:
            continue
        reason = item.get("reason") if item.get("reason") in REASON_CODES else "none_given"
        missing.append({
            "ingredient": ingredient,
            "reason": reason,
            "replaced_with": clean_text(item.get("replaced_with"), 60).lower(),
            "equipment": clean_text(item.get("equipment"), 40).lower(),
            "note": clean_text(item.get("note"), 120),
        })

    try:
        ai_kcal = float(raw.get("ai_kcal_per_serving"))
    except (TypeError, ValueError):
        ai_kcal = None

    servings = raw.get("servings")
    structure = {
        "ingredients": ingredients,
        "servings": servings if isinstance(servings, int) and 0 < servings <= 50 else None,
        "ai_kcal_per_serving": ai_kcal if ai_kcal and 0 < ai_kcal < 10000 else None,
        "classic": {
            "is_classic": is_classic and bool(core),
            "classic_name": clean_text(classic_raw.get("classic_name"), 80) if is_classic else "",
            "core_ingredients": core[:MAX_CLASSIC_ITEMS] if is_classic else [],
            "usual_minutes": usual_minutes,
            "missing": missing if is_classic else [],
        },
    }
    return structure, warnings


def extract_recipe_structure(recipe_text, preferences):
    """
    Returns {"structure": ..., "warnings": [...]} for a finished recipe,
    or None if the AI call fails. A failure never blocks the recipe; the page
    then says nutrition is not available.
    """
    if not settings.OPENAI_API_KEY or not recipe_text:
        return None

    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.responses.create(
            model=MODEL,
            input=build_structure_prompt(recipe_text, preferences),
            temperature=0,
            max_output_tokens=1500,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "recipe_structure",
                    "schema": STRUCTURE_SCHEMA,
                    "strict": True,
                }
            },
        )
        raw = json.loads(response.output_text)
    except Exception as error:  # network, quota or malformed JSON: carry on without data
        print("CULINAAI STRUCTURE EXTRACTION ERROR:", repr(error))
        return None

    structure, warnings = clean_structure(raw)
    return {"structure": structure, "warnings": warnings}
