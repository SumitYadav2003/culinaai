"""
The dashboard's impact cards and weekly balance, worked out by code from the
insights already stored with each generated recipe (RecipeHistory.insights).
No AI call, and no number that isn't on a recipe page already.

Two honest limits, shown on the page:
- These are recipes the user generated, not meals they ate.
- Savings compare a cooked version with the recipe it came from, as written.
"""

from datetime import timedelta

from django.utils import timezone

from .models import RecipeHistory

NUTRIENT_WORDS = {"fat_g": "fat", "saturates_g": "saturated fat", "sugars_g": "sugars", "salt_g": "salt"}
WEEK_DAYS = 7
MAX_RECIPES = 500  # plenty for one user; keeps the dashboard quick

# What a nudge suggests for each nutrient, pointing at features the user already has.
NUDGE_TIPS = {
    "salt_g": "Try “Use half the salt” on a Healthiest card, or pick Everyday healthy on the form.",
    "saturates_g": "Healthiest cards often swap butter, ghee or cream for oil or yogurt.",
    "sugars_g": "Healthiest cards can cut the sugar by a third in most sauces and puddings.",
    "fat_g": "Pick Everyday healthy on the form, or look at the Healthiest card.",
}


def level_of(insights, nutrient):
    """'High', 'Good' or 'Low' for protein or fibre from a recipe's stored rows; None if unknown."""
    label = {"protein": "Protein", "fibre": "Fibre"}[nutrient]
    for row in insights.get("nutrition_rows") or []:
        if row.get("label") == label:
            level = row.get("light_label") or None
            return "Good" if level == "Source" else level  # recipes saved before the word changed
    return None


def complete(insights):
    return bool(insights.get("available")) and bool((insights.get("nutrition") or {}).get("is_complete"))


def average(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def version_savings(items):
    """
    Totals for the versions the user cooked ("Cook this version"), compared with
    the recipe each came from, as written, for all its servings. A version that
    came out dearer counts against the total, so the figure is never flattering.
    """
    count, money, carbon = 0, 0.0, 0.0
    has_money = has_carbon = False
    for insights in items:
        expected = (insights.get("basis") or {}).get("expected") or {}
        original = expected.get("original") or {}
        if not (insights.get("basis") or {}).get("version") or not original:
            continue
        count += 1
        servings = (insights.get("nutrition") or {}).get("servings") or 1
        now_cost, was_cost = (insights.get("cost") or {}).get("per_serving"), original.get("cost")
        if now_cost is not None and was_cost is not None:
            money += (was_cost - now_cost) * servings
            has_money = True
        now_carbon, was_carbon = (insights.get("carbon") or {}).get("per_serving"), original.get("carbon")
        if now_carbon is not None and was_carbon is not None:
            carbon += (was_carbon - now_carbon) * servings
            has_carbon = True
    return {
        "count": count,
        "money": round(money, 2) if has_money else None,
        "carbon": round(carbon, 2) if has_carbon else None,
    }


def weekly_balance(items):
    """
    The last 7 days of recipes with complete nutrition: how many were everyday
    healthy, which nutrients came out high, protein and fibre levels, and nudges.
    """
    recipes = [insights for insights in items if complete(insights)]
    total = len(recipes)
    everyday = sum(1 for insights in recipes if insights.get("tag") == "everyday")

    high_counts = {
        nutrient: sum(1 for insights in recipes if insights["nutrition"]["traffic_lights"].get(nutrient) == "red")
        for nutrient in NUTRIENT_WORDS
    }
    protein = {level: sum(1 for i in recipes if level_of(i, "protein") == level) for level in ("High", "Good", "Low")}
    low_fibre = sum(1 for insights in recipes if level_of(insights, "fibre") == "Low")

    nudges = []
    if total >= 2:
        for nutrient, count in sorted(high_counts.items(), key=lambda pair: -pair[1]):
            if count * 2 >= total and count:
                nudges.append({
                    "warning": True,
                    "text": f"{count} of your {total} recipes this week were high in {NUTRIENT_WORDS[nutrient]}. "
                            f"{NUDGE_TIPS[nutrient]}",
                })
        if low_fibre * 2 >= total and low_fibre:
            nudges.append({
                "warning": True,
                "text": f"{low_fibre} of your {total} recipes this week were low in fibre. "
                        "Brown rice, wholewheat pasta, beans and lentils add fibre.",
            })
        if not nudges and everyday == total:
            nudges.append({"warning": False, "text": f"All {total} of your recipes this week were everyday healthy."})

    return {
        "total": total,
        "everyday": everyday,
        "treat": total - everyday,
        "high": [
            {"nutrient": NUTRIENT_WORDS[nutrient], "count": count}
            for nutrient, count in high_counts.items() if count
        ],
        "protein": protein,
        "low_fibre": low_fibre,
        "nudges": nudges,
    }


def build_impact_context(user):
    """Everything the dashboard's impact section needs, as plain values."""
    rows = list(
        RecipeHistory.objects.filter(user=user)
        .order_by("-created_at")
        .values_list("insights", "created_at")[:MAX_RECIPES]
    )
    all_items = [insights for insights, _ in rows if isinstance(insights, dict) and insights.get("available")]
    week_start = timezone.now() - timedelta(days=WEEK_DAYS)
    week_items = [
        insights for insights, created in rows
        if created >= week_start and isinstance(insights, dict) and insights.get("available")
    ]

    with_nutrition = [insights for insights in all_items if complete(insights)]
    return {
        "impact": {
            "recipes": len(all_items),
            "judged": len(with_nutrition),
            "everyday": sum(1 for insights in with_nutrition if insights.get("tag") == "everyday"),
            "average_cost": average([(i.get("cost") or {}).get("per_serving") for i in all_items]),
            "average_carbon": average([(i.get("carbon") or {}).get("per_serving") for i in all_items]),
            "versions": version_savings(all_items),
        },
        "week": weekly_balance(week_items),
    }


# ---------------------------------------------------------------------------
# A worked example for the SDG page: one real swap, recalculated live by code
# ---------------------------------------------------------------------------

# A classic family spaghetti bolognese (the same one as the hand-checked recipes in tests).
EXAMPLE_TITLE = "Spaghetti bolognese for 4"
EXAMPLE_RECIPE = [
    ("beef mince", 500), ("spaghetti", 400), ("chopped tomatoes", 400), ("onion", 150), ("carrot", 100),
    ("garlic", 10), ("olive oil", 15), ("parmesan", 30), ("tomato puree", 30),
]
EXAMPLE_SERVINGS = 4
EXAMPLE_SWAP = ("18-469", "13-657")  # half the beef mince for red lentils (ingredient_swaps.csv)
WEEKS_IN_A_YEAR = 52


def dish_figures(result):
    return {
        "cost": result.cost_gbp_per_serving,
        "carbon": result.carbon_kg_per_serving,
        "kcal": round(result.per_serving["energy_kcal"]),
        "saturates": round(result.per_serving["saturates_g"], 1),
        "fibre": round(result.per_serving["fibre_g"], 1),
        "everyday": "red" not in result.traffic_lights.values(),
    }


def swap_example():
    """
    Before and after for one swap on one dish, with what it adds up to if a family
    of 4 had it once a week for a year. Worked out from the current data each time
    the page loads, so it can never go stale. None if anything is missing.
    """
    from nutrition.models import CofidFood
    from nutrition.services import IngredientInput, calculate_for_foods, resolve_ingredients

    from .swap_service import apply_swap, load_swaps

    try:
        resolved = resolve_ingredients([IngredientInput(name, grams) for name, grams in EXAMPLE_RECIPE])
        swap = next(s for s in load_swaps() if (s.from_code, s.to_code) == EXAMPLE_SWAP)
        new_food = CofidFood.objects.select_related("carbon_category").get(food_code=swap.to_code)
        before = calculate_for_foods(resolved, EXAMPLE_SERVINGS)
        after = calculate_for_foods(apply_swap(resolved, swap, new_food), EXAMPLE_SERVINGS)
        if None in (before.cost_gbp_per_serving, after.cost_gbp_per_serving,
                    before.carbon_kg_per_serving, after.carbon_kg_per_serving):
            return None
    except Exception as error:  # missing data should hide the example, never break the page
        print("CULINAAI SWAP EXAMPLE ERROR:", repr(error))
        return None

    meals = EXAMPLE_SERVINGS * WEEKS_IN_A_YEAR
    money = before.cost_gbp_per_serving - after.cost_gbp_per_serving
    carbon = before.carbon_kg_per_serving - after.carbon_kg_per_serving
    return {
        "title": EXAMPLE_TITLE,
        "swap": swap.text.format(**{"from": "beef mince"}),
        "note": swap.note,
        "before": dish_figures(before),
        "after": dish_figures(after),
        "per_serving": {"money": round(money, 2), "carbon": round(carbon, 2)},
        # Unrounded, for the page's "your household" sliders, so they match the year figures.
        "per_serving_exact": {"money": round(money, 4), "carbon": round(carbon, 4)},
        "people": EXAMPLE_SERVINGS,
        "year": {"meals": meals, "money": round(money * meals), "carbon": round(carbon * meals)},
    }
