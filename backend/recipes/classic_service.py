"""
"Compared with the classic": when a recipe is a version of a known dish, list
the classic's core ingredients that this version leaves out, each with a reason.

Who decides what:
- Which items are missing: code, by comparing the classic's core list with the
  recipe's own ingredients. The AI's word is not taken for it.
- Allergy or diet: code, from the user's expanded avoid terms. This is the one
  place a restricted ingredient may be named, because the section exists to
  explain that it was left out.
- Every other reason is suggested by the AI and must pass its rule below
  (e.g. a "healthier swap" must lower fat, saturates, sugars, salt or energy in
  the computed numbers). A reason that fails is replaced by what code can
  prove, and the failure is reported to quality gate 10.
"""

from nutrition.services import find_by_alias, find_by_words, load_foods_for_matching, words_of

from .ai_service import split_user_items
from .recipe_quality_engine import contains_term, expand_allergy_terms, get_restricted_diet_terms
from .risk_service import hidden_products_for_allergies

REASON_LABELS = {
    "allergy_diet": "Allergy or diet setting",
    "not_in_your_ingredients": "Not in your ingredients",
    "equipment": "Equipment",
    "time_limit": "Time limit",
    "budget": "Budget",
    "healthier_swap": "Healthier swap",
    "style_choice": "Style choice",
    "none_given": "No reason given",
}

# Too basic to list as "missing" from a classic.
BASIC_ITEMS = {"salt", "pepper", "black pepper", "water", "oil"}

SWAP_NUTRIENTS = {"energy_kcal": "energy", "fat_g": "fat", "saturates_g": "saturated fat", "sugars_g": "sugars", "salt_g": "salt"}


def same_ingredient(a, b):
    """'beef mince' matches 'lean beef mince'; 'parmesan' matches 'parmesan cheese'."""
    words_a, words_b = words_of(a), words_of(b)
    return bool(words_a) and bool(words_b) and (words_a <= words_b or words_b <= words_a)


def is_in(item, names):
    return any(same_ingredient(item, name) for name in names)


def user_avoid_terms(preferences):
    """The user's allergies (expanded, plus hidden-allergen products) and diet restrictions."""
    allergies = split_user_items(preferences.get("allergies"))
    terms = set(expand_allergy_terms(allergies))
    terms.update(hidden_products_for_allergies(preferences.get("allergies")))
    terms.update(get_restricted_diet_terms(preferences.get("diet_preferences") or []))
    return sorted(term for term in terms if term)


def food_for(name, foods):
    return find_by_alias(name) or find_by_words(name, foods)


def lowered_nutrients(removed, replacement, foods):
    """Nutrients (per 100 g) where the replacement is lower than the removed item."""
    old, new = food_for(removed, foods), food_for(replacement, foods)
    if not old or not new:
        return []
    lowered = []
    for field, label in SWAP_NUTRIENTS.items():
        before, after = getattr(old, field), getattr(new, field)
        if before is not None and after is not None and after < before:
            lowered.append(label)
    return lowered


def check_reason(item, suggestion, preferences, classic, foods):
    """
    Returns (ok, detail) for the AI's suggested reason for one missing item.
    `detail` is the sentence shown to the user when the reason is accepted.
    """
    reason = suggestion.get("reason", "none_given")
    user_items = split_user_items(preferences.get("ingredients"))
    equipment = " | ".join(preferences.get("cooking_equipment") or [])

    if reason == "not_in_your_ingredients":
        return (not is_in(item, user_items), "Not in your ingredients list.")
    if reason == "equipment":
        needed = suggestion.get("equipment", "")
        ok = bool(needed) and bool(equipment) and not contains_term(equipment, needed)
        return (ok, f"Needs a {needed}, which you didn't select.")
    if reason == "time_limit":
        usual, limit = classic.get("usual_minutes"), preferences.get("cooking_time_minutes")
        ok = bool(usual) and bool(limit) and int(limit) < usual
        return (ok, f"The classic method takes about {usual} minutes; your limit was {limit}.")
    if reason == "budget":
        return ("low" in str(preferences.get("budget_level", "")).lower(), "You chose a low budget.")
    if reason == "healthier_swap":
        replacement = suggestion.get("replaced_with", "")
        lowered = lowered_nutrients(item, replacement, foods) if replacement else []
        return (bool(lowered), f"Swapped for {replacement}, which is lower in {', '.join(lowered)} per 100 g.")
    if reason == "style_choice":
        note = suggestion.get("note", "")
        return (bool(note), note)
    return (False, "")  # allergy_diet claimed without a match, or none_given


def compare_with_classic(structure, preferences):
    """
    Returns {"is_classic", "classic_name", "items": [...], "issues": [...]} or
    {"is_classic": False} when the dish is not a recognised classic.
    `issues` lists reasons that failed their rule (used by quality gate 10).
    """
    classic = structure.get("classic") or {}
    if not classic.get("is_classic"):
        return {"is_classic": False, "items": [], "issues": []}

    recipe_names = [ingredient["name"] for ingredient in structure.get("ingredients", [])]
    avoid_terms = user_avoid_terms(preferences)
    user_items = split_user_items(preferences.get("ingredients"))
    suggestions = classic.get("missing") or []
    foods = load_foods_for_matching()

    items, issues = [], []
    for core in classic.get("core_ingredients", []):
        if core in BASIC_ITEMS or is_in(core, recipe_names):
            continue

        suggestion = next((s for s in suggestions if same_ingredient(s["ingredient"], core)), {})
        ai_reason = suggestion.get("reason", "none_given")

        if any(contains_term(core, term) for term in avoid_terms):
            reason, detail, ok = "allergy_diet", "Left out because of your allergy or diet settings.", True
        else:
            ok, detail = check_reason(core, suggestion, preferences, classic, foods)
            reason = ai_reason
            if not ok:
                issues.append({
                    "ingredient": core,
                    "ai_reason": ai_reason,
                    "problem": f"'{REASON_LABELS[ai_reason]}' could not be confirmed for {core}.",
                })
                # Show only what code can prove.
                if not is_in(core, user_items):
                    reason, detail = "not_in_your_ingredients", "Not in your ingredients list."
                else:
                    reason, detail = "none_given", "This version leaves it out."

        items.append({
            "ingredient": core,
            "reason": reason,
            "label": REASON_LABELS[reason],
            "detail": detail,
            "can_add_back": reason != "allergy_diet",
        })

    return {
        "is_classic": True,
        "classic_name": classic.get("classic_name", ""),
        "items": items,
        "issues": issues,
    }
