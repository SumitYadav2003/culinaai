from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from recipes.models import FavouriteRecipe, Recipe, RecipeFeedback


@login_required
def dashboard_view(request):
    """
    Displays the logged-in user's CulinaAI dashboard with recipe activity.
    """

    saved_recipes = Recipe.objects.filter(
        user=request.user,
        is_saved=True,
    )

    favourite_recipes = FavouriteRecipe.objects.filter(
        user=request.user,
    )

    feedback_count = RecipeFeedback.objects.filter(
        user=request.user,
    ).count()

    recent_recipes = saved_recipes.order_by("-created_at")[:5]

    context = {
        "saved_recipes_count": saved_recipes.count(),
        "favourite_recipes_count": favourite_recipes.count(),
        "ai_generations_count": saved_recipes.filter(is_ai_generated=True).count(),
        "feedback_count": feedback_count,
        "recent_recipes": recent_recipes,
    }

    return render(request, "dashboard/dashboard.html", context)