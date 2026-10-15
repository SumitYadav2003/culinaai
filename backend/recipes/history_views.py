"""
History: every recipe that was made, saved or not.

(Split out of views.py; recipes/views.py still re-exports everything.)
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render


from .pagination import paginate
from .models import (
    Cuisine,
    DietPreference,
    MealType,
    Recipe,
    RecipeHistory,
)





# View: shows generated recipe history for the logged-in user with search and filters.
@login_required
def recipe_history_view(request):
    """
    Displays all automatically generated recipe history items for the logged-in user.
    """

    history_items = (
        # Important: only the logged-in user’s history is shown.
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

    page_obj, page_query = paginate(request, history_items, 20)

    context = {
        "history_items": page_obj,
        "page_obj": page_obj,
        "page_query": page_query,
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


# View: shows one generated recipe history item in full detail.
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


# View: saves a generated history item into the user’s saved recipe library.
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
            "This recipe is already in your saved recipes.",
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

    # Important: converts a RecipeHistory item into a saved Recipe record.
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
        insights=history_item.insights,
    )

    for diet_name in history_item.dietary_preferences:
        diet = DietPreference.objects.filter(name=diet_name).first()

        if diet:
            recipe.diet_preferences.add(diet)

    history_item.saved_recipe = recipe
    history_item.save(update_fields=["saved_recipe"])

    messages.success(
        request,
        "Saved. You'll find it in Saved recipes.",
    )

    return redirect("saved_recipe_detail", recipe_id=recipe.id)


# View: deletes a history item while keeping any separately saved recipe intact.
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
        f'Deleted "{history_title}" from your history.',
    )

    return redirect("recipe_history")
