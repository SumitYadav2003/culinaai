"""
The weekly meal plan and its shopping list. No AI is used here: everything is
worked out from the saved recipes and the pantry.

The shopping list
-----------------
For every recipe planned in the week:

- If the recipe has its ingredients worked out in grams (recipe.insights,
  filled in when the recipe was made), each one is scaled to the planned
  servings and the same ingredient across recipes is added up:
  "Red onion, about 300 g, for Tray bake (Mon) and Dal (Wed)".
- Older recipes without those figures fall back to the ingredient lines as
  written. Those can't be added up safely (200 g and 1 cup don't add), so each
  line is listed under the ingredient with the recipe it came from.

Anything that matches the user's pantry (in date and marked available) goes in
a separate "you may already have" group, showing what it matched so the user
can judge (pantry "oil" matches "olive oil").
"""

import re
from collections import OrderedDict
from datetime import date, timedelta

from django.utils import timezone

from .models import MealPlanEntry, ShoppingListCheck, ShoppingListExtra
from .shopping_service import (
    CATEGORY_DEFINITIONS,
    choose_category_key,
    extract_ingredient_items,
    get_available_pantry_lookup,
    normalise_for_matching,
)

DEFAULT_SERVINGS = 2
# Not worth putting on a shopping list.
SKIP_KEYS = {"water", "cold water", "hot water", "boiling water", "warm water", "ice"}

SHOP_CATEGORY_TITLES = {
    "fresh_produce": "Fruit, veg and herbs",
    "protein": "Meat, fish, eggs and beans",
    "dairy": "Dairy and chilled",
    "pantry": "Cupboard",
    "spices": "Spices and seasoning",
    "other": "Other",
}


# ---------- Weeks ----------

def week_start_for(day):
    """The Monday of the week that day is in."""

    return day - timedelta(days=day.weekday())


def parse_week(value):
    """The Monday of the week asked for in ?week=YYYY-MM-DD, or this week."""

    try:
        day = date.fromisoformat(str(value))
    except (TypeError, ValueError):
        day = timezone.localdate()
    return week_start_for(day)


def week_days(week_start):
    return [week_start + timedelta(days=offset) for offset in range(7)]


def week_label(week_start):
    """'13 – 19 Oct 2026', or across months '27 Oct – 2 Nov 2026'."""

    end = week_start + timedelta(days=6)
    if week_start.month == end.month:
        return f"{week_start.day} – {end.day} {end:%b %Y}"
    if week_start.year == end.year:
        return f"{week_start.day} {week_start:%b} – {end.day} {end:%b %Y}"
    return f"{week_start.day} {week_start:%b %Y} – {end.day} {end:%b %Y}"


def short_date(day):
    """'Thu 15 Oct'. (Built by hand: "%-d" doesn't work on Windows.)"""

    return f"{day:%a} {day.day} {day:%b}"


def long_day(day, today=None):
    """'today (Thu 15 Oct)', 'tomorrow (Fri 16 Oct)' or 'Saturday 17 Oct', for messages and menus."""

    label = day_label(day, today)
    if label in ("Today", "Tomorrow"):
        return f"{label.lower()} ({short_date(day)})"
    return f"{day:%A} {day.day} {day:%b}"


def day_label(day, today=None):
    today = today or timezone.localdate()
    if day == today:
        return "Today"
    if day == today + timedelta(days=1):
        return "Tomorrow"
    return f"{day:%A}"


# ---------- The plan ----------

def week_entries(user, week_start):
    return (
        MealPlanEntry.objects.filter(
            user=user,
            recipe__is_saved=True,
            date__gte=week_start,
            date__lt=week_start + timedelta(days=7),
        )
        .select_related("recipe")
        .order_by("date", "created_at")
    )


def sort_entries(entries):
    return sorted(entries, key=lambda e: (e.date, MealPlanEntry.MEAL_ORDER.get(e.meal, 9), e.created_at))


def build_week(user, week_start):
    """The seven days of the week, each with its meals in breakfast-to-snack order."""

    today = timezone.localdate()
    by_day = {day: [] for day in week_days(week_start)}
    for entry in sort_entries(week_entries(user, week_start)):
        by_day[entry.date].append(entry)

    return [
        {
            "date": day,
            "label": day_label(day, today),
            "is_today": day == today,
            "is_past": day < today,
            "entries": by_day[day],
        }
        for day in week_days(week_start)
    ]


def upcoming_entries(user, days=2):
    """What's planned for today and tomorrow, for the dashboard."""

    today = timezone.localdate()
    entries = (
        MealPlanEntry.objects.filter(
            user=user,
            recipe__is_saved=True,
            date__gte=today,
            date__lt=today + timedelta(days=days),
        )
        .select_related("recipe")
    )
    grouped = OrderedDict((today + timedelta(days=n), []) for n in range(days))
    for entry in sort_entries(entries):
        grouped[entry.date].append(entry)
    return [{"date": day, "label": day_label(day, today), "entries": items} for day, items in grouped.items()]


def recipe_base_servings(recipe):
    """How many people the recipe as written serves."""

    insights = recipe.insights or {}
    servings = (insights.get("nutrition") or {}).get("servings")
    if not servings:
        match = re.search(r"SERVINGS:\s*\n?\s*(\d+)", recipe.instructions_text or "", re.IGNORECASE)
        servings = int(match.group(1)) if match else None
    try:
        servings = int(servings)
    except (TypeError, ValueError):
        servings = None
    return servings if servings and 0 < servings <= 50 else DEFAULT_SERVINGS


def structured_ingredients(recipe):
    """The ingredients in grams, if the recipe has them worked out; otherwise an empty list."""

    insights = recipe.insights or {}
    if not insights.get("available"):
        return []
    items = []
    for item in insights.get("ingredients") or []:
        name = str(item.get("name") or "").strip()
        try:
            grams = float(item.get("grams") or 0)
        except (TypeError, ValueError):
            grams = 0
        if name and grams > 0:
            items.append({"name": name, "grams": grams})
    return items


def copy_week(user, from_start, to_start):
    """Copies one week's plan into another. Meals already there are left alone. Returns how many were added."""

    existing = set(
        week_entries(user, to_start).values_list("recipe_id", "date", "meal")
    )
    added = 0
    for entry in week_entries(user, from_start):
        new_date = to_start + (entry.date - from_start)
        if (entry.recipe_id, new_date, entry.meal) in existing:
            continue
        MealPlanEntry.objects.create(
            user=user, recipe=entry.recipe, date=new_date, meal=entry.meal, servings=entry.servings,
        )
        added += 1
    return added


# ---------- The shopping list ----------

def format_grams(grams):
    """Rounded the way you'd shop: 'about 450 g', 'about 1.2 kg'."""

    if grams >= 995:
        kilos = round(grams / 1000, 1)
        return f"about {kilos:g} kg"
    if grams >= 100:
        return f"about {int(round(grams / 10.0) * 10)} g"
    if grams >= 10:
        return f"about {int(round(grams / 5.0) * 5)} g"
    return f"about {max(1, int(round(grams)))} g"


def display_name(name):
    name = str(name).strip()
    return name[:1].upper() + name[1:] if name else name


def strip_quantity(line):
    """
    The ingredient name in a written line, used to group it:
    '2 tbsp olive oil' -> 'olive oil', '4 chicken thighs, skinless (about 500 g)' -> 'chicken thigh'.
    """

    text = re.sub(r"\([^)]*\)", " ", str(line))
    text = text.split(",")[0]
    words = normalise_for_matching(text)
    return words or str(line).strip().lower()


UNIT_WORDS = (
    "g|gram|grams|kg|ml|l|litre|litres|cup|cups|tbsp|tablespoons?|tsp|teaspoons?|"
    "pinch|handful|pack|packet|tin|tins|can|cans|clove|cloves|slice|slices|bunch"
)


def line_display_name(line):
    """The readable name for a written line: '3 garlic cloves, crushed' -> 'Garlic cloves'."""

    text = re.sub(r"\([^)]*\)", " ", str(line)).split(",")[0]
    text = re.sub(r"^[\s\d½¼¾⅓⅔./x×-]+", "", text.strip())
    text = re.sub(rf"^(?:{UNIT_WORDS})\b\.?\s*(?:of\s+)?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:large|medium|small)\s+", "", text, flags=re.IGNORECASE)
    return display_name(" ".join(text.split())) or display_name(line)


def pantry_match_for(key, pantry_lookup):
    """
    A pantry item that matches this ingredient. Stricter than "any word in
    common": every word of one name must be in the other, so pantry "oil"
    matches "olive oil", but "red pepper" doesn't match "black pepper".
    """

    tokens = set(key.split())
    if not tokens:
        return None
    for entry in pantry_lookup:
        pantry_tokens = set(entry["key"].split())
        if pantry_tokens and (pantry_tokens <= tokens or tokens <= pantry_tokens):
            return entry
    return None


def build_shopping_list(user, week_start):
    """
    The week's shopping list:

    {
      "groups": [{"key", "title", "items": [item, ...]}, ...],   # to buy
      "have": [item, ...],                                       # matched the pantry
      "extras": [ShoppingListExtra, ...],
      "recipe_count", "to_buy_count", "done_count", "has_unscaled",
    }

    Each item: key, name, amount ("about 450 g" or ""), lines (written amounts that
    couldn't be added up), uses (recipe titles and days), done, pantry_name.
    """

    entries = sort_entries(week_entries(user, week_start))
    items = OrderedDict()
    has_unscaled = False

    def item_for(key, name):
        if key not in items:
            items[key] = {
                "key": key,
                "name": display_name(name),
                "grams": 0.0,
                "lines": [],
                "uses": OrderedDict(),  # recipe title -> days, joined into text below
                "category": choose_category_key(name),
            }
        return items[key]

    for entry in entries:
        recipe = entry.recipe
        day_name = f"{entry.date:%a}"
        factor = entry.servings / recipe_base_servings(recipe)
        structured = structured_ingredients(recipe)

        if structured:
            for ingredient in structured:
                key = normalise_for_matching(ingredient["name"])
                if not key or key in SKIP_KEYS:
                    continue
                item = item_for(key, ingredient["name"])
                item["grams"] += ingredient["grams"] * factor
                days = item["uses"].setdefault(recipe.title, [])
                if day_name not in days:
                    days.append(day_name)
        else:
            for line in extract_ingredient_items(recipe.ingredients_text):
                key = strip_quantity(line)
                if not key or key in SKIP_KEYS:
                    continue
                has_unscaled = True
                item = item_for(key, line_display_name(line))
                note = line if entry.servings == recipe_base_servings(recipe) else (
                    f"{line} (recipe serves {recipe_base_servings(recipe)}, planned for {entry.servings})"
                )
                item["lines"].append(f"{note} – {recipe.title}")
                days = item["uses"].setdefault(recipe.title, [])
                if day_name not in days:
                    days.append(day_name)

    checked = set(
        ShoppingListCheck.objects.filter(user=user, week_start=week_start).values_list("item_key", flat=True)
    )
    pantry_lookup = get_available_pantry_lookup(user)

    groups = OrderedDict(
        (category["key"], {"key": category["key"], "title": SHOP_CATEGORY_TITLES[category["key"]], "items": []})
        for category in CATEGORY_DEFINITIONS
    )
    have = []

    for item in sorted(items.values(), key=lambda i: i["name"].lower()):
        # "Lemon rice (Wed, Fri), Tray bake (Mon)"
        item["uses"] = [f"{title} ({', '.join(days)})" for title, days in item["uses"].items()]
        item["amount"] = format_grams(item["grams"]) if item["grams"] else ""
        item["done"] = item["key"] in checked
        match = pantry_match_for(item["key"], pantry_lookup)
        item["pantry_name"] = match["name"] if match else ""
        if match:
            have.append(item)
        else:
            groups[item["category"]]["items"].append(item)

    visible_groups = [group for group in groups.values() if group["items"]]
    extras = list(ShoppingListExtra.objects.filter(user=user, week_start=week_start))
    to_buy = [item for group in visible_groups for item in group["items"]]

    return {
        "groups": visible_groups,
        "have": have,
        "extras": extras,
        "recipe_count": len(entries),
        "to_buy_count": len(to_buy) + len(extras),
        "done_count": sum(1 for item in to_buy if item["done"]) + sum(1 for extra in extras if extra.done),
        "has_unscaled": has_unscaled,
    }


def shopping_list_text(shopping, week_start):
    """The list as plain text, for copying and for the email."""

    lines = [f"CulinaAI shopping list, week of {week_label(week_start)}", ""]
    for group in shopping["groups"]:
        lines.append(group["title"].upper())
        for item in group["items"]:
            tick = "[x]" if item["done"] else "[ ]"
            amount = f", {item['amount']}" if item["amount"] else ""
            lines.append(f"{tick} {item['name']}{amount}")
            for line in item["lines"]:
                lines.append(f"      {line}")
        lines.append("")
    if shopping["extras"]:
        lines.append("ALSO")
        for extra in shopping["extras"]:
            lines.append(f"{'[x]' if extra.done else '[ ]'} {extra.name}")
        lines.append("")
    if shopping["have"]:
        lines.append("YOU MAY ALREADY HAVE (in your pantry)")
        for item in shopping["have"]:
            amount = f", {item['amount']}" if item["amount"] else ""
            lines.append(f"- {item['name']}{amount}")
        lines.append("")
    lines.append("Amounts are estimates for the servings you planned. Check labels for allergens.")
    return "\n".join(lines)
