from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count
from django.shortcuts import render

from recipes.analytics_service import build_user_analytics_context
from recipes.models import FavouriteRecipe, Recipe, RecipeFeedback, RecipeRating


@login_required
def dashboard_view(request):
    """
    Displays the logged-in user's CulinaAI dashboard.

    The dashboard is designed as a professional user analytics hub.

    It now includes:
    - saved recipes count
    - favourite recipes count
    - total AI recipe generations
    - AI-modified recipes
    - feedback and ratings
    - taste profile
    - favourite cuisine
    - average cooking time
    - favourite ingredients
    - recent searches
    - weekly/monthly activity data
    - chart-ready analytics data
    """

    saved_recipes = Recipe.objects.filter(
        user=request.user,
        is_saved=True,
    )

    favourite_recipes = FavouriteRecipe.objects.filter(
        user=request.user,
    )

    modified_recipes = saved_recipes.filter(
        original_recipe__isnull=False,
    )

    feedback_items = RecipeFeedback.objects.filter(
        user=request.user,
    )

    average_rating_data = RecipeRating.objects.filter(
        user=request.user,
    ).aggregate(
        average_rating=Avg("rating"),
    )

    average_rating = average_rating_data.get("average_rating") or 0

    recent_recipes = saved_recipes.select_related(
        "cuisine",
        "meal_type",
        "original_recipe",
    ).order_by("-created_at")[:5]

    saved_count = saved_recipes.count()
    favourite_count = favourite_recipes.count()
    modified_count = modified_recipes.count()
    feedback_count = feedback_items.count()

    # Build full analytics context from recipe history, saved recipes,
    # favourites, cuisines, ingredients and cooking time.
    analytics_context = build_user_analytics_context(
        user=request.user,
    )

    # Prefer automatic recipe history for generation count.
    # Fallback to saved AI recipes if history has less data.
    history_generation_count = analytics_context.get(
        "total_recipes_generated",
        0,
    )

    saved_ai_generation_count = saved_recipes.filter(
        is_ai_generated=True,
    ).count()

    ai_generation_count = max(
        history_generation_count,
        saved_ai_generation_count,
    )

    # Find the cuisine the user has saved most often.
    # This gives the dashboard a personal "taste profile" feeling.
    top_cuisine = (
        saved_recipes.exclude(cuisine__isnull=True)
        .values("cuisine__name")
        .annotate(total=Count("id"))
        .order_by("-total", "cuisine__name")
        .first()
    )

    # Find the meal type the user uses most often.
    # Example: Lunch, Dinner, Snack, Breakfast.
    top_meal_type = (
        saved_recipes.exclude(meal_type__isnull=True)
        .values("meal_type__name")
        .annotate(total=Count("id"))
        .order_by("-total", "meal_type__name")
        .first()
    )

    # Count unique cuisines to show recipe variety.
    cuisine_variety_count = (
        saved_recipes.exclude(cuisine__isnull=True)
        .values("cuisine")
        .distinct()
        .count()
    )

    recipe_variety_score = min(cuisine_variety_count * 20, 100)

    latest_feedback = feedback_items.select_related(
        "recipe",
    ).order_by("-created_at").first()

    latest_modified_recipe = modified_recipes.select_related(
        "original_recipe",
        "cuisine",
        "meal_type",
    ).order_by("-created_at").first()

    if saved_count == 0:
        smart_tip_title = "Build your recipe library"
        smart_tip_text = (
            "Generate and save your first AI recipe to unlock personalised "
            "dashboard insights."
        )
        smart_tip_icon = "bi-magic"

    elif modified_count == 0:
        smart_tip_title = "Try your first AI refinement"
        smart_tip_text = (
            "Modify a saved recipe to make it healthier, quicker, cheaper, "
            "vegetarian or custom."
        )
        smart_tip_icon = "bi-arrow-repeat"

    elif feedback_count == 0:
        smart_tip_title = "Add evaluation feedback"
        smart_tip_text = (
            "Rate and review recipes to build stronger evidence for recipe "
            "quality evaluation."
        )
        smart_tip_icon = "bi-chat-square-heart"

    else:
        smart_tip_title = "Your CulinaAI profile is active"
        smart_tip_text = (
            "You are using saved recipes, AI refinements, favourites and "
            "feedback together."
        )
        smart_tip_icon = "bi-graph-up-arrow"

    context = {
        "saved_recipes_count": saved_count,
        "favourite_recipes_count": favourite_count,
        "ai_generations_count": ai_generation_count,
        "feedback_count": feedback_count,
        "modified_recipes_count": modified_count,
        "average_rating": round(average_rating, 1),
        "recent_recipes": recent_recipes,

        # Personalised taste intelligence.
        "top_cuisine_name": (
            top_cuisine["cuisine__name"]
            if top_cuisine
            else "Not enough data"
        ),
        "top_cuisine_total": (
            top_cuisine["total"]
            if top_cuisine
            else 0
        ),
        "top_meal_type_name": (
            top_meal_type["meal_type__name"]
            if top_meal_type
            else "Not enough data"
        ),
        "top_meal_type_total": (
            top_meal_type["total"]
            if top_meal_type
            else 0
        ),
        "cuisine_variety_count": cuisine_variety_count,
        "recipe_variety_score": recipe_variety_score,

        # Activity insights.
        "latest_feedback": latest_feedback,
        "latest_modified_recipe": latest_modified_recipe,

        # Smart suggestion.
        "smart_tip_title": smart_tip_title,
        "smart_tip_text": smart_tip_text,
        "smart_tip_icon": smart_tip_icon,
    }

    # Add advanced analytics data into the same dashboard context.
    context.update(analytics_context)

    return render(request, "dashboard/dashboard.html", context)