"""
One plain sentence about a recipe's quality checks, for the recipe pages.

The validation engine (recipe_quality_engine.py) runs ten checks and keeps a
detailed report. People cooking don't need ten boxes, so the pages show one
line: that the recipe fits what they asked for, or the one thing worth knowing.
The full list stays one click away.
"""

# What each check looked at, and what to say when it didn't pass.
CHECKS = {
    "Allergy Safety": ("your allergies", "It may contain something you're avoiding{terms}."),
    "Diet Compliance": ("your diet", "It may not fit your diet{terms}."),
    "Ingredient Match": ("your ingredients", "It doesn't use all of your ingredients{missing}."),
    "Recipe Structure": ("a complete method", "Part of the recipe may be missing."),
    "Cooking Time Match": ("your cooking time", "It may take longer than the time you set."),
    "Equipment Compatibility": ("your equipment", "It may need equipment you didn't select{equipment}."),
    "Difficulty Match": ("the difficulty", "It may be a little harder than the difficulty you chose."),
    "Cuisine and Nutrition Relevance": ("the cuisine", "It may not closely match the cuisine or nutrition goal you chose."),
    "Health Claims": ("health claims", "It makes a health claim that isn't backed up."),
    "Explanation Consistency": ("the notes", "Its notes may not match the recipe exactly."),
}

# Failing one of these means the recipe may not be safe for this person.
SAFETY = {"Allergy Safety", "Diet Compliance"}


def listed(values):
    values = [str(value).strip().lstrip("-•* ").strip() for value in values or [] if value]
    values = [value for value in values if value]
    return f" ({', '.join(values[:4])})" if values else ""


def note_for(check):
    _, template = CHECKS.get(check.get("name"), ("", "{name} needs a look."))
    details = check.get("details") or {}
    return template.format(
        name=check.get("name", "A check"),
        terms=listed(details.get("conflicting_terms") or details.get("restricted_terms_found")),
        missing=listed(details.get("missing_ingredients")),
        equipment=listed(details.get("unavailable_equipment_found")),
    )


def summarise_checks(report):
    """
    {"state": "ok" | "note" | "warning", "headline", "notes", "checks", "passed", "total"}
    for a validation report, or None when there is nothing to summarise.
    """
    if not isinstance(report, dict):
        return None
    checks = [check for check in report.get("checks") or [] if isinstance(check, dict) and check.get("name")]
    if not checks:
        return None

    failed = [check for check in checks if not check.get("passed")]
    safety_failed = [check for check in failed if check["name"] in SAFETY]
    notes = [note_for(check) for check in (safety_failed or failed)]

    if safety_failed:
        state = "warning"
        headline = "Check before you cook."
    elif failed:
        state = "note"
        headline = "Checked: it fits your allergies and diet."
    else:
        state = "ok"
        headline = "Checked: it fits your allergies, diet, ingredients, cooking time and equipment."

    return {
        "state": state,
        "headline": headline,
        "notes": notes[:2],
        "passed": len(checks) - len(failed),
        "total": len(checks),
        "checks": [
            {
                "name": check["name"],
                "passed": bool(check.get("passed")),
                "text": (
                    f"Matches {CHECKS[check['name']][0]}." if check.get("passed") and check["name"] in CHECKS
                    else note_for(check) if not check.get("passed") else check.get("message", "")
                ),
            }
            for check in checks
        ],
    }
