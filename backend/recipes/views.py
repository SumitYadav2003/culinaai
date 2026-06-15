from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import RecipeGenerationForm


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

            request.session["recipe_preview_data"] = {
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

            return redirect(f"{reverse('generate_recipe')}#recipe-preview")

    else:
        form = RecipeGenerationForm()

    preview_data = request.session.pop("recipe_preview_data", None)

    return render(
        request,
        "recipes/generate.html",
        {
            "form": form,
            "preview_data": preview_data,
            "generation_preview": preview_data is not None,
        },
    )