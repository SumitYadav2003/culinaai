import base64
import json
import uuid
import traceback
from datetime import timedelta
from collections import Counter
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.mail import send_mail
from django.db.models import Avg, Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .cooking_chat_service import ask_cooking_assistant


from .ai_service import (
    generate_ai_recipe,
    generate_recipe_image_base64,
    modify_ai_recipe,
)
from .recipe_quality_engine import (
    build_regeneration_preferences,
    build_safe_fallback_recipe,
    validate_recipe_output,
)
from .forms import (
    RecipeEmailForm,
    RecipeFeedbackForm,
    RecipeGenerationForm,
    RecipeModifyForm,
    SavedRecipeEditForm,
    PantryItemForm,
)
from .models import (
    Cuisine,
    DietPreference,
    FavouriteRecipe,
    MealType,
    Recipe,
    RecipeFeedback,
    RecipeHistory,
    RecipeRating,
    PantryItem,
)
from .shopping_service import build_shopping_list_context

from .recommendation_service import get_personalised_recommendations

from .cooking_mode_service import build_cooking_mode_context

from .cooking_chat_service import build_cooking_chat_context


def extract_recipe_title(recipe_text):
    """
    Extracts a clean recipe title from the AI-generated recipe text.
    """

    if not recipe_text:
        return "AI Generated Recipe"

    lines = recipe_text.splitlines()

    for index, line in enumerate(lines):
        clean_line = line.strip()

        if clean_line.upper().startswith("RECIPE TITLE"):
            title_part = clean_line.replace("RECIPE TITLE:", "").strip()

            if title_part:
                return title_part[:200]

            if index + 1 < len(lines):
                next_line = lines[index + 1].strip()

                if next_line:
                    return next_line[:200]

    for line in lines:
        clean_line = line.strip()

        if clean_line:
            return clean_line[:200]

    return "AI Generated Recipe"


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
    






def create_recipe_history_entry(
    user,
    recipe_text,
    recipe_prompt,
    preferences,
    image_path="",
    image_prompt="",
    validation_report=None,
    validation_attempt_history=None,
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
    )



@login_required
def generate_recipe_view(request):
    """
    Handles the AI recipe generation page.

    CulinaAI flow:
    1. Generate recipe using AI.
    2. Validate recipe using custom constraint-based validation engine.
    3. If validation fails, regenerate with correction instructions.
    4. If AI still fails safety validation, create a deterministic safe fallback recipe.
    5. Show a generated recipe instead of simply blocking the user.
    6. Automatically store every generated recipe in RecipeHistory.
    7. Supports Smart Pantry and personalised recommendation prefill.
    """

    if request.method == "POST":
        form = RecipeGenerationForm(request.POST)

        if form.is_valid():
            cleaned_data = form.cleaned_data

            spice_choices = dict(form.fields["spice_level"].choices)
            budget_choices = dict(form.fields["budget_level"].choices)
            nutrition_choices = dict(form.fields["nutrition_goal"].choices)
            equipment_choices = dict(form.fields["cooking_equipment"].choices)

            selected_equipment = [
                equipment_choices.get(equipment, equipment)
                for equipment in cleaned_data.get("cooking_equipment", [])
            ]

            other_diet_preference = request.POST.get(
                "other_diet_preference",
                "",
            ).strip()

            other_kitchen_equipment = request.POST.get(
                "other_kitchen_equipment",
                "",
            ).strip()

            selected_utensils = [
                utensil.strip()
                for utensil in request.POST.getlist("utensils")
                if utensil.strip()
            ]

            other_utensils = request.POST.get(
                "other_utensils",
                "",
            ).strip()

            selected_diet_preferences = [
                diet.name for diet in cleaned_data.get("diet_preferences", [])
            ]

            if other_diet_preference:
                selected_diet_preferences.append(
                    f"Other: {other_diet_preference}",
                )

            if other_kitchen_equipment:
                selected_equipment.append(
                    f"Other: {other_kitchen_equipment}",
                )

            selected_utensils_for_preview = selected_utensils.copy()

            if other_utensils:
                selected_utensils_for_preview.append(
                    f"Other: {other_utensils}",
                )

            additional_notes_parts = []

            if cleaned_data.get("additional_notes"):
                additional_notes_parts.append(
                    cleaned_data.get("additional_notes"),
                )

            if other_diet_preference:
                additional_notes_parts.append(
                    f"Custom diet preference: {other_diet_preference}",
                )

            if other_kitchen_equipment:
                additional_notes_parts.append(
                    f"Other kitchen equipment available: {other_kitchen_equipment}",
                )

            if selected_utensils_for_preview:
                additional_notes_parts.append(
                    "Available utensils: "
                    + ", ".join(selected_utensils_for_preview),
                )

            combined_additional_notes = (
                " | ".join(additional_notes_parts)
                if additional_notes_parts
                else "None provided"
            )

            preview_data = {
                "ingredients": cleaned_data.get("ingredients"),
                "cuisine": cleaned_data.get("cuisine").name
                if cleaned_data.get("cuisine")
                else "Any cuisine",
                "meal_type": cleaned_data.get("meal_type").name
                if cleaned_data.get("meal_type")
                else "Any meal type",
                "diet_preferences": selected_diet_preferences,
                "other_diet_preference": other_diet_preference,
                "allergies": cleaned_data.get("allergies") or "None provided",
                "cooking_time_minutes": cleaned_data.get("cooking_time_minutes"),
                "servings": cleaned_data.get("servings"),
                "difficulty": cleaned_data.get("difficulty"),
                "spice_level": spice_choices.get(
                    cleaned_data.get("spice_level"),
                    "Medium",
                ),
                "budget_level": budget_choices.get(
                    cleaned_data.get("budget_level"),
                    "Moderate Budget",
                ),
                "nutrition_goal": nutrition_choices.get(
                    cleaned_data.get("nutrition_goal"),
                    "Balanced",
                ),
                "cooking_equipment": selected_equipment,
                "other_kitchen_equipment": other_kitchen_equipment,
                "utensils": selected_utensils_for_preview,
                "other_utensils": other_utensils,
                "additional_notes": combined_additional_notes,
            }

            request.session["recipe_preview_data"] = preview_data
            request.session["latest_recipe_preferences"] = preview_data

            try:
                max_regeneration_attempts = 3

                current_preferences = preview_data
                final_ai_result = None
                final_validation_report = None
                validation_attempt_history = []
                fallback_used = False

                for attempt_number in range(1, max_regeneration_attempts + 1):
                    ai_result = generate_ai_recipe(current_preferences)
                    recipe_text = ai_result.get("recipe_text", "")

                    validation_report = validate_recipe_output(
                        preferences=preview_data,
                        recipe_text=recipe_text,
                        attempt_number=attempt_number,
                    )

                    validation_attempt_history.append(
                        {
                            "attempt_number": attempt_number,
                            "score": validation_report.get("score"),
                            "status": validation_report.get("status"),
                            "risk_level": validation_report.get("risk_level"),
                            "hard_fail": validation_report.get("hard_fail"),
                            "failed_checks": [
                                check.get("name")
                                for check in validation_report.get(
                                    "failed_checks",
                                    [],
                                )
                            ],
                        }
                    )

                    final_ai_result = ai_result
                    final_validation_report = validation_report

                    if not validation_report.get("should_regenerate"):
                        break

                    current_preferences = build_regeneration_preferences(
                        original_preferences=preview_data,
                        validation_report=validation_report,
                        attempt_number=attempt_number,
                    )

                if not final_ai_result or not final_validation_report:
                    messages.error(
                        request,
                        "CulinaAI could not generate a recipe. Please try again.",
                    )
                    return redirect(f"{reverse('generate_recipe')}#recipe-preview")

                if (
                    final_validation_report.get("hard_fail")
                    and final_validation_report.get("score", 0) < 70
                ):
                    fallback_ai_result = build_safe_fallback_recipe(preview_data)

                    fallback_validation_report = validate_recipe_output(
                        preferences=preview_data,
                        recipe_text=fallback_ai_result.get("recipe_text", ""),
                        attempt_number=max_regeneration_attempts + 1,
                    )

                    validation_attempt_history.append(
                        {
                            "attempt_number": max_regeneration_attempts + 1,
                            "score": fallback_validation_report.get("score"),
                            "status": "Safe fallback recipe generated",
                            "risk_level": fallback_validation_report.get("risk_level"),
                            "hard_fail": fallback_validation_report.get("hard_fail"),
                            "failed_checks": [
                                check.get("name")
                                for check in fallback_validation_report.get(
                                    "failed_checks",
                                    [],
                                )
                            ],
                        }
                    )

                    final_ai_result = fallback_ai_result
                    final_validation_report = fallback_validation_report
                    fallback_used = True

                final_ai_result["validation_report"] = final_validation_report
                final_ai_result["validation_attempt_history"] = validation_attempt_history
                final_ai_result["quality_score"] = final_validation_report.get("score")
                final_ai_result["validation_status"] = final_validation_report.get("status")

                generated_recipe_title = extract_recipe_title(
                    final_ai_result.get("recipe_text", ""),
                )

                generated_image_path = ""
                generated_image_prompt = ""

                try:
                    image_result = generate_recipe_image_base64(
                        recipe_title=generated_recipe_title,
                        preferences=preview_data,
                    )

                    generated_image_prompt = image_result.get("image_prompt", "")
                    generated_image_path = save_generated_recipe_image(
                        image_result.get("image_base64", ""),
                    )

                except Exception:
                    generated_image_path = ""
                    generated_image_prompt = ""

                final_ai_result["generated_image"] = generated_image_path
                final_ai_result["generated_image_url"] = get_storage_url(
                    generated_image_path,
                )
                final_ai_result["generated_image_prompt"] = generated_image_prompt

                request.session["ai_recipe_result"] = final_ai_result
                request.session["latest_ai_recipe_text"] = final_ai_result.get(
                    "recipe_text",
                    "",
                )
                request.session["latest_ai_recipe_prompt"] = final_ai_result.get(
                    "prompt",
                    "",
                )
                request.session["latest_recipe_image_path"] = generated_image_path
                request.session["latest_recipe_image_prompt"] = generated_image_prompt
                request.session["latest_validation_report"] = final_validation_report
                request.session["latest_validation_attempt_history"] = validation_attempt_history

                try:
                    history_entry = create_recipe_history_entry(
                        user=request.user,
                        recipe_text=final_ai_result.get("recipe_text", ""),
                        recipe_prompt=final_ai_result.get("prompt", ""),
                        preferences=preview_data,
                        image_path=generated_image_path,
                        image_prompt=generated_image_prompt,
                        validation_report=final_validation_report,
                        validation_attempt_history=validation_attempt_history,
                    )

                    if history_entry:
                        request.session["latest_recipe_history_id"] = history_entry.id

                except Exception:
                    request.session.pop("latest_recipe_history_id", None)

                if fallback_used:
                    messages.warning(
                        request,
                        "CulinaAI detected unsafe AI output and automatically created a safe corrected recipe using the validation engine.",
                    )
                elif len(validation_attempt_history) > 1:
                    messages.success(
                        request,
                        "CulinaAI checked, corrected and validated the recipe before showing the final result.",
                    )
                else:
                    messages.success(
                        request,
                        "Recipe generated, validated and added to your history successfully.",
                    )

            except Exception as error:
                # Last-resort protection:
                # If the OpenAI/API/validation/history pipeline fails, do not leave the user
                # with an empty result. Log the real error for debugging, then generate a
                # deterministic safe fallback recipe.
                print("CULINAAI REAL API GENERATION ERROR:", repr(error))
                traceback.print_exc()

                try:
                    fallback_ai_result = build_safe_fallback_recipe(preview_data)
                    fallback_recipe_text = fallback_ai_result.get("recipe_text", "")

                    try:
                        fallback_validation_report = validate_recipe_output(
                            preferences=preview_data,
                            recipe_text=fallback_recipe_text,
                            attempt_number=1,
                        )

                    except Exception as validation_error:
                        print(
                            "CULINAAI FALLBACK VALIDATION ERROR:",
                            repr(validation_error),
                        )
                        traceback.print_exc()

                        fallback_validation_report = {
                            "score": 85,
                            "status": "Verified with fallback",
                            "risk_level": "Low",
                            "badge": "Fallback Verified",
                            "target_score": 85,
                            "passed_count": 1,
                            "failed_count": 0,
                            "hard_fail": False,
                            "should_regenerate": False,
                            "checks": [
                                {
                                    "name": "Fallback Safety Check",
                                    "category": "system",
                                    "severity": "low",
                                    "passed": True,
                                    "score": 85,
                                    "max_score": 100,
                                    "message": (
                                        "A safe fallback recipe was created because "
                                        "the AI generation pipeline failed."
                                    ),
                                    "details": {},
                                }
                            ],
                            "failed_checks": [],
                        }

                    validation_attempt_history = [
                        {
                            "attempt_number": 1,
                            "score": fallback_validation_report.get("score"),
                            "status": fallback_validation_report.get("status"),
                            "risk_level": fallback_validation_report.get("risk_level"),
                            "hard_fail": fallback_validation_report.get("hard_fail"),
                            "failed_checks": [
                                check.get("name")
                                for check in fallback_validation_report.get(
                                    "failed_checks",
                                    [],
                                )
                            ],
                        }
                    ]

                    fallback_ai_result["validation_report"] = fallback_validation_report
                    fallback_ai_result["validation_attempt_history"] = (
                        validation_attempt_history
                    )
                    fallback_ai_result["quality_score"] = fallback_validation_report.get(
                        "score",
                    )
                    fallback_ai_result["validation_status"] = fallback_validation_report.get(
                        "status",
                    )
                    fallback_ai_result["generated_image"] = ""
                    fallback_ai_result["generated_image_url"] = ""
                    fallback_ai_result["generated_image_prompt"] = ""

                    request.session["ai_recipe_result"] = fallback_ai_result
                    request.session["latest_ai_recipe_text"] = fallback_recipe_text
                    request.session["latest_ai_recipe_prompt"] = fallback_ai_result.get(
                        "prompt",
                        "",
                    )
                    request.session["latest_recipe_image_path"] = ""
                    request.session["latest_recipe_image_prompt"] = ""
                    request.session["latest_validation_report"] = fallback_validation_report
                    request.session["latest_validation_attempt_history"] = (
                        validation_attempt_history
                    )

                    try:
                        history_entry = create_recipe_history_entry(
                            user=request.user,
                            recipe_text=fallback_recipe_text,
                            recipe_prompt=fallback_ai_result.get("prompt", ""),
                            preferences=preview_data,
                            image_path="",
                            image_prompt="",
                            validation_report=fallback_validation_report,
                            validation_attempt_history=validation_attempt_history,
                        )

                        if history_entry:
                            request.session["latest_recipe_history_id"] = history_entry.id

                    except Exception as history_error:
                        print("CULINAAI HISTORY ERROR:", repr(history_error))
                        traceback.print_exc()
                        request.session.pop("latest_recipe_history_id", None)

                    messages.warning(
                        request,
                        (
                            "CulinaAI could not complete the live AI generation pipeline, "
                            "so it used its safe fallback recipe generator. The recipe is "
                            "still available, and the real technical error has been printed "
                            "in the terminal for debugging."
                        ),
                    )

                except Exception as fallback_error:
                    print("CULINAAI FALLBACK GENERATION ERROR:", repr(fallback_error))
                    traceback.print_exc()

                    messages.error(
                        request,
                        (
                            "Recipe preview is ready, but both live AI generation and "
                            "the fallback generator failed. Please check the terminal "
                            "for the exact error."
                        ),
                    )


            return redirect(f"{reverse('generate_recipe')}#recipe-preview")

        messages.error(
            request,
            "Please correct the recipe generation form and try again.",
        )

    else:
        pantry_mode = request.GET.get("from_pantry") == "1"
        recommendation_query = request.GET.get("recommendation", "").strip()

        if recommendation_query:
            form = RecipeGenerationForm(
                initial={
                    "ingredients": recommendation_query,
                }
            )

            messages.info(
                request,
                "Recommended ingredients have been added to the recipe generator.",
            )

        elif pantry_mode:
            today = timezone.localdate()

            pantry_items = (
                PantryItem.objects.filter(
                    user=request.user,
                    is_available=True,
                )
                .filter(
                    Q(expiry_date__isnull=True) | Q(expiry_date__gte=today)
                )
                .order_by(
                    "expiry_date",
                    "ingredient_name",
                )
            )

            pantry_ingredients = []

            for item in pantry_items:
                clean_name = item.ingredient_name.strip()

                if clean_name:
                    pantry_ingredients.append(clean_name)

            if pantry_ingredients:
                form = RecipeGenerationForm(
                    initial={
                        "ingredients": ", ".join(pantry_ingredients),
                    }
                )

                messages.info(
                    request,
                    "Your available Smart Pantry ingredients have been added to the recipe generator. Expired items are excluded.",
                )
            else:
                form = RecipeGenerationForm()

                messages.warning(
                    request,
                    "You do not have any available non-expired pantry ingredients yet. Add pantry items first.",
                )

        else:
            form = RecipeGenerationForm()

    preview_data = request.session.pop("recipe_preview_data", None)
    ai_recipe_result = request.session.pop("ai_recipe_result", None)

    return render(
        request,
        "recipes/generate.html",
        {
            "form": form,
            "preview_data": preview_data,
            "ai_recipe_result": ai_recipe_result,
            "generation_preview": preview_data is not None,
        },
    )












@login_required
def recipe_history_view(request):
    """
    Displays all automatically generated recipe history items for the logged-in user.
    """

    history_items = (
        RecipeHistory.objects.filter(user=request.user)
        .select_related("saved_recipe")
        .order_by("-created_at")
    )

    search_query = request.GET.get("q", "").strip()
    cuisine_filter = request.GET.get("cuisine", "").strip()
    difficulty_filter = request.GET.get("difficulty", "").strip()

    if search_query:
        history_items = history_items.filter(
            Q(title__icontains=search_query)
            | Q(recipe_text__icontains=search_query)
            | Q(ingredients_text__icontains=search_query)
            | Q(cuisine_name__icontains=search_query)
            | Q(meal_type_name__icontains=search_query)
        )

    if cuisine_filter:
        history_items = history_items.filter(
            cuisine_name__iexact=cuisine_filter,
        )

    if difficulty_filter:
        history_items = history_items.filter(
            difficulty=difficulty_filter,
        )

    cuisine_options = (
        RecipeHistory.objects.filter(user=request.user)
        .exclude(cuisine_name="")
        .values_list("cuisine_name", flat=True)
        .distinct()
        .order_by("cuisine_name")
    )

    context = {
        "history_items": history_items,
        "search_query": search_query,
        "cuisine_filter": cuisine_filter,
        "difficulty_filter": difficulty_filter,
        "cuisine_options": cuisine_options,
        "difficulty_choices": Recipe.DIFFICULTY_CHOICES,
        "total_history_count": RecipeHistory.objects.filter(user=request.user).count(),
        "saved_from_history_count": RecipeHistory.objects.filter(
            user=request.user,
            saved_recipe__isnull=False,
        ).count(),
    }

    return render(request, "recipes/recipe_history.html", context)


@login_required
def recipe_history_detail_view(request, history_id):
    """
    Displays one generated recipe history item in full detail.
    """

    history_item = get_object_or_404(
        RecipeHistory.objects.select_related("saved_recipe"),
        id=history_id,
        user=request.user,
    )

    return render(
        request,
        "recipes/recipe_history_detail.html",
        {
            "history_item": history_item,
        },
    )


@login_required
def save_history_recipe_view(request, history_id):
    """
    Saves a recipe from automatic history into the user's saved recipe library.
    """

    if request.method != "POST":
        return redirect("recipe_history_detail", history_id=history_id)

    history_item = get_object_or_404(
        RecipeHistory,
        id=history_id,
        user=request.user,
    )

    if history_item.saved_recipe and history_item.saved_recipe.is_saved:
        messages.info(
            request,
            "This history recipe is already saved in your recipe library.",
        )
        return redirect(
            "saved_recipe_detail",
            recipe_id=history_item.saved_recipe.id,
        )

    cuisine = None
    meal_type = None

    if history_item.cuisine_name and history_item.cuisine_name != "Any cuisine":
        cuisine = Cuisine.objects.filter(name=history_item.cuisine_name).first()

    if history_item.meal_type_name and history_item.meal_type_name != "Any meal type":
        meal_type = MealType.objects.filter(name=history_item.meal_type_name).first()

    recipe = Recipe.objects.create(
        user=request.user,
        title=history_item.title,
        description=history_item.additional_notes,
        generated_image=history_item.generated_image.name
        if history_item.generated_image
        else None,
        cuisine=cuisine,
        meal_type=meal_type,
        ingredients_text=history_item.ingredients_text,
        instructions_text=history_item.recipe_text,
        cooking_time_minutes=history_item.cooking_time_minutes or 30,
        difficulty=history_item.difficulty or "easy",
        allergy_notes=history_item.allergies,
        ai_prompt=history_item.recipe_prompt,
        ai_response=history_item.recipe_text,
        is_ai_generated=True,
        is_saved=True,
        quality_score=history_item.quality_score,
        validation_status=history_item.validation_status,
        validation_risk_level=history_item.validation_risk_level,
        validation_badge=history_item.validation_badge,
        validation_attempts=history_item.validation_attempts,
        validation_report=history_item.validation_report,
        validation_attempt_history=history_item.validation_attempt_history,
    )

    for diet_name in history_item.dietary_preferences:
        diet = DietPreference.objects.filter(name=diet_name).first()

        if diet:
            recipe.diet_preferences.add(diet)

    history_item.saved_recipe = recipe
    history_item.save(update_fields=["saved_recipe"])

    messages.success(
        request,
        "Recipe saved from history into your recipe library.",
    )

    return redirect("saved_recipe_detail", recipe_id=recipe.id)


@login_required
def delete_recipe_history_view(request, history_id):
    """
    Deletes one recipe history item.

    This does not delete the saved recipe if the user already saved it separately.
    """

    if request.method != "POST":
        return redirect("recipe_history_detail", history_id=history_id)

    history_item = get_object_or_404(
        RecipeHistory,
        id=history_id,
        user=request.user,
    )

    history_title = history_item.title
    history_item.delete()

    messages.success(
        request,
        f'"{history_title}" was removed from your recipe history.',
    )

    return redirect("recipe_history")

































@login_required
def save_generated_recipe_view(request):
    """
    Saves the latest AI-generated recipe from the user's session into PostgreSQL.

    This version also saves CulinaAI validation evidence:
    - quality score
    - validation status
    - risk level
    - validation badge
    - validation attempt count
    - full validation report
    - generation/correction history
    """

    if request.method != "POST":
        return redirect("generate_recipe")

    recipe_text = request.session.get("latest_ai_recipe_text")
    recipe_prompt = request.session.get("latest_ai_recipe_prompt")
    recipe_image_path = request.session.get("latest_recipe_image_path")
    recipe_image_prompt = request.session.get("latest_recipe_image_prompt")
    preferences = request.session.get("latest_recipe_preferences")

    validation_report = request.session.get("latest_validation_report") or {}
    validation_attempt_history = (
        request.session.get("latest_validation_attempt_history") or []
    )

    if not recipe_text or not preferences:
        messages.error(
            request,
            "No generated recipe found to save. Please generate a recipe first.",
        )
        return redirect("generate_recipe")

    cuisine = None
    meal_type = None

    cuisine_name = preferences.get("cuisine")
    meal_type_name = preferences.get("meal_type")

    if cuisine_name and cuisine_name != "Any cuisine":
        cuisine = Cuisine.objects.filter(name=cuisine_name).first()

    if meal_type_name and meal_type_name != "Any meal type":
        meal_type = MealType.objects.filter(name=meal_type_name).first()

    quality_score = validation_report.get("score")

    recipe = Recipe.objects.create(
        user=request.user,
        title=extract_recipe_title(recipe_text),
        description=preferences.get("additional_notes", ""),
        generated_image=recipe_image_path or None,
        cuisine=cuisine,
        meal_type=meal_type,
        ingredients_text=preferences.get("ingredients", ""),
        instructions_text=recipe_text,
        cooking_time_minutes=preferences.get("cooking_time_minutes") or 30,
        difficulty=preferences.get("difficulty", "easy"),
        allergy_notes=preferences.get("allergies", ""),
        ai_prompt=recipe_prompt or "",
        ai_response=recipe_text,
        is_ai_generated=True,
        is_saved=True,

        # CulinaAI validation fields
        quality_score=quality_score if quality_score is not None else None,
        validation_status=validation_report.get("status", ""),
        validation_risk_level=validation_report.get("risk_level", ""),
        validation_badge=validation_report.get("badge", ""),
        validation_attempts=len(validation_attempt_history),
        validation_report=validation_report,
        validation_attempt_history=validation_attempt_history,
    )


    history_id = request.session.get("latest_recipe_history_id")

    if history_id:
        RecipeHistory.objects.filter(
            id=history_id,
            user=request.user,
        ).update(
            saved_recipe=recipe,
        )


    

    diet_names = preferences.get("diet_preferences", [])

    for diet_name in diet_names:
        diet = DietPreference.objects.filter(name=diet_name).first()

        if diet:
            recipe.diet_preferences.add(diet)

    request.session.pop("latest_ai_recipe_text", None)
    request.session.pop("latest_ai_recipe_prompt", None)
    request.session.pop("latest_recipe_image_path", None)
    request.session.pop("latest_recipe_image_prompt", None)
    request.session.pop("latest_recipe_preferences", None)
    request.session.pop("latest_validation_report", None)
    request.session.pop("latest_validation_attempt_history", None)
    request.session.pop("latest_recipe_history_id", None)

    messages.success(
        request,
        "Recipe saved successfully with CulinaAI validation evidence.",
    )

    return redirect("saved_recipes")


@login_required
def saved_recipes_view(request):
    """
    Displays saved recipes for the logged-in user with search and filter support.
    """

    recipes = (
        Recipe.objects.filter(
            user=request.user,
            is_saved=True,
        )
        .select_related("cuisine", "meal_type")
        .order_by("-created_at")
    )

    search_query = request.GET.get("q", "").strip()
    cuisine_id = request.GET.get("cuisine", "").strip()
    meal_type_id = request.GET.get("meal_type", "").strip()
    difficulty = request.GET.get("difficulty", "").strip()

    if search_query:
        recipes = recipes.filter(title__icontains=search_query)

    if cuisine_id:
        recipes = recipes.filter(cuisine_id=cuisine_id)

    if meal_type_id:
        recipes = recipes.filter(meal_type_id=meal_type_id)

    if difficulty:
        recipes = recipes.filter(difficulty=difficulty)

    context = {
        "recipes": recipes,
        "cuisines": Cuisine.objects.all().order_by("name"),
        "meal_types": MealType.objects.all().order_by("name"),
        "difficulty_choices": Recipe.DIFFICULTY_CHOICES,
        "search_query": search_query,
        "selected_cuisine": cuisine_id,
        "selected_meal_type": meal_type_id,
        "selected_difficulty": difficulty,
    }

    return render(request, "recipes/saved_recipes.html", context)


@login_required
@require_POST
def ask_cooking_assistant_view(request, recipe_id):
    """
    Handles AJAX requests for the AI Cooking Chat Assistant.

    The assistant is:
    - recipe-aware
    - pantry-aware
    - chat-history aware
    - saved to database
    """

    recipe = get_object_or_404(
        Recipe.objects.select_related(
            "cuisine",
            "meal_type",
        ).prefetch_related(
            "diet_preferences",
        ),
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    try:
        data = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        data = request.POST

    question = data.get("question", "").strip()
    quick_prompt_key = data.get("quick_prompt_key", "").strip()

    result = ask_cooking_assistant(
        user=request.user,
        recipe=recipe,
        question=question,
        quick_prompt_key=quick_prompt_key,
    )

    response_data = {
        "success": result.success,
        "reply": result.reply,
        "session_id": result.session.id,
        "error": result.error,
    }

    if result.user_message:
        response_data["user_message"] = {
            "id": result.user_message.id,
            "sender": result.user_message.sender,
            "message": result.user_message.message,
            "created_at": result.user_message.created_at.strftime("%d %b %Y, %H:%M"),
        }

    if result.assistant_message:
        response_data["assistant_message"] = {
            "id": result.assistant_message.id,
            "sender": result.assistant_message.sender,
            "message": result.assistant_message.message,
            "created_at": result.assistant_message.created_at.strftime("%d %b %Y, %H:%M"),
        }

    return JsonResponse(response_data)


@login_required
def saved_recipe_detail_view(request, recipe_id):
    """
    Displays one saved recipe in full detail for the logged-in user.

    Includes:
    - recipe detail
    - favourite status
    - rating and feedback
    - email recipe form
    - AI modify recipe form
    - pantry-aware shopping list
    - AI cooking chat assistant context
    """

    recipe = get_object_or_404(
        Recipe.objects.select_related(
            "cuisine",
            "meal_type",
            "original_recipe",
        ).prefetch_related(
            "diet_preferences",
        ),
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    is_favourite = FavouriteRecipe.objects.filter(
        user=request.user,
        recipe=recipe,
    ).exists()

    user_rating = RecipeRating.objects.filter(
        user=request.user,
        recipe=recipe,
    ).first()

    user_feedback_items = RecipeFeedback.objects.filter(
        user=request.user,
        recipe=recipe,
    ).order_by("-id")[:5]

    feedback_form = RecipeFeedbackForm(
        initial={
            "rating": str(user_rating.rating) if user_rating else "5",
        }
    )

    email_form = RecipeEmailForm()
    modify_form = RecipeModifyForm()

    shopping_context = build_shopping_list_context(
        recipe=recipe,
        user=request.user,
    )

    cooking_chat_context = build_cooking_chat_context(
        user=request.user,
        recipe=recipe,
    )

    modified_recipe_preview = request.session.get("modified_recipe_preview")
    preview_already_displayed = request.session.get(
        "modified_recipe_preview_displayed",
        False,
    )

    if modified_recipe_preview:
        preview_recipe_id = modified_recipe_preview.get("recipe_id")

        if preview_recipe_id != recipe.id:
            modified_recipe_preview = None

        elif preview_already_displayed:
            request.session.pop("modified_recipe_preview", None)
            request.session.pop("modified_recipe_preview_displayed", None)
            modified_recipe_preview = None

        else:
            request.session["modified_recipe_preview_displayed"] = True

    context = {
        "recipe": recipe,
        "is_favourite": is_favourite,
        "feedback_form": feedback_form,
        "email_form": email_form,
        "modify_form": modify_form,
        "modified_recipe_preview": modified_recipe_preview,
        "user_rating": user_rating,
        "user_feedback_items": user_feedback_items,
        "original_recipe": recipe.original_recipe,
        "is_modified_version": recipe.is_modified_version,

        # Pantry-aware shopping list.
        "shopping_categories": shopping_context["shopping_categories"],
        "shopping_total_items": shopping_context["shopping_total_items"],
        "shopping_total_categories": shopping_context[
            "shopping_total_categories"
        ],
        "pantry_available_items": shopping_context["pantry_available_items"],
        "pantry_missing_items": shopping_context["pantry_missing_items"],
        "pantry_available_count": shopping_context["pantry_available_count"],
        "pantry_missing_count": shopping_context["pantry_missing_count"],
        "pantry_match_score": shopping_context["pantry_match_score"],
        "pantry_has_matches": shopping_context["pantry_has_matches"],
    }

    context.update(cooking_chat_context)

    return render(
        request,
        "recipes/saved_recipe_detail.html",
        context,
    )


@login_required
def edit_saved_recipe_view(request, recipe_id):
    """
    Allows the logged-in user to edit only the saved recipe title and personal notes.
    """

    recipe = get_object_or_404(
        Recipe,
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    if request.method == "POST":
        form = SavedRecipeEditForm(request.POST, instance=recipe)

        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Your recipe title and personal notes have been updated.",
            )
            return redirect("saved_recipe_detail", recipe_id=recipe.id)

        messages.error(request, "Please correct the errors below.")
    else:
        form = SavedRecipeEditForm(instance=recipe)

    return render(
        request,
        "recipes/edit_saved_recipe.html",
        {
            "form": form,
            "recipe": recipe,
        },
    )




@login_required
def cooking_mode_view(request, recipe_id):
    """
    Displays an interactive step-by-step cooking mode for a saved recipe.

    Features:
    - step-by-step recipe guidance
    - progress tracking
    - mark step as completed
    - built-in cooking timer
    """

    recipe = get_object_or_404(
        Recipe.objects.select_related(
            "cuisine",
            "meal_type",
        ).prefetch_related(
            "diet_preferences",
        ),
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    context = build_cooking_mode_context(
        recipe=recipe,
    )

    return render(request, "recipes/cooking_mode.html", context)



@login_required
def favourite_recipes_view(request):
    """
    Displays all favourite recipes for the logged-in user.
    """

    search_query = request.GET.get("q", "").strip()
    selected_cuisine = request.GET.get("cuisine", "").strip()
    selected_meal_type = request.GET.get("meal_type", "").strip()
    selected_difficulty = request.GET.get("difficulty", "").strip()

    favourite_recipes = (
        FavouriteRecipe.objects.filter(
            user=request.user,
            recipe__is_saved=True,
        )
        .select_related(
            "recipe",
            "recipe__cuisine",
            "recipe__meal_type",
        )
        .prefetch_related(
            "recipe__diet_preferences",
        )
        .order_by("-created_at")
    )

    if search_query:
        favourite_recipes = favourite_recipes.filter(
            Q(recipe__title__icontains=search_query)
            | Q(recipe__description__icontains=search_query)
            | Q(recipe__ingredients_text__icontains=search_query)
            | Q(recipe__instructions_text__icontains=search_query)
            | Q(recipe__cuisine__name__icontains=search_query)
            | Q(recipe__meal_type__name__icontains=search_query)
            | Q(recipe__diet_preferences__name__icontains=search_query)
        )

    if selected_cuisine:
        favourite_recipes = favourite_recipes.filter(
            recipe__cuisine_id=selected_cuisine,
        )

    if selected_meal_type:
        favourite_recipes = favourite_recipes.filter(
            recipe__meal_type_id=selected_meal_type,
        )

    if selected_difficulty:
        favourite_recipes = favourite_recipes.filter(
            recipe__difficulty=selected_difficulty,
        )

    favourite_recipes = favourite_recipes.distinct()

    cuisines = Cuisine.objects.all().order_by("name")
    meal_types = MealType.objects.all().order_by("name")

    difficulties = [
        ("easy", "Easy"),
        ("medium", "Medium"),
        ("hard", "Hard"),
    ]

    has_active_filters = any(
        [
            search_query,
            selected_cuisine,
            selected_meal_type,
            selected_difficulty,
        ]
    )

    return render(
        request,
        "recipes/favourite_recipes.html",
        {
            "favourite_recipes": favourite_recipes,
            "cuisines": cuisines,
            "meal_types": meal_types,
            "difficulties": difficulties,
            "search_query": search_query,
            "selected_cuisine": selected_cuisine,
            "selected_meal_type": selected_meal_type,
            "selected_difficulty": selected_difficulty,
            "has_active_filters": has_active_filters,
        },
    )


@login_required
def submit_recipe_feedback_view(request, recipe_id):
    """
    Saves or updates a user's rating and optional feedback comment for a saved recipe.
    """

    if request.method != "POST":
        return redirect("saved_recipe_detail", recipe_id=recipe_id)

    recipe = get_object_or_404(
        Recipe,
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    form = RecipeFeedbackForm(request.POST)

    if form.is_valid():
        rating_value = int(form.cleaned_data["rating"])
        comment = form.cleaned_data.get("comment", "").strip()

        RecipeRating.objects.update_or_create(
            user=request.user,
            recipe=recipe,
            defaults={
                "rating": rating_value,
            },
        )

        if comment:
            RecipeFeedback.objects.create(
                user=request.user,
                recipe=recipe,
                comment=comment,
            )

        messages.success(
            request,
            "Thank you. Your rating and feedback have been saved.",
        )
    else:
        messages.error(
            request,
            "Please check your rating and feedback before submitting.",
        )

    return redirect("saved_recipe_detail", recipe_id=recipe.id)


@login_required
def send_recipe_email_view(request, recipe_id):
    """
    Sends a saved recipe to a user-provided email address.
    """

    if request.method != "POST":
        return redirect("saved_recipe_detail", recipe_id=recipe_id)

    recipe = get_object_or_404(
        Recipe,
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    form = RecipeEmailForm(request.POST)

    if form.is_valid():
        recipient_email = form.cleaned_data["recipient_email"]
        optional_message = form.cleaned_data.get("message", "").strip()

        subject = f"CulinaAI Recipe: {recipe.title}"

        email_body = f"""
Hello,

{request.user.username} has shared a CulinaAI recipe with you.

{optional_message}

Recipe: {recipe.title}

Ingredients:
{recipe.ingredients_text}

Allergy and safety notes:
{recipe.allergy_notes or "No allergy notes provided. Please check ingredients manually before cooking."}

Recipe instructions:
{recipe.instructions_text}

Enjoy cooking,
CulinaAI
"""

        send_mail(
            subject=subject,
            message=email_body,
            from_email=None,
            recipient_list=[recipient_email],
            fail_silently=False,
        )

        messages.success(request, f"Recipe sent successfully to {recipient_email}.")
    else:
        messages.error(request, "Please enter a valid email address before sending.")

    return redirect("saved_recipe_detail", recipe_id=recipe.id)


@login_required
def toggle_favourite_recipe_view(request, recipe_id):
    """
    Adds or removes a saved recipe from favourites.
    """

    if request.method != "POST":
        return redirect("saved_recipe_detail", recipe_id=recipe_id)

    recipe = get_object_or_404(
        Recipe,
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    favourite, created = FavouriteRecipe.objects.get_or_create(
        user=request.user,
        recipe=recipe,
    )

    if created:
        messages.success(request, "Recipe added to favourites.")
    else:
        favourite.delete()
        messages.info(request, "Recipe removed from favourites.")

    return redirect("saved_recipe_detail", recipe_id=recipe.id)


@login_required
def modify_saved_recipe_view(request, recipe_id):
    """
    Handles AI-powered modification requests for an existing saved recipe.
    """

    if request.method != "POST":
        return redirect("saved_recipe_detail", recipe_id=recipe_id)

    recipe = get_object_or_404(
        Recipe,
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    form = RecipeModifyForm(request.POST)

    if form.is_valid():
        modification_type = form.cleaned_data["modification_type"]
        custom_instruction = form.cleaned_data.get("custom_instruction", "").strip()

        try:
            ai_result = modify_ai_recipe(
                recipe=recipe,
                modification_type=modification_type,
                custom_instruction=custom_instruction,
            )

            request.session["modified_recipe_preview"] = {
                "recipe_id": recipe.id,
                "modification_type": modification_type,
                "custom_instruction": custom_instruction,
                "prompt": ai_result.get("prompt", ""),
                "modified_recipe_text": ai_result.get("modified_recipe_text", ""),
            }

            request.session["modified_recipe_preview_displayed"] = False

            messages.success(
                request,
                "AI modification generated successfully. Review the modified recipe below.",
            )

        except Exception:
            messages.error(
                request,
                "AI modification failed. Please check your OpenAI API key, billing credits, or connection.",
            )

        return redirect(
            f"{reverse('saved_recipe_detail', args=[recipe.id])}#culina-modified-preview"
        )

    messages.error(request, "Please check the recipe modification form and try again.")
    return redirect(
        f"{reverse('saved_recipe_detail', args=[recipe.id])}#culina-modify-recipe"
    )


@login_required
def save_modified_recipe_view(request, recipe_id):
    """
    Saves the AI-modified recipe preview as a new saved recipe.
    """

    if request.method != "POST":
        return redirect("saved_recipe_detail", recipe_id=recipe_id)

    original_recipe = get_object_or_404(
        Recipe,
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    modified_preview = request.session.get("modified_recipe_preview")

    if not modified_preview:
        messages.error(request, "No modified recipe preview found to save.")
        return redirect("saved_recipe_detail", recipe_id=original_recipe.id)

    if modified_preview.get("recipe_id") != original_recipe.id:
        messages.error(
            request,
            "This modified recipe preview does not match the current recipe.",
        )
        return redirect("saved_recipe_detail", recipe_id=original_recipe.id)

    modified_recipe_text = modified_preview.get("modified_recipe_text", "").strip()
    modification_type = modified_preview.get("modification_type", "")
    custom_instruction = modified_preview.get("custom_instruction", "")
    modification_prompt = modified_preview.get("prompt", "")

    if not modified_recipe_text:
        messages.error(request, "Modified recipe text is empty and cannot be saved.")
        return redirect("saved_recipe_detail", recipe_id=original_recipe.id)

    new_recipe = Recipe.objects.create(
        user=request.user,
        title=extract_recipe_title(modified_recipe_text),
        description=f"Modified version of: {original_recipe.title}",
        generated_image=original_recipe.generated_image,
        cuisine=original_recipe.cuisine,
        meal_type=original_recipe.meal_type,
        original_recipe=original_recipe,
        modification_type=modification_type,
        modification_instruction=custom_instruction,
        ingredients_text=original_recipe.ingredients_text,
        instructions_text=modified_recipe_text,
        cooking_time_minutes=original_recipe.cooking_time_minutes,
        difficulty=original_recipe.difficulty,
        allergy_notes=original_recipe.allergy_notes,
        ai_prompt=modification_prompt,
        ai_response=modified_recipe_text,
        is_ai_generated=True,
        is_saved=True,
    )

    for diet in original_recipe.diet_preferences.all():
        new_recipe.diet_preferences.add(diet)

    request.session.pop("modified_recipe_preview", None)
    request.session.pop("modified_recipe_preview_displayed", None)

    messages.success(request, "Modified recipe saved successfully as a new saved recipe.")
    return redirect("saved_recipe_detail", recipe_id=new_recipe.id)


@login_required
def delete_saved_recipe_confirm_view(request, recipe_id):
    """
    Shows a confirmation page before deleting a saved recipe.
    """

    recipe = get_object_or_404(
        Recipe,
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    modified_versions_count = recipe.modified_versions.filter(
        user=request.user,
        is_saved=True,
    ).count()

    context = {
        "recipe": recipe,
        "modified_versions_count": modified_versions_count,
    }

    return render(request, "recipes/delete_saved_recipe_confirm.html", context)


@login_required
def delete_saved_recipe_view(request, recipe_id):
    """
    Deletes a saved recipe from the logged-in user's recipe library.
    """

    if request.method != "POST":
        return redirect("delete_saved_recipe_confirm", recipe_id=recipe_id)

    recipe = get_object_or_404(
        Recipe,
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    recipe_title = recipe.title
    recipe.delete()

    messages.success(
        request,
        f'"{recipe_title}" was deleted from your saved recipes.',
    )

    return redirect("saved_recipes")


@login_required
def print_saved_recipe_view(request, recipe_id):
    """
    Displays a clean print/export version of a saved recipe.
    """

    recipe = get_object_or_404(
        Recipe,
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    return render(
        request,
        "recipes/print_recipe.html",
        {
            "recipe": recipe,
        },
    )






















@login_required
def toggle_community_recipe_view(request, recipe_id):
    """
    Allows a recipe owner to add or remove a saved recipe from the community.

    Private saved recipes stay private by default. A recipe becomes visible in
    the community only when the owner explicitly shares it.
    """

    if request.method != "POST":
        return redirect("saved_recipe_detail", recipe_id=recipe_id)

    recipe = get_object_or_404(
        Recipe,
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    if recipe.is_public:
        recipe.is_public = False
        recipe.public_shared_at = None
        recipe.save(
            update_fields=[
                "is_public",
                "public_shared_at",
                "updated_at",
            ]
        )

        messages.info(
            request,
            "Recipe removed from the community. It is now private again.",
        )
    else:
        recipe.is_public = True
        recipe.public_shared_at = timezone.now()
        recipe.save(
            update_fields=[
                "is_public",
                "public_shared_at",
                "updated_at",
            ]
        )

        messages.success(
            request,
            "Recipe added to the community successfully.",
        )

    return redirect("saved_recipe_detail", recipe_id=recipe.id)


@login_required
def community_recipes_view(request):
    """
    Displays public community recipes shared by users.

    This page uses database records dynamically. Only recipes with is_public=True
    appear here. Search, filters, sorting and featured slider data are prepared
    for the community recipe UI.
    """

    search_query = request.GET.get("q", "").strip()
    selected_cuisine = request.GET.get("cuisine", "").strip()
    selected_meal_type = request.GET.get("meal_type", "").strip()
    selected_difficulty = request.GET.get("difficulty", "").strip()
    sort_filter = request.GET.get("sort", "latest").strip()

    community_recipes = (
        Recipe.objects.filter(
            is_saved=True,
            is_public=True,
        )
        .select_related(
            "user",
            "cuisine",
            "meal_type",
        )
        .prefetch_related(
            "diet_preferences",
        )
        .annotate(
            average_rating_value=Avg("ratings__rating"),
            rating_total=Count("ratings", distinct=True),
            feedback_total=Count("feedback", distinct=True),
        )
    )

    if search_query:
        community_recipes = community_recipes.filter(
            Q(title__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(ingredients_text__icontains=search_query)
            | Q(instructions_text__icontains=search_query)
            | Q(ai_response__icontains=search_query)
            | Q(user__username__icontains=search_query)
            | Q(cuisine__name__icontains=search_query)
            | Q(meal_type__name__icontains=search_query)
            | Q(diet_preferences__name__icontains=search_query)
        )

    if selected_cuisine:
        community_recipes = community_recipes.filter(
            cuisine_id=selected_cuisine,
        )

    if selected_meal_type:
        community_recipes = community_recipes.filter(
            meal_type_id=selected_meal_type,
        )

    if selected_difficulty:
        community_recipes = community_recipes.filter(
            difficulty=selected_difficulty,
        )

    community_recipes = community_recipes.distinct()

    if sort_filter == "oldest":
        community_recipes = community_recipes.order_by(
            "public_shared_at",
            "created_at",
        )
    elif sort_filter == "rating":
        community_recipes = community_recipes.order_by(
            "-average_rating_value",
            "-rating_total",
            "-public_shared_at",
            "-created_at",
        )
    elif sort_filter == "views":
        community_recipes = community_recipes.order_by(
            "-community_views",
            "-public_shared_at",
            "-created_at",
        )
    elif sort_filter == "feedback":
        community_recipes = community_recipes.order_by(
            "-feedback_total",
            "-public_shared_at",
            "-created_at",
        )
    else:
        community_recipes = community_recipes.order_by(
            "-public_shared_at",
            "-created_at",
        )

    featured_recipes = (
        Recipe.objects.filter(
            is_saved=True,
            is_public=True,
        )
        .select_related(
            "user",
            "cuisine",
            "meal_type",
        )
        .prefetch_related(
            "diet_preferences",
        )
        .annotate(
            average_rating_value=Avg("ratings__rating"),
            rating_total=Count("ratings", distinct=True),
            feedback_total=Count("feedback", distinct=True),
        )
        .order_by(
            "-community_views",
            "-average_rating_value",
            "-public_shared_at",
            "-created_at",
        )[:8]
    )

    has_active_filters = any(
        [
            search_query,
            selected_cuisine,
            selected_meal_type,
            selected_difficulty,
            sort_filter != "latest",
        ]
    )

    context = {
        "community_recipes": community_recipes,
        "featured_recipes": featured_recipes,
        "cuisines": Cuisine.objects.all().order_by("name"),
        "meal_types": MealType.objects.all().order_by("name"),
        "difficulty_choices": Recipe.DIFFICULTY_CHOICES,
        "sort_filter": sort_filter,
        "search_query": search_query,
        "selected_cuisine": selected_cuisine,
        "selected_meal_type": selected_meal_type,
        "selected_difficulty": selected_difficulty,
        "has_active_filters": has_active_filters,
    }

    return render(request, "recipes/community_recipes.html", context)


@login_required
def community_recipe_detail_view(request, recipe_id):
    """
    Displays the full detail page for a public community recipe.

    Users can view the shared recipe, see engagement information and submit
    rating/feedback. The recipe view count is increased whenever the public
    detail page is opened.
    """

    recipe = get_object_or_404(
        Recipe.objects.select_related(
            "user",
            "cuisine",
            "meal_type",
        ).prefetch_related(
            "diet_preferences",
        ),
        id=recipe_id,
        is_saved=True,
        is_public=True,
    )

    Recipe.objects.filter(
        id=recipe.id,
    ).update(
        community_views=F("community_views") + 1,
    )

    recipe.refresh_from_db(
        fields=[
            "community_views",
        ]
    )

    user_rating = RecipeRating.objects.filter(
        user=request.user,
        recipe=recipe,
    ).first()

    feedback_items = (
        RecipeFeedback.objects.filter(
            recipe=recipe,
        )
        .select_related("user")
        .order_by("-created_at")[:20]
    )

    feedback_form = RecipeFeedbackForm(
        initial={
            "rating": str(user_rating.rating) if user_rating else "5",
        }
    )

    related_recipes = (
        Recipe.objects.filter(
            is_saved=True,
            is_public=True,
        )
        .exclude(id=recipe.id)
        .select_related(
            "user",
            "cuisine",
            "meal_type",
        )
        .annotate(
            average_rating_value=Avg("ratings__rating"),
            feedback_total=Count("feedback", distinct=True),
        )
    )

    if recipe.cuisine_id:
        related_recipes = related_recipes.filter(
            cuisine_id=recipe.cuisine_id,
        )

    related_recipes = related_recipes.order_by(
        "-average_rating_value",
        "-community_views",
        "-public_shared_at",
    )[:3]

    context = {
        "recipe": recipe,
        "feedback_form": feedback_form,
        "feedback_items": feedback_items,
        "user_rating": user_rating,
        "related_recipes": related_recipes,
        "is_owner": recipe.user == request.user,
        "average_rating": recipe.average_rating,
        "feedback_count": recipe.feedback_count,
    }

    return render(request, "recipes/community_recipe_detail.html", context)


@login_required
def submit_community_recipe_feedback_view(request, recipe_id):
    """
    Saves or updates rating and feedback for a public community recipe.

    Each user has one rating per recipe, while feedback comments can be added
    over time. This data will later support the Evaluation Dashboard.
    """

    if request.method != "POST":
        return redirect("community_recipe_detail", recipe_id=recipe_id)

    recipe = get_object_or_404(
        Recipe,
        id=recipe_id,
        is_saved=True,
        is_public=True,
    )

    form = RecipeFeedbackForm(request.POST)

    if form.is_valid():
        rating_value = int(form.cleaned_data["rating"])
        comment = form.cleaned_data.get("comment", "").strip()

        RecipeRating.objects.update_or_create(
            user=request.user,
            recipe=recipe,
            defaults={
                "rating": rating_value,
            },
        )

        if comment:
            RecipeFeedback.objects.create(
                user=request.user,
                recipe=recipe,
                comment=comment,
            )

        messages.success(
            request,
            "Thank you. Your community rating and feedback have been saved.",
        )
    else:
        messages.error(
            request,
            "Please check your rating and feedback before submitting.",
        )

    return redirect("community_recipe_detail", recipe_id=recipe.id)





















@login_required
def quality_dashboard_view(request):
    """
    Staff-only CulinaAI quality dashboard.

    Stage 3C:
    Adds advanced analytics plus filtering/search for admin recipe records.
    """

    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(
            request,
            "You do not have permission to access the CulinaAI quality dashboard.",
        )
        return redirect("home")

    recipes = Recipe.objects.filter(
        is_ai_generated=True,
        is_saved=True,
    )

    validated_recipes = recipes.filter(
        quality_score__isnull=False,
    )

    total_ai_recipes = recipes.count()
    validated_count = validated_recipes.count()
    unvalidated_count = total_ai_recipes - validated_count

    scores = list(
        validated_recipes.values_list(
            "quality_score",
            flat=True,
        )
    )

    if scores:
        average_score = round(sum(scores) / len(scores), 1)
        highest_score = max(scores)
        lowest_score = min(scores)
    else:
        average_score = 0
        highest_score = 0
        lowest_score = 0

    excellent_count = validated_recipes.filter(
        quality_score__gte=85,
    ).count()

    verified_count = validated_recipes.filter(
        quality_score__gte=70,
        quality_score__lt=85,
    ).count()

    moderate_count = validated_recipes.filter(
        quality_score__gte=50,
        quality_score__lt=70,
    ).count()

    needs_review_count = validated_recipes.filter(
        quality_score__lt=50,
    ).count()

    low_risk_count = validated_recipes.filter(
        validation_risk_level__icontains="low",
    ).count()

    medium_risk_count = validated_recipes.filter(
        validation_risk_level__icontains="medium",
    ).count()

    high_risk_count = validated_recipes.filter(
        validation_risk_level__icontains="high",
    ).count()

    first_attempt_count = validated_recipes.filter(
        validation_attempts__lte=1,
    ).count()

    corrected_count = validated_recipes.filter(
        validation_attempts__gt=1,
    ).count()

    attempt_values = list(
        validated_recipes.values_list(
            "validation_attempts",
            flat=True,
        )
    )

    if attempt_values:
        average_attempts = round(sum(attempt_values) / len(attempt_values), 1)
    else:
        average_attempts = 0

    def percentage(part, total):
        if not total:
            return 0
        return round((part / total) * 100, 1)

    validation_coverage_rate = percentage(validated_count, total_ai_recipes)
    unvalidated_rate = percentage(unvalidated_count, total_ai_recipes)
    first_attempt_rate = percentage(first_attempt_count, validated_count)
    regeneration_rate = percentage(corrected_count, validated_count)

    fallback_count = 0
    issue_counter = Counter()

    for recipe in validated_recipes:
        report = recipe.validation_report or {}
        attempt_history = recipe.validation_attempt_history or []

        combined_text = (
            f"{recipe.validation_status} "
            f"{recipe.validation_badge} "
            f"{report} "
            f"{attempt_history}"
        ).lower()

        if "fallback" in combined_text:
            fallback_count += 1

        if recipe.quality_score is not None and recipe.quality_score < 85:
            issue_counter["Score below excellent threshold"] += 1

        if recipe.validation_risk_level:
            risk_text = recipe.validation_risk_level.lower()

            if "medium" in risk_text:
                issue_counter["Medium risk validation result"] += 1

            if "high" in risk_text:
                issue_counter["High risk validation result"] += 1

        if isinstance(report, dict):
            possible_check_lists = [
                report.get("checks"),
                report.get("criteria"),
                report.get("validation_checks"),
                report.get("check_results"),
            ]

            for check_list in possible_check_lists:
                if not isinstance(check_list, list):
                    continue

                for check in check_list:
                    if not isinstance(check, dict):
                        continue

                    check_name = (
                        check.get("name")
                        or check.get("category")
                        or check.get("title")
                        or check.get("criterion")
                        or "Validation check"
                    )

                    check_status = str(
                        check.get("status")
                        or check.get("result")
                        or ""
                    ).lower()

                    check_passed = check.get("passed")

                    if (
                        check_passed is False
                        or "fail" in check_status
                        or "warning" in check_status
                        or "review" in check_status
                    ):
                        issue_counter[str(check_name)] += 1

            warning_items = report.get("warnings") or report.get("issues") or []

            if isinstance(warning_items, list):
                for warning in warning_items:
                    if isinstance(warning, str) and warning.strip():
                        issue_counter[warning.strip()] += 1

    if unvalidated_count:
        issue_counter["Older recipes without stored validation evidence"] += unvalidated_count

    common_issues = [
        {
            "label": label,
            "count": count,
        }
        for label, count in issue_counter.most_common(5)
    ]

    staff_review_recipes = recipes.filter(
        Q(quality_score__lt=85)
        | Q(quality_score__isnull=True)
        | Q(validation_risk_level__icontains="medium")
        | Q(validation_risk_level__icontains="high")
    ).select_related(
        "user",
        "cuisine",
        "meal_type",
    ).order_by("-created_at")[:6]

    staff_review_count = recipes.filter(
        Q(quality_score__lt=85)
        | Q(quality_score__isnull=True)
        | Q(validation_risk_level__icontains="medium")
        | Q(validation_risk_level__icontains="high")
    ).count()

    if average_score >= 85 and high_risk_count == 0:
        quality_health_label = "Excellent"
        quality_health_text = (
            "The validation system is performing strongly with high average quality "
            "and no high-risk records."
        )
    elif average_score >= 70:
        quality_health_label = "Stable"
        quality_health_text = (
            "The validation system is generally stable, but some records may still "
            "require staff review."
        )
    else:
        quality_health_label = "Needs Review"
        quality_health_text = (
            "The validation system has lower scoring records, so staff review is recommended."
        )

    # Stage 3C filter controls for the recipe records table.
    search_query = request.GET.get("q", "").strip()
    validation_filter = request.GET.get("validation", "all")
    risk_filter = request.GET.get("risk", "all")
    sort_filter = request.GET.get("sort", "latest")

    filtered_recipes = recipes.select_related(
        "user",
        "cuisine",
        "meal_type",
    )

    if search_query:
        filtered_recipes = filtered_recipes.filter(
            Q(title__icontains=search_query)
            | Q(user__username__icontains=search_query)
            | Q(cuisine__name__icontains=search_query)
            | Q(meal_type__name__icontains=search_query)
        )

    if validation_filter == "validated":
        filtered_recipes = filtered_recipes.filter(
            quality_score__isnull=False,
        )
    elif validation_filter == "unvalidated":
        filtered_recipes = filtered_recipes.filter(
            quality_score__isnull=True,
        )
    elif validation_filter == "excellent":
        filtered_recipes = filtered_recipes.filter(
            quality_score__gte=85,
        )
    elif validation_filter == "below_excellent":
        filtered_recipes = filtered_recipes.filter(
            Q(quality_score__lt=85) | Q(quality_score__isnull=True)
        )
    elif validation_filter == "needs_review":
        filtered_recipes = filtered_recipes.filter(
            Q(quality_score__lt=70)
            | Q(quality_score__isnull=True)
            | Q(validation_risk_level__icontains="medium")
            | Q(validation_risk_level__icontains="high")
        )

    if risk_filter == "low":
        filtered_recipes = filtered_recipes.filter(
            validation_risk_level__icontains="low",
        )
    elif risk_filter == "medium":
        filtered_recipes = filtered_recipes.filter(
            validation_risk_level__icontains="medium",
        )
    elif risk_filter == "high":
        filtered_recipes = filtered_recipes.filter(
            validation_risk_level__icontains="high",
        )
    elif risk_filter == "unknown":
        filtered_recipes = filtered_recipes.filter(
            Q(validation_risk_level__isnull=True)
            | Q(validation_risk_level="")
        )

    if sort_filter == "oldest":
        filtered_recipes = filtered_recipes.order_by("created_at")
    elif sort_filter == "score_high":
        filtered_recipes = filtered_recipes.order_by("-quality_score", "-created_at")
    elif sort_filter == "score_low":
        filtered_recipes = filtered_recipes.order_by("quality_score", "-created_at")
    else:
        filtered_recipes = filtered_recipes.order_by("-created_at")

    filtered_recipe_count = filtered_recipes.count()
    filtered_recipes = filtered_recipes[:30]

    context = {
        "total_ai_recipes": total_ai_recipes,
        "validated_count": validated_count,
        "unvalidated_count": unvalidated_count,
        "average_score": average_score,
        "excellent_count": excellent_count,
        "verified_count": verified_count,
        "moderate_count": moderate_count,
        "needs_review_count": needs_review_count,
        "low_risk_count": low_risk_count,
        "medium_risk_count": medium_risk_count,
        "high_risk_count": high_risk_count,
        "first_attempt_count": first_attempt_count,
        "corrected_count": corrected_count,
        "recent_recipes": filtered_recipes,
        "filtered_recipe_count": filtered_recipe_count,
        "search_query": search_query,
        "validation_filter": validation_filter,
        "risk_filter": risk_filter,
        "sort_filter": sort_filter,
        "validation_coverage_rate": validation_coverage_rate,
        "unvalidated_rate": unvalidated_rate,
        "first_attempt_rate": first_attempt_rate,
        "regeneration_rate": regeneration_rate,
        "fallback_count": fallback_count,
        "average_attempts": average_attempts,
        "highest_score": highest_score,
        "lowest_score": lowest_score,
        "staff_review_recipes": staff_review_recipes,
        "staff_review_count": staff_review_count,
        "common_issues": common_issues,
        "quality_health_label": quality_health_label,
        "quality_health_text": quality_health_text,
    }

    return render(request, "recipes/quality_dashboard.html", context)




































@login_required
def quality_recipe_evidence_view(request, recipe_id):
    """
    Staff-only validation evidence detail page.

    Allows staff/admin users to inspect human-readable validation evidence,
    stored validation report, attempt history and saved AI recipe output.
    """

    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(
            request,
            "You do not have permission to access this validation evidence page.",
        )
        return redirect("home")

    recipe = get_object_or_404(
        Recipe.objects.select_related(
            "user",
            "cuisine",
            "meal_type",
        ),
        id=recipe_id,
        is_ai_generated=True,
        is_saved=True,
    )

    validation_report = recipe.validation_report or {}
    validation_attempt_history = recipe.validation_attempt_history or []

    validation_report_pretty = json.dumps(
        validation_report,
        indent=2,
        ensure_ascii=False,
        default=str,
    )

    validation_attempt_history_pretty = json.dumps(
        validation_attempt_history,
        indent=2,
        ensure_ascii=False,
        default=str,
    )

    # Main saved AI output.
    # Your Recipe model stores the full AI output in ai_response.
    recipe_content = recipe.ai_response.strip() if recipe.ai_response else ""

    # Fallback for older/manual records where ai_response may be empty.
    if not recipe_content:
        fallback_parts = []

        if recipe.description:
            fallback_parts.append(f"Description:\n{recipe.description}")

        if recipe.ingredients_text:
            fallback_parts.append(f"Ingredients:\n{recipe.ingredients_text}")

        if recipe.instructions_text:
            fallback_parts.append(f"Instructions:\n{recipe.instructions_text}")

        recipe_content = "\n\n".join(fallback_parts)

    def get_first_existing(check_data, possible_keys, default=""):
        for key in possible_keys:
            value = check_data.get(key)

            if value is not None and value != "":
                return value

        return default

    def build_score_text(check_data):
        awarded = get_first_existing(
            check_data,
            [
                "score_awarded",
                "awarded_score",
                "points_awarded",
                "score",
                "points",
            ],
            None,
        )

        maximum = get_first_existing(
            check_data,
            [
                "max_score",
                "maximum_score",
                "max_points",
                "total_points",
                "out_of",
            ],
            None,
        )

        if awarded is not None and maximum is not None:
            return f"{awarded}/{maximum}"

        if awarded is not None:
            return str(awarded)

        return ""

    def build_readable_check(check_data, fallback_name="Validation check"):
        check_name = get_first_existing(
            check_data,
            [
                "name",
                "category",
                "title",
                "criterion",
                "check",
                "label",
            ],
            fallback_name,
        )

        message = get_first_existing(
            check_data,
            [
                "message",
                "detail",
                "details",
                "explanation",
                "reason",
                "note",
                "notes",
                "feedback",
            ],
            "No extra explanation stored for this check.",
        )

        raw_status = str(
            get_first_existing(
                check_data,
                [
                    "status",
                    "result",
                    "outcome",
                    "state",
                ],
                "",
            )
        ).lower()

        passed = get_first_existing(
            check_data,
            [
                "passed",
                "is_passed",
                "success",
                "valid",
            ],
            None,
        )

        hard_fail = get_first_existing(
            check_data,
            [
                "hard_fail",
                "critical_fail",
                "failed",
            ],
            False,
        )

        if passed is True or raw_status in ["passed", "pass", "success", "verified"]:
            status_label = "Passed"
            css_class = "check-passed"
            icon = "bi-check-circle-fill"
        elif hard_fail is True or passed is False or "fail" in raw_status:
            status_label = "Failed"
            css_class = "check-failed"
            icon = "bi-x-circle-fill"
        elif "warning" in raw_status or "review" in raw_status or "moderate" in raw_status:
            status_label = "Warning"
            css_class = "check-warning"
            icon = "bi-exclamation-triangle-fill"
        else:
            status_label = "Recorded"
            css_class = "check-info"
            icon = "bi-info-circle-fill"

        return {
            "label": str(check_name).replace("_", " ").title(),
            "message": str(message),
            "score_text": build_score_text(check_data),
            "status_label": status_label,
            "css_class": css_class,
            "icon": icon,
        }

    readable_validation_checks = []

    if isinstance(validation_report, dict):
        possible_check_lists = [
            validation_report.get("checks"),
            validation_report.get("criteria"),
            validation_report.get("validation_checks"),
            validation_report.get("check_results"),
            validation_report.get("score_breakdown"),
            validation_report.get("criteria_results"),
            validation_report.get("results"),
        ]

        for check_list in possible_check_lists:
            if isinstance(check_list, list):
                for check in check_list:
                    if isinstance(check, dict):
                        readable_validation_checks.append(
                            build_readable_check(check)
                        )

            elif isinstance(check_list, dict):
                for key, value in check_list.items():
                    if isinstance(value, dict):
                        readable_validation_checks.append(
                            build_readable_check(value, fallback_name=key)
                        )
                    else:
                        readable_validation_checks.append(
                            {
                                "label": str(key).replace("_", " ").title(),
                                "message": f"Stored value: {value}",
                                "score_text": "",
                                "status_label": "Recorded",
                                "css_class": "check-info",
                                "icon": "bi-info-circle-fill",
                            }
                        )

        warning_items = validation_report.get("warnings") or validation_report.get("issues") or []

        if isinstance(warning_items, list):
            for warning in warning_items:
                if warning:
                    readable_validation_checks.append(
                        {
                            "label": "Validation Warning",
                            "message": str(warning),
                            "score_text": "",
                            "status_label": "Warning",
                            "css_class": "check-warning",
                            "icon": "bi-exclamation-triangle-fill",
                        }
                    )

    # Fallback readable evidence if no detailed check list exists in JSON.
    if not readable_validation_checks:
        readable_validation_checks = [
            {
                "label": "Overall Quality Score",
                "message": "Final stored quality score produced by the CulinaAI validation engine.",
                "score_text": f"{recipe.quality_score}/100" if recipe.quality_score is not None else "Not stored",
                "status_label": "Recorded",
                "css_class": "check-info",
                "icon": "bi-speedometer2",
            },
            {
                "label": "Validation Status",
                "message": recipe.validation_status or "No validation status was stored for this recipe.",
                "score_text": "",
                "status_label": "Recorded",
                "css_class": "check-info",
                "icon": "bi-patch-check-fill",
            },
            {
                "label": "Risk Level",
                "message": recipe.validation_risk_level or "No risk level was stored for this recipe.",
                "score_text": "",
                "status_label": "Recorded",
                "css_class": "check-info",
                "icon": "bi-shield-exclamation",
            },
            {
                "label": "Validation Attempts",
                "message": "Number of generation, correction or fallback attempts stored for this recipe.",
                "score_text": str(recipe.validation_attempts or 0),
                "status_label": "Recorded",
                "css_class": "check-info",
                "icon": "bi-arrow-repeat",
            },
        ]

    context = {
        "recipe": recipe,
        "recipe_content": recipe_content,
        "readable_validation_checks": readable_validation_checks,
        "validation_report_pretty": validation_report_pretty,
        "validation_attempt_history_pretty": validation_attempt_history_pretty,
    }

    return render(request, "recipes/quality_recipe_evidence.html", context)
















@login_required
def unsave_recipe_view(request, recipe_id):
    """
    Removes a saved recipe from the user's saved recipe library without
    permanently deleting the recipe record.

    This keeps validation evidence and recipe history in the database,
    but hides the recipe from the saved recipes page.
    """

    if request.method != "POST":
        return redirect("saved_recipe_detail", recipe_id=recipe_id)

    recipe = get_object_or_404(
        Recipe,
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    recipe_title = recipe.title

    # Remove favourite connection if the recipe was favourited.
    FavouriteRecipe.objects.filter(
        user=request.user,
        recipe=recipe,
    ).delete()

    # If the recipe was shared publicly, make it private again.
    recipe.is_saved = False
    recipe.is_public = False
    recipe.public_shared_at = None

    recipe.save(
        update_fields=[
            "is_saved",
            "is_public",
            "public_shared_at",
            "updated_at",
        ]
    )

    messages.success(
        request,
        f'"{recipe_title}" has been removed from your saved recipes.',
    )

    return redirect("saved_recipes")
















@login_required
def pantry_list_view(request):
    """
    Displays the logged-in user's Smart Pantry items and handles adding new items.

    Supports:
    - single pantry item add
    - bulk pantry item add
    - expiry insight
    - personalised recommendations
    """

    today = timezone.localdate()
    soon_date = today + timedelta(days=3)

    if request.method == "POST":
        pantry_action = request.POST.get("pantry_action", "single_add")

        if pantry_action == "bulk_add":
            ingredient_names = request.POST.getlist("bulk_ingredient_name")
            quantities = request.POST.getlist("bulk_quantity")
            units = request.POST.getlist("bulk_unit")
            categories = request.POST.getlist("bulk_category")
            expiry_dates = request.POST.getlist("bulk_expiry_date")
            notes_list = request.POST.getlist("bulk_notes")

            added_count = 0
            error_rows = []

            row_count = max(
                len(ingredient_names),
                len(quantities),
                len(units),
                len(categories),
                len(expiry_dates),
                len(notes_list),
            )

            for index in range(row_count):
                ingredient_name = (
                    ingredient_names[index].strip()
                    if index < len(ingredient_names)
                    else ""
                )

                quantity = (
                    quantities[index].strip()
                    if index < len(quantities)
                    else ""
                )

                unit = (
                    units[index].strip()
                    if index < len(units) and units[index].strip()
                    else "other"
                )

                category = (
                    categories[index].strip()
                    if index < len(categories) and categories[index].strip()
                    else "other"
                )

                expiry_date = (
                    expiry_dates[index].strip()
                    if index < len(expiry_dates)
                    else ""
                )

                notes = (
                    notes_list[index].strip()
                    if index < len(notes_list)
                    else ""
                )

                row_has_data = any(
                    [
                        ingredient_name,
                        quantity,
                        expiry_date,
                        notes,
                    ]
                )

                if not row_has_data:
                    continue

                if not ingredient_name:
                    error_rows.append(index + 1)
                    continue

                item_form = PantryItemForm(
    {
        "ingredient_name": ingredient_name,
        "quantity": quantity or "",
        "unit": unit or "other",
        "category": category or "other",
        "expiry_date": expiry_date or "",
        "notes": notes or "",
        "is_available": "on",
    }
)

                if item_form.is_valid():
                    pantry_item = item_form.save(commit=False)
                    pantry_item.user = request.user
                    pantry_item.save()
                    added_count += 1
                else:
                    error_rows.append(index + 1)

            if added_count:
                messages.success(
                    request,
                    f"{added_count} pantry item{'s' if added_count > 1 else ''} added successfully.",
                )

            if error_rows:
                messages.error(
                    request,
                    "Some bulk rows were not added. Please check row(s): "
                    + ", ".join(str(row) for row in error_rows),
                )

            if not added_count and not error_rows:
                messages.info(
                    request,
                    "No pantry items were added because all bulk rows were empty.",
                )

            return redirect("pantry_list")

        form = PantryItemForm(request.POST)

        if form.is_valid():
            pantry_item = form.save(commit=False)
            pantry_item.user = request.user
            pantry_item.save()

            messages.success(
                request,
                f"{pantry_item.ingredient_name} has been added to your Smart Pantry.",
            )
            return redirect("pantry_list")

        messages.error(
            request,
            "Please correct the errors below and try again.",
        )

    else:
        form = PantryItemForm()

    pantry_items = PantryItem.objects.filter(
        user=request.user,
    ).order_by(
        "expiry_date",
        "ingredient_name",
    )

    available_pantry_items = pantry_items.filter(
        is_available=True,
    )

    expired_items = available_pantry_items.filter(
        expiry_date__lt=today,
    )

    expiring_soon_items = available_pantry_items.filter(
        expiry_date__gte=today,
        expiry_date__lte=soon_date,
    )

    priority_pantry_items = (
        available_pantry_items.filter(
            expiry_date__gte=today,
        )
        .order_by("expiry_date", "ingredient_name")[:5]
    )

    personalised_recommendations = get_personalised_recommendations(
        request.user,
        limit=4,
    )

    context = {
        "form": form,
        "pantry_items": pantry_items,
        "total_items": pantry_items.count(),
        "available_items_count": available_pantry_items.count(),
        "expired_items_count": expired_items.count(),
        "expiring_soon_count": expiring_soon_items.count(),
        "expired_items": expired_items,
        "expiring_soon_items": expiring_soon_items,
        "priority_pantry_items": priority_pantry_items,
        "personalised_recommendations": personalised_recommendations,
    }

    return render(request, "recipes/pantry_list.html", context)













@login_required
def pantry_item_update_view(request, item_id):
    """
    Allows a logged-in user to update only their own pantry item.
    """

    pantry_item = get_object_or_404(
        PantryItem,
        id=item_id,
        user=request.user,
    )

    if request.method == "POST":
        form = PantryItemForm(request.POST, instance=pantry_item)

        if form.is_valid():
            updated_item = form.save()

            messages.success(
                request,
                f"{updated_item.ingredient_name} has been updated successfully.",
            )
            return redirect("pantry_list")

        messages.error(
            request,
            "Please correct the errors below and try again.",
        )

    else:
        form = PantryItemForm(instance=pantry_item)

    context = {
        "form": form,
        "pantry_item": pantry_item,
    }

    return render(request, "recipes/pantry_item_form.html", context)


@login_required
def pantry_item_delete_view(request, item_id):
    """
    Allows a logged-in user to delete only their own pantry item.
    """

    pantry_item = get_object_or_404(
        PantryItem,
        id=item_id,
        user=request.user,
    )

    if request.method == "POST":
        item_name = pantry_item.ingredient_name
        pantry_item.delete()

        messages.success(
            request,
            f"{item_name} has been removed from your Smart Pantry.",
        )
        return redirect("pantry_list")

    context = {
        "pantry_item": pantry_item,
    }

    return render(request, "recipes/pantry_item_confirm_delete.html", context)















