"""
The diet and allergies saved on the profile (accounts.UserProfile), used to fill in
the New recipe form, and to warn when a recipe was made without one of them.
"""

from accounts.models import UserProfile


def split_list(text):
    return [part.strip() for part in str(text or "").replace("\n", ",").replace(";", ",").split(",") if part.strip()]


def saved_diet(user):
    """{"diet_ids", "diet_names", "other_diet", "allergies", "has_any"} for this user."""

    profile = UserProfile.objects.filter(user=user).prefetch_related("diet_preferences").first()
    if profile is None:
        return {"diet_ids": [], "diet_names": [], "other_diet": "", "allergies": "", "has_any": False}
    diets = list(profile.diet_preferences.all())
    return {
        "diet_ids": [diet.id for diet in diets],
        "diet_names": [diet.name for diet in diets],
        "other_diet": profile.other_diet,
        "allergies": profile.allergies,
        "has_any": bool(diets or profile.other_diet.strip() or profile.allergies.strip()),
    }


def missing_saved_allergies(user, allergies_text):
    """Saved allergies that aren't in the list typed for this recipe, so the recipe wasn't checked for them."""

    saved = split_list(saved_diet(user)["allergies"])
    typed = " ".join(split_list(allergies_text)).lower()
    return [item for item in saved if item.lower() not in typed]
