"""
AI-suggested swaps for "One dish, three ways": the AI proposes, code verifies.

The fixed swap list (ingredient_swaps.csv) is reliable but small and knows
nothing about the dish. So one small AI call reads the recipe's ingredients and
suggests swaps that suit this dish ("mushrooms for half the chicken").

The AI only names ingredients. It never gives a price, carbon figure, calorie or
health claim. Each suggestion must pass every check in check_suggestions, or it
is dropped (and the reason kept, for evaluation):

1. "from" is an ingredient of this recipe that was found in the food data
2. "to" is found in the food data too (aliases or the word match), and is a
   different food
3. the amount is one of: all, half, or "less" (use half, nothing added)
4. the new ingredient is safe for the user's allergies and diet (the same rules
   as the quality gates)
5. the weight of the new ingredient per 100 g replaced is between 25 and 150 g
6. the cooking note has no medical or health claim (gate 9's patterns) and is short

What survives goes into swap_service.three_ways next to the fixed list, where code
works out every number and picks the cheapest, healthiest and greenest versions.
"""

import json

from django.conf import settings
from openai import OpenAI

from nutrition.services import IngredientInput, resolve_ingredients

from .classic_service import same_ingredient
from .recipe_quality_engine import find_health_claims
from .structure_service import clean_text
from .swap_service import Swap, is_safe_for_user

MODEL = "gpt-4.1-mini"
MAX_SUGGESTIONS = 8
AMOUNTS = {"all": 1.0, "half": 0.5, "less": 0.5}
MIN_GRAMS_PER_100G, MAX_GRAMS_PER_100G = 25, 150

SUGGESTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["suggestions"],
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["from", "to", "amount", "grams_per_100g", "note"],
                "properties": {
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                    "amount": {"type": "string", "enum": list(AMOUNTS)},
                    "grams_per_100g": {"type": "number"},
                    "note": {"type": "string"},
                },
            },
        },
    },
}

TEXT_TEMPLATES = {
    "all": "Use {to} instead of {{from}}",
    "half": "Swap half the {{from}} for {to}",
    "less": "Use half the {{from}}",
}


def build_swap_prompt(ingredients, preferences):
    lines = "\n".join(f"- {item['name']} ({item.get('display') or str(item['grams']) + ' g'})" for item in ingredients)
    return f"""
You help a UK home cook make one dish cheaper, healthier or lower in carbon by swapping ingredients.

Suggest up to {MAX_SUGGESTIONS} swaps for THIS dish. Each swap must keep it recognisably the same dish,
and suit its cuisine and cooking method. Prefer everyday ingredients sold in UK supermarkets.

Rules:
- "from" must be copied exactly from the ingredient list below.
- "to" is the plain name of one raw ingredient as a shopper would say it (e.g. "chickpeas", "brown rice").
  For "less", leave "to" empty.
- "amount": "all" replaces all of it, "half" replaces half, "less" means use half and add nothing.
- "grams_per_100g": grams of the new ingredient for each 100 g replaced (100 for a like-for-like swap,
  about 40 for dried lentils replacing meat). Use 0 for "less".
- "note": one short practical cooking tip (under 15 words), or empty. No health or nutrition claims.
- Do not give prices, calories, carbon figures or health claims. Code works those out.
- Never suggest anything that conflicts with these:
  Allergies or ingredients to avoid: {preferences.get("allergies") or "None provided"}
  Diet preferences: {", ".join(preferences.get("diet_preferences") or []) or "None"}

Ingredients:
{lines}
""".strip()


def ask_ai_for_swaps(ingredients, preferences):
    """The AI's raw suggestions (a list of dicts), or None if the call fails."""
    if not settings.OPENAI_API_KEY or not ingredients:
        return None
    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.responses.create(
            model=MODEL,
            input=build_swap_prompt(ingredients, preferences),
            temperature=0,
            max_output_tokens=800,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "ingredient_swaps",
                    "schema": SUGGESTION_SCHEMA,
                    "strict": True,
                }
            },
        )
        return json.loads(response.output_text).get("suggestions") or []
    except Exception as error:  # network, quota or malformed JSON: the fixed list still works
        print("CULINAAI SWAP SUGGESTION ERROR:", repr(error))
        return None


def check_suggestions(raw, resolved, preferences):
    """
    Turns the AI's suggestions into Swaps, keeping only those that pass every check.
    Returns (swaps, rejected) where rejected is [{"suggestion": ..., "reason": ...}].
    """
    swaps, rejected, seen = [], [], set()

    def reject(item, reason):
        rejected.append({"suggestion": f"{item.get('from', '')} -> {item.get('to', '')}", "reason": reason})

    for item in (raw or [])[:MAX_SUGGESTIONS]:
        if not isinstance(item, dict):
            continue
        from_name = clean_text(item.get("from"), 60).lower()
        to_name = clean_text(item.get("to"), 60).lower().replace("{", "").replace("}", "")
        amount = item.get("amount")

        line = next((r for r in resolved if r.food and same_ingredient(r.name, from_name)), None)
        if line is None:
            reject(item, "Not an ingredient of this recipe that is in the food data")
            continue
        if amount not in AMOUNTS:
            reject(item, "Amount must be all, half or less")
            continue

        new_food, ratio = None, 0.0
        if amount != "less":
            new_food = resolve_ingredients([IngredientInput(to_name, 100)])[0].food if to_name else None
            if new_food is None:
                reject(item, "New ingredient not found in the food data")
                continue
            if new_food.food_code == line.food.food_code:
                reject(item, "Same food as the original")
                continue
            try:
                grams = float(item.get("grams_per_100g"))
            except (TypeError, ValueError):
                grams = 0.0
            if not MIN_GRAMS_PER_100G <= grams <= MAX_GRAMS_PER_100G:
                reject(item, "Amount of the new ingredient looked wrong")
                continue
            ratio = grams / 100
            probe = Swap(line.food.food_code, new_food.food_code, AMOUNTS[amount], ratio, to_name, "", "", "ai")
            if not is_safe_for_user(probe, new_food, preferences):
                reject(item, "Clashes with the user's allergies or diet")
                continue

        note = clean_text(item.get("note"), 100)
        if find_health_claims(note):
            note = ""  # the swap may still be fine; the claim is not

        key = (line.food.food_code, new_food.food_code if new_food else "", AMOUNTS[amount])
        if key in seen:
            continue
        seen.add(key)
        swaps.append(Swap(
            from_code=line.food.food_code,
            to_code=new_food.food_code if new_food else "",
            share=AMOUNTS[amount],
            ratio=ratio,
            to_name=to_name if new_food else "",
            text=TEXT_TEMPLATES[amount].format(to=to_name),
            note=note,
            source="ai",
        ))
    return swaps, rejected


def suggest_swaps(ingredients, resolved, preferences):
    """
    The checked AI swaps for one recipe and a short record of what happened:
    (swaps, {"suggested": n, "accepted": n, "rejected": [...]}). Never raises.
    """
    raw = ask_ai_for_swaps(ingredients, preferences)
    if raw is None:
        return [], {"suggested": 0, "accepted": 0, "rejected": [], "available": False}
    swaps, rejected = check_suggestions(raw, resolved, preferences)
    return swaps, {"suggested": len(raw), "accepted": len(swaps), "rejected": rejected, "available": True}
