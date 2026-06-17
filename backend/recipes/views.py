from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from .ai_service import generate_ai_recipe
from .forms import RecipeGenerationForm
from .models import Cuisine, DietPreference, MealType, Recipe


def extract_recipe_title(recipe_text):
    """
    Extracts a clean recipe title from the AI-generated recipe text.
    Falls back to a default title if no clear title is found.
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
                "cuisine": cleaned_data.get("cuisine").name if cleaned_data.get("cuisine") else "Any cuisine",
                "meal_type": cleaned_data.get("meal_type").name if cleaned_data.get("meal_type") else "Any meal type",
                "diet_preferences": [
                    diet.name for diet in cleaned_data.get("diet_preferences", [])
                ],
                "allergies": cleaned_data.get("allergies") or "None provided",
                "cooking_time_minutes": cleaned_data.get("cooking_time_minutes"),
                "servings": cleaned_data.get("servings"),
                "difficulty": cleaned_data.get("difficulty"),
                "spice_level": spice_choices.get(cleaned_data.get("spice_level"), "Medium"),
                "budget_level": budget_choices.get(cleaned_data.get("budget_level"), "Moderate Budget"),
                "nutrition_goal": nutrition_choices.get(cleaned_data.get("nutrition_goal"), "Balanced"),
                "cooking_equipment": selected_equipment,
                "additional_notes": cleaned_data.get("additional_notes") or "None provided",
            }

            request.session["recipe_preview_data"] = preview_data
            request.session["latest_recipe_preferences"] = preview_data

            try:
                ai_result = generate_ai_recipe(preview_data)

                request.session["ai_recipe_result"] = ai_result
                request.session["latest_ai_recipe_text"] = ai_result.get("recipe_text", "")
                request.session["latest_ai_recipe_prompt"] = ai_result.get("prompt", "")

            except Exception:
                messages.error(
                    request,
                    "Recipe preview is ready, but AI generation failed. Please check your OpenAI API key or billing credits.",
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
    """

    if request.method != "POST":
        return redirect("generate_recipe")

    recipe_text = request.session.get("latest_ai_recipe_text")
    recipe_prompt = request.session.get("latest_ai_recipe_prompt")
    preferences = request.session.get("latest_recipe_preferences")

    if not recipe_text or not preferences:
        messages.error(request, "No generated recipe found to save. Please generate a recipe first.")
        return redirect("generate_recipe")

    cuisine = None
    meal_type = None

    cuisine_name = preferences.get("cuisine")
    meal_type_name = preferences.get("meal_type")

    if cuisine_name and cuisine_name != "Any cuisine":
        cuisine = Cuisine.objects.filter(name=cuisine_name).first()

    if meal_type_name and meal_type_name != "Any meal type":
        meal_type = MealType.objects.filter(name=meal_type_name).first()

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
    )

    diet_names = preferences.get("diet_preferences", [])

    for diet_name in diet_names:
        diet = DietPreference.objects.filter(name=diet_name).first()
        if diet:
            recipe.diet_preferences.add(diet)

    messages.success(request, "Recipe saved successfully.")
    return redirect("saved_recipes")



@login_required
def saved_recipes_view(request):
    """
    Displays all recipes saved by the logged-in user.
    """

    recipes = Recipe.objects.filter(
        user=request.user,
        is_saved=True,
    ).order_by("-created_at")

    return render(
        request,
        "recipes/saved_recipes.html",
        {
            "recipes": recipes,
        },
    )