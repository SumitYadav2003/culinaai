"""
"One dish, three ways": the cheapest, the healthiest and the greenest version of
a recipe, each made from at most three ingredient swaps.

Who decides what:
- Which swaps exist: a fixed, hand-checked list (nutrition/data/ingredient_swaps.csv),
  e.g. "swap half the beef mince for red lentils", plus any swaps the AI suggests
  for this dish that pass the code's checks (swap_suggestion_service.py). The AI
  never supplies a number.
- Which swaps are allowed for this user: code. A swap is skipped when the new
  ingredient clashes with the user's allergies or diet (the same rules the
  quality gates use).
- Which swaps each version uses, and every number shown: code. Each swap is tried,
  the whole dish is recalculated (nutrition/services.py), and the swap that helps
  most is kept, up to three.

What "cheapest", "healthiest" and "greenest" mean:
- Cheapest: lowest cost per serving. A swap may not turn any of fat, saturates,
  sugars or salt to a worse traffic light.
- Greenest: lowest kg CO2e per serving, with the same traffic-light rule.
- Healthiest: lowest health score (health_score below), which uses the UK
  traffic lights and fibre. It may cost more; the page shows that trade-off.
"""

import csv
from dataclasses import dataclass, replace
from functools import lru_cache

from nutrition.management.commands.load_cofid import DATA_DIR
from nutrition.models import CofidFood
from nutrition.services import TRAFFIC_LIGHT_THRESHOLDS, ResolvedIngredient, calculate_for_foods

from .classic_service import user_avoid_terms
from .recipe_quality_engine import contains_term
from .risk_service import allergens_for_user_allergies, allergens_in

SWAPS_CSV = DATA_DIR / "ingredient_swaps.csv"

# At most three swaps, so each version is still recognisably the same dish.
MAX_SWAPS = 3

# A swap must help by at least this much per serving to be worth suggesting.
MIN_GAIN = {"cheapest": 0.02, "greenest": 0.01, "healthiest": 0.02}  # £, kg CO2e, health points

LIGHT_POINTS = {"green": 0, "amber": 1, "red": 2}
LIGHT_WORDS = {"green": "Low", "amber": "Medium", "red": "High"}
NUTRIENT_WORDS = {"fat_g": "fat", "saturates_g": "saturates", "sugars_g": "sugars", "salt_g": "salt"}
HIGH_FIBRE_PER_100G = 6.0  # UK "high fibre" claim condition

VERSIONS = [
    ("cheapest", "Cheapest", "bi-piggy-bank"),
    ("healthiest", "Healthiest", "bi-heart-pulse"),
    ("greenest", "Greenest", "bi-tree"),
]

NO_SWAP_MESSAGES = {
    "cheapest": "No swap on our list makes this dish cheaper without making it less healthy.",
    "healthiest": "No swap on our list makes this dish healthier.",
    "greenest": "No swap on our list lowers this dish's carbon without making it less healthy.",
}
NOT_ENOUGH_DATA = {
    "cheapest": "Not shown, because no ingredient in this dish has a price.",
    "healthiest": "Not shown, because some ingredients weren't found in the food data.",
    "greenest": "Not shown, because no ingredient in this dish has a carbon figure.",
}


@dataclass(frozen=True)
class Swap:
    from_code: str
    to_code: str  # empty: "use less" of the original, with nothing added
    share: float  # share of the original amount that is replaced or removed
    ratio: float  # grams of the new food for each gram replaced
    to_name: str
    text: str  # "Swap half the {from} for red lentils"
    note: str
    source: str = "list"  # "list" (ingredient_swaps.csv) or "ai" (swap_suggestion_service.py, checked by code)


@lru_cache(maxsize=1)
def load_swaps():
    with SWAPS_CSV.open(encoding="utf-8") as handle:
        return tuple(
            Swap(
                row["from_code"], row["to_code"], float(row["share"]), float(row["ratio"]),
                row["to_name"], row["text"], row["note"],
            )
            for row in csv.DictReader(handle)
        )


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def health_score(result):
    """
    Lower is healthier. Each medium traffic light counts 1 and each high one 2,
    plus how close fat, saturates, sugars and salt are on average to the "high"
    level per 100 g, minus up to half a point for fibre (full half at the UK
    "high fibre" level of 6 g per 100 g).
    """
    lights = sum(LIGHT_POINTS[light] for light in result.traffic_lights.values())
    closeness = sum(
        result.per_100g[nutrient] / TRAFFIC_LIGHT_THRESHOLDS[nutrient][1] for nutrient in TRAFFIC_LIGHT_THRESHOLDS
    ) / len(TRAFFIC_LIGHT_THRESHOLDS)
    fibre_bonus = 0.5 * min(result.per_100g["fibre_g"] / HIGH_FIBRE_PER_100G, 1.0)
    return lights + closeness - fibre_bonus


def measure(goal, result):
    """
    The number each version tries to lower, per serving, or None when there is no
    figure. Cost and carbon add up the ingredients (kept to 3 decimals) rather than
    the dish total, which is rounded to 2, so small savings are not lost to rounding.
    """
    if goal == "cheapest":
        if result.cost_gbp_total is None:
            return None
        return sum(m.cost_gbp for m in result.matched if m.cost_gbp is not None) / result.servings
    if goal == "greenest":
        if result.carbon_kg_total is None:
            return None
        return sum(m.carbon_kg for m in result.matched if m.carbon_kg is not None) / result.servings
    return health_score(result)


def lights_got_worse(result, original):
    return any(
        LIGHT_POINTS[result.traffic_lights[n]] > LIGHT_POINTS[original.traffic_lights[n]]
        for n in TRAFFIC_LIGHT_THRESHOLDS
    )


# ---------------------------------------------------------------------------
# Which swaps apply
# ---------------------------------------------------------------------------

def is_safe_for_user(swap, food, preferences):
    """False when the new ingredient clashes with the user's allergies or diet."""
    if not swap.to_code:
        return True  # using less of something adds nothing new
    texts = [swap.to_name, food.name]
    if any(contains_term(text, term) for text in texts for term in user_avoid_terms(preferences)):
        return False
    user_allergens = allergens_for_user_allergies(preferences.get("allergies"))
    found = allergens_in([swap.to_name], {swap.to_name: food.name})
    return not (user_allergens & set(found))


def has_figure(goal, food):
    """Cost and carbon swaps need a figure on both sides, or the saving is not real."""
    if goal == "cheapest":
        return food.price_per_kg_gbp is not None
    if goal == "greenest":
        return food.carbon_category is not None or food.food_code in {"17-377", "17-367"}
    return True


def apply_swap(resolved, swap, new_food):
    """The recipe with this swap made on every line that uses the original food."""
    swapped = []
    for item in resolved:
        if item.food is None or item.food.food_code != swap.from_code:
            swapped.append(item)
            continue
        kept = item.grams * (1 - swap.share)
        if kept > 0:
            swapped.append(replace(item, grams=kept))
        if new_food is not None:
            swapped.append(ResolvedIngredient(swap.to_name, item.grams * swap.share * swap.ratio, new_food, "swap"))
    return swapped


def original_name(swap, resolved):
    """The recipe's own name for the food being swapped, e.g. 'paneer'."""
    return next(item.name for item in resolved if item.food and item.food.food_code == swap.from_code)


def describe(swap, resolved):
    """'Swap half the beef mince for red lentils', using the recipe's own name for the food."""
    return swap.text.format(**{"from": original_name(swap, resolved)})


# ---------------------------------------------------------------------------
# Building the three versions
# ---------------------------------------------------------------------------

def impact_text(goal, before, after):
    """What one swap did, in words: '£0.42 less per serving', 'Saturates: High → Medium'."""
    if goal == "cheapest":
        return f"£{measure(goal, before) - measure(goal, after):.2f} less per serving"
    if goal == "greenest":
        return f"{measure(goal, before) - measure(goal, after):.2f} kg CO₂e less per serving"

    changes = [
        f"{NUTRIENT_WORDS[n].capitalize()}: {LIGHT_WORDS[before.traffic_lights[n]]} → {LIGHT_WORDS[after.traffic_lights[n]]}"
        for n in TRAFFIC_LIGHT_THRESHOLDS
        if before.traffic_lights[n] != after.traffic_lights[n]
    ]
    if changes:
        return ", ".join(changes)
    drops = sorted(
        ((before.per_serving[n] - after.per_serving[n], n) for n in TRAFFIC_LIGHT_THRESHOLDS),
        reverse=True,
    )
    fibre_gain = after.per_serving["fibre_g"] - before.per_serving["fibre_g"]
    parts = [f"{drop:.1f} g less {NUTRIENT_WORDS[n]}" for drop, n in drops[:2] if drop >= 0.1]
    if fibre_gain >= 0.5:
        parts.append(f"{fibre_gain:.1f} g more fibre")
    return (", ".join(parts) + " per serving") if parts else "A little less fat, saturates, sugars or salt"


def build_version(goal, resolved, servings, original, candidates):
    """
    Greedy: keep adding the swap that helps most, up to MAX_SWAPS.
    Also says whether the version's cost and carbon can be compared with the
    original: not when a swap brings in or takes out a food with no figure
    (butter has no carbon figure, so "rapeseed oil instead of butter" would look
    like it adds carbon).
    """
    current, current_result = resolved, original
    chosen, used = [], set()
    comparable = {"cheapest": True, "greenest": True}

    for _ in range(MAX_SWAPS):
        best = None
        for swap, new_food in candidates:
            if swap.from_code in used:
                continue
            trial = apply_swap(current, swap, new_food)
            result = calculate_for_foods(trial, servings)
            if goal != "healthiest" and lights_got_worse(result, original):
                continue
            after = measure(goal, result)
            if after is None:
                continue
            gain = measure(goal, current_result) - after
            if gain >= MIN_GAIN[goal] and (best is None or gain > best[0]):
                best = (gain, swap, trial, result)
        if best is None:
            break
        _, swap, trial, result = best
        old_food = next(item.food for item in current if item.food and item.food.food_code == swap.from_code)
        new_food = next((food for candidate, food in candidates if candidate is swap), None)
        for measure_goal in comparable:
            if not has_figure(measure_goal, old_food) or (new_food is not None and not has_figure(measure_goal, new_food)):
                comparable[measure_goal] = False
        chosen.append({
            "from_code": swap.from_code,
            "to_code": swap.to_code,
            "from_name": original_name(swap, current),
            "to_name": swap.to_name,
            "share": swap.share,
            "text": describe(swap, current),
            "note": swap.note,
            "source": swap.source,
            "impact": impact_text(goal, current_result, result),
        })
        used.add(swap.from_code)
        current, current_result = trial, result

    return chosen, current_result, comparable


def version_summary(result, original, comparable):
    """
    Cost, carbon and energy per serving for one version, with the change from
    the original. Changes are worked out before rounding, so they match the
    per-swap amounts, and the version's figure is the original's plus the change,
    so the numbers on the page add up.
    """

    def change(goal, places):
        now, before = measure(goal, result), measure(goal, original)
        if now is None or before is None or not comparable[goal]:
            return None
        return round(now - before, places)

    tag = None
    still_high = []
    if result.is_complete:
        tag = "treat" if "red" in result.traffic_lights.values() else "everyday"
        still_high = [NUTRIENT_WORDS[n] for n, light in result.traffic_lights.items() if light == "red"]
    cost_change, carbon_change = change("cheapest", 2), change("greenest", 2)
    cost, carbon = result.cost_gbp_per_serving, result.carbon_kg_per_serving
    if cost_change is not None:
        cost = round(original.cost_gbp_per_serving + cost_change, 2)
    if carbon_change is not None:
        carbon = round(original.carbon_kg_per_serving + carbon_change, 2)
    kcal = round(result.per_serving["energy_kcal"])
    kcal_change = kcal - round(original.per_serving["energy_kcal"])
    return {
        "cost": cost,
        "cost_change": cost_change,
        "carbon": carbon,
        "carbon_change": carbon_change,
        "kcal": kcal,
        "kcal_change": kcal_change,
        "tag": tag,
        "still_high": still_high,
        "stats": [
            {"label": "Cost", "value": None if cost is None else f"£{cost:.2f}",
             "change": change_text(cost_change, "£{:.2f}")},
            {"label": "Carbon", "value": None if carbon is None else f"{carbon:.2f} kg CO₂e",
             "change": change_text(carbon_change, "{:.2f} kg")},
            {"label": "Energy", "value": f"{kcal} kcal", "change": change_text(kcal_change, "{:.0f} kcal")},
        ],
    }


def change_text(change, template):
    """-0.42 -> '£0.42 less'; None -> '' (not comparable, so nothing is claimed)."""
    if change is None:
        return ""
    if change == 0:
        return "no change"
    return template.format(abs(change)) + (" less" if change < 0 else " more")


def three_ways(resolved, servings, preferences, extra_swaps=()):
    """
    resolved:    the recipe's ingredients matched to foods (nutrition.services.resolve_ingredients)
    extra_swaps: Swaps the AI suggested that already passed swap_suggestion_service checks
    Returns a list of three dicts (cheapest, healthiest, greenest) for the page.
    """
    original = calculate_for_foods(resolved, servings)
    codes_in_recipe = {item.food.food_code for item in resolved if item.food}
    on_list = {(swap.from_code, swap.to_code, swap.share) for swap in load_swaps()}
    extra = [swap for swap in extra_swaps if (swap.from_code, swap.to_code, swap.share) not in on_list]
    swaps = [swap for swap in list(load_swaps()) + extra if swap.from_code in codes_in_recipe]
    new_foods = {
        food.food_code: food
        for food in CofidFood.objects.select_related("carbon_category").filter(
            food_code__in={swap.to_code for swap in swaps if swap.to_code}
        )
    }
    old_foods = {item.food.food_code: item.food for item in resolved if item.food}

    versions = []
    for goal, title, icon in VERSIONS:
        version = {"goal": goal, "title": title, "icon": icon, "swaps": []}
        if measure(goal, original) is None or (goal == "healthiest" and not original.is_complete):
            version["message"] = NOT_ENOUGH_DATA[goal]
            versions.append(version)
            continue

        candidates = []
        for swap in swaps:
            new_food = new_foods.get(swap.to_code)
            if swap.to_code and new_food is None:
                continue  # the list names a food that isn't loaded; never guess
            if new_food is not None and not is_safe_for_user(swap, new_food, preferences):
                continue
            if not has_figure(goal, old_foods[swap.from_code]):
                continue
            if new_food is not None and not has_figure(goal, new_food):
                continue
            candidates.append((swap, new_food))

        chosen, result, comparable = build_version(goal, resolved, servings, original, candidates)
        version["swaps"] = chosen
        if chosen:
            version.update(version_summary(result, original, comparable))
            version["instruction"] = (
                f"Make the {title.lower()} version of this recipe with these swaps: "
                + "; ".join(swap["text"] for swap in chosen)
                + ". Adjust the quantities and steps to suit, and keep everything else the same."
            )
        else:
            version["message"] = NO_SWAP_MESSAGES[goal]
        versions.append(version)
    return versions
