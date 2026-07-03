import json
from collections import Counter
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db.models import Avg, Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone



from .ai_service import generate_ai_recipe, modify_ai_recipe
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
)
from .models import (
    Cuisine,
    DietPreference,
    FavouriteRecipe,
    MealType,
    Recipe,
    RecipeFeedback,
    RecipeRating,
)
from .shopping_service import build_shopping_list_context


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


@login_required
def generate_recipe_view(request):
    """
    Handles the AI recipe generation page.

    New CulinaAI flow:
    1. Generate recipe using AI.
    2. Validate recipe using custom constraint-based validation engine.
    3. If validation fails, regenerate with correction instructions.
    4. If AI still fails safety validation, create a deterministic safe fallback recipe.
    5. Show a generated recipe instead of simply blocking the user.
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

            preview_data = {
                "ingredients": cleaned_data.get("ingredients"),
                "cuisine": cleaned_data.get("cuisine").name
                if cleaned_data.get("cuisine")
                else "Any cuisine",
                "meal_type": cleaned_data.get("meal_type").name
                if cleaned_data.get("meal_type")
                else "Any meal type",
                "diet_preferences": [
                    diet.name for diet in cleaned_data.get("diet_preferences", [])
                ],
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
                "additional_notes": cleaned_data.get("additional_notes")
                or "None provided",
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
                final_ai_result[
                    "validation_attempt_history"
                ] = validation_attempt_history
                final_ai_result["quality_score"] = final_validation_report.get(
                    "score",
                )
                final_ai_result["validation_status"] = final_validation_report.get(
                    "status",
                )

                request.session["ai_recipe_result"] = final_ai_result
                request.session["latest_ai_recipe_text"] = final_ai_result.get(
                    "recipe_text",
                    "",
                )
                request.session["latest_ai_recipe_prompt"] = final_ai_result.get(
                    "prompt",
                    "",
                )
                request.session["latest_validation_report"] = final_validation_report
                request.session[
                    "latest_validation_attempt_history"
                ] = validation_attempt_history

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
                        "Recipe generated and validated successfully.",
                    )

            except Exception:
                messages.error(
                    request,
                    "Recipe preview is ready, but AI generation or validation failed. Please check your OpenAI API key, billing credits, or connection.",
                )

            return redirect(f"{reverse('generate_recipe')}#recipe-preview")

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

    diet_names = preferences.get("diet_preferences", [])

    for diet_name in diet_names:
        diet = DietPreference.objects.filter(name=diet_name).first()

        if diet:
            recipe.diet_preferences.add(diet)

    request.session.pop("latest_ai_recipe_text", None)
    request.session.pop("latest_ai_recipe_prompt", None)
    request.session.pop("latest_recipe_preferences", None)
    request.session.pop("latest_validation_report", None)
    request.session.pop("latest_validation_attempt_history", None)

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
def saved_recipe_detail_view(request, recipe_id):
    """
    Displays one saved recipe in full detail for the logged-in user.
    """

    recipe = get_object_or_404(
        Recipe,
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

    shopping_context = build_shopping_list_context(recipe)

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

    return render(
        request,
        "recipes/saved_recipe_detail.html",
        {
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
            "shopping_categories": shopping_context["shopping_categories"],
            "shopping_total_items": shopping_context["shopping_total_items"],
            "shopping_total_categories": shopping_context[
                "shopping_total_categories"
            ],
        },
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



















