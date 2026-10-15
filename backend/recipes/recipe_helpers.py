"""
Helpers shared by the recipe pages: the recipe title, saving images, the
nutrition/cost panels (insights), the quality-check rows and emailing a recipe.

(Split out of views.py; recipes/views.py still re-exports everything.)
"""

import base64
import uuid
import traceback
from django.contrib import messages
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.mail import send_mail


from .models import (
    RecipeHistory,
)
from .cuisine_service import recipe_cuisine_check
from .insight_service import build_insights
from .structure_service import extract_recipe_structure





# Helper: extracts a clean recipe title from AI-generated text.
def extract_recipe_title(recipe_text):
    """
    Extracts a clean recipe title from AI-generated recipe text.

    This supports both:
    - normal generated recipes
    - AI-modified recipes
    """

    if not recipe_text:
        return "AI Generated Recipe"

    lines = recipe_text.splitlines()

    # Important: AI output may use either normal or modified title heading.
    title_headings = [
        "RECIPE TITLE",
        "MODIFIED RECIPE TITLE",
    ]

    for index, line in enumerate(lines):
        clean_line = line.strip()
        clean_upper = clean_line.upper()

        for heading in title_headings:
            if clean_upper.startswith(heading):
                title_part = ""

                if ":" in clean_line:
                    title_part = clean_line.split(":", 1)[1].strip()

                if title_part:
                    return title_part[:200]

                # If title is written on the next line, use that next line.
                if index + 1 < len(lines):
                    next_line = lines[index + 1].strip()

                    if next_line:
                        return next_line[:200]

    # Fallback: use the first non-empty line.
    for line in lines:
        clean_line = line.strip()

        if clean_line:
            return clean_line[:200]

    return "AI Generated Recipe"


# Helper: saves a generated Base64 recipe image into Django media storage.
def save_generated_recipe_image(image_base64):
    """
    Saves an OpenAI-generated Base64 image into Django's media storage.

    Returns the relative media path that can be assigned directly to
    Recipe.generated_image.
    """

    if not image_base64:
        return ""

    clean_image_base64 = str(image_base64).strip()

    if clean_image_base64.startswith("data:image") and "," in clean_image_base64:
        clean_image_base64 = clean_image_base64.split(",", 1)[1]

    image_binary = base64.b64decode(clean_image_base64)
    image_file = ContentFile(image_binary)

    image_path = f"recipe_images/culinaai_recipe_{uuid.uuid4().hex}.png"

    return default_storage.save(image_path, image_file)


# Helper: returns a safe display URL for saved media files.
def get_storage_url(file_path):
    """
    Safely returns a display URL for a file saved using Django storage.
    """

    if not file_path:
        return ""

    try:
        return default_storage.url(file_path)
    except Exception:
        return ""


    











# Helper: nutrition, cost, carbon, health and risk panels for one recipe.
def build_recipe_insights(recipe_text, preferences):
    """
    Reads the finished recipe into structured ingredients (one small AI call),
    then works out everything else in code (insight_service.py).

    Never raises: if anything fails, the recipe is still shown and the panel
    says nutrition is not available.
    """

    try:
        structure_result = extract_recipe_structure(recipe_text, preferences)
        insights = build_insights(structure_result, preferences, recipe_text)
    except Exception as error:
        print("CULINAAI INSIGHTS ERROR:", repr(error))
        traceback.print_exc()
        insights = build_insights(None, preferences, recipe_text)

    # Does it use the ingredients typical of the chosen cuisine? (cuisine_service.py, published data)
    try:
        cuisine = recipe_cuisine_check(preferences, insights, recipe_text)
        if cuisine:
            insights = dict(insights, cuisine=cuisine)
    except Exception as error:
        print("CULINAAI CUISINE CHECK ERROR:", repr(error))

    return insights


# Helper: builds validation preferences for AI-modified recipes.
def build_modified_recipe_validation_preferences(recipe, modification_type="", custom_instruction=""):
    """
    Creates a preferences dictionary for validating an AI-modified recipe.

    The normal recipe generation flow already validates recipes using the
    original form preferences. Modified recipes do not come directly from that
    form, so this helper rebuilds enough preference data from the saved recipe
    and the user's modification request.

    This means modified recipes can also store:
    - quality score
    - validation status
    - risk level
    - validation badge
    - full validation report
    - validation attempt history
    """

    modification_labels = {
        "healthier": "Healthier",
        "cheaper": "Cheaper",
        "quicker": "Quicker",
        "vegetarian": "Vegetarian",
        "spicier": "Spicier",
        "simpler": "Simpler",
        "custom": "Custom modification",
    }

    modification_label = modification_labels.get(
        modification_type,
        modification_type or "Modified recipe",
    )

    # Start with the original saved recipe cuisine.
    # If the custom instruction clearly asks for a cuisine change, update it
    # so the validation engine checks the modified recipe against the new style.
    cuisine_name = recipe.cuisine.name if recipe.cuisine else "Any cuisine"
    custom_instruction_lower = str(custom_instruction or "").lower()

    cuisine_keywords = {
        "chinese": "Chinese",
        "indian": "Indian",
        "italian": "Italian",
        "mexican": "Mexican",
        "thai": "Thai",
        "japanese": "Japanese",
        "korean": "Korean",
        "mediterranean": "Mediterranean",
        "american": "American",
        "british": "British",
        "french": "French",
        "spanish": "Spanish",
    }

    for keyword, display_name in cuisine_keywords.items():
        if keyword in custom_instruction_lower:
            cuisine_name = display_name
            break

    diet_preferences = [diet.name for diet in recipe.diet_preferences.all()]

    # If the modification itself asks for a diet change, add that requirement
    # to the validation preferences before checking the modified recipe.
    if modification_type == "vegetarian" and "Vegetarian" not in diet_preferences:
        diet_preferences.append("Vegetarian")

    if "vegan" in custom_instruction_lower and "Vegan" not in diet_preferences:
        diet_preferences.append("Vegan")

    if "vegetarian" in custom_instruction_lower and "Vegetarian" not in diet_preferences:
        diet_preferences.append("Vegetarian")

    if "gluten-free" in custom_instruction_lower and "Gluten Free" not in diet_preferences:
        diet_preferences.append("Gluten Free")

    if "dairy-free" in custom_instruction_lower and "Dairy Free" not in diet_preferences:
        diet_preferences.append("Dairy Free")

    # This gives the validation engine clear context without needing a new model field.
    additional_notes = (
        f"AI modification type: {modification_label}. "
        f"Custom instruction: {custom_instruction or 'None provided'}. "
        "Validate the modified recipe against the original saved recipe safety, diet and allergy restrictions."
    )

    return {
        "ingredients": recipe.ingredients_text or "",
        "cuisine": cuisine_name,
        "meal_type": recipe.meal_type.name if recipe.meal_type else "Any meal type",
        "diet_preferences": diet_preferences,
        "allergies": recipe.allergy_notes or "None provided",
        "cooking_time_minutes": recipe.cooking_time_minutes or 30,
        "servings": getattr(recipe, "servings", None) or 2,
        "difficulty": recipe.difficulty or "easy",
        "spice_level": "Medium",
        "budget_level": "Moderate Budget",
        "nutrition_goal": modification_label,
        "cooking_equipment": [],
        "utensils": [],
        "additional_notes": additional_notes,
    }


# Helper: converts one validation report into a simple attempt-history row.
def build_validation_attempt_row(validation_report, attempt_number=1):
    """
    Converts the full validation report into a compact history item.

    The Recipe model stores both:
    - full validation_report JSON
    - shorter validation_attempt_history JSON

    This helper keeps modified recipe validation evidence consistent with the
    normal recipe generation flow.
    """

    validation_report = validation_report or {}

    return {
        "attempt_number": attempt_number,
        "score": validation_report.get("score"),
        "status": validation_report.get("status"),
        "risk_level": validation_report.get("risk_level"),
        "hard_fail": validation_report.get("hard_fail"),
        "failed_checks": [
            check.get("name")
            for check in validation_report.get("failed_checks", [])
            if isinstance(check, dict)
        ],
    }


# Helper: stores each generated recipe into RecipeHistory for history, analytics and evidence.
def create_recipe_history_entry(
    user,
    recipe_text,
    recipe_prompt,
    preferences,
    image_path="",
    image_prompt="",
    validation_report=None,
    validation_attempt_history=None,
    insights=None,
):
    """
    Automatically stores every generated recipe in RecipeHistory.

    This supports:
    - user history page
    - recent searches
    - analytics dashboard
    - future ML recommendation engine
    """

    if not recipe_text or not preferences:
        return None

    validation_report = validation_report or {}
    validation_attempt_history = validation_attempt_history or []

    # Important: this creates the automatic history database record.
    return RecipeHistory.objects.create(
        user=user,
        title=extract_recipe_title(recipe_text),
        recipe_text=recipe_text,
        recipe_prompt=recipe_prompt or "",

        ingredients_text=preferences.get("ingredients", ""),
        cuisine_name=preferences.get("cuisine", ""),
        meal_type_name=preferences.get("meal_type", ""),
        dietary_preferences=preferences.get("diet_preferences", []) or [],
        allergies=preferences.get("allergies", ""),

        cooking_time_minutes=preferences.get("cooking_time_minutes") or 30,
        servings=preferences.get("servings") or None,
        difficulty=preferences.get("difficulty") or "easy",

        spice_level=preferences.get("spice_level", ""),
        budget_level=preferences.get("budget_level", ""),
        nutrition_goal=preferences.get("nutrition_goal", ""),
        cooking_equipment=preferences.get("cooking_equipment", []) or [],
        utensils=preferences.get("utensils", []) or [],
        additional_notes=preferences.get("additional_notes", ""),

        generated_image=image_path or None,
        generated_image_prompt=image_prompt or "",

        quality_score=validation_report.get("score"),
        validation_status=validation_report.get("status", ""),
        validation_risk_level=validation_report.get("risk_level", ""),
        validation_badge=validation_report.get("badge", ""),
        validation_attempts=len(validation_attempt_history),
        validation_report=validation_report,
        validation_attempt_history=validation_attempt_history,
        insights=insights or {},
    )


def failed_check_details(validation_report):
    """{check name: its details} for the checks that failed, e.g. the allergy words found."""
    return {
        check.get("name"): check.get("details")
        for check in validation_report.get("failed_checks", [])
        if check.get("details")
    }


def recipe_email_body(sender_name, title, recipe_text, note=""):
    """The plain-text email for a recipe."""
    parts = [f"{sender_name} sent you a recipe from CulinaAI.", ""]
    if note:
        parts += [note, ""]
    parts += [
        title,
        "",
        recipe_text.strip(),
        "",
        "Allergy and nutrition information is a guide. Always check ingredient labels.",
        "",
        "CulinaAI",
    ]
    return "\n".join(parts)


def send_recipe_email_safely(request, recipient, title, body):
    """Sends a recipe email and tells the user whether it went. Never raises."""
    try:
        send_mail(
            subject=f"Recipe: {title}",
            message=body,
            from_email=None,
            recipient_list=[recipient],
            fail_silently=False,
        )
    except Exception as error:
        print("CULINAAI RECIPE EMAIL ERROR:", repr(error))
        messages.error(request, "The email couldn't be sent just now. Please try again in a moment.")
        return False
    messages.success(request, f"Recipe sent to {recipient}.")
    return True
