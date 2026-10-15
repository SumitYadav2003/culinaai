"""
Sharing recipes with other cooks, and rating shared recipes.

(Split out of views.py; recipes/views.py still re-exports everything.)
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone


from .forms import (
    RecipeFeedbackForm,
)
from .demo_service import not_in_demo
from .models import (
    Cuisine,
    MealType,
    Recipe,
    RecipeFeedback,
    RecipeRating,
)





# View: lets a recipe owner share or remove a recipe from the community page.
@login_required
@not_in_demo()
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
            "Stopped sharing. Only you can see this recipe now.",
        )
    else:
        # Important: setting is_public=True shares this recipe with the community.
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
            "Shared. Other cooks can now see, rate and comment on it.",
        )

    return redirect("saved_recipe_detail", recipe_id=recipe.id)


# View: displays public community recipes with search, filters, sorting and featured data.
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
        # Important: only public saved recipes appear in the community list.
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


# View: displays a public recipe detail page and increases its community view count.
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

    # Important: F expression safely increments community views in the database.
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


# View: saves rating and feedback for a public community recipe.
@login_required
@not_in_demo()
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
            "Thanks, your rating is posted.",
        )
    else:
        messages.error(
            request,
            "Choose a rating from 1 to 5.",
        )

    return redirect("community_recipe_detail", recipe_id=recipe.id)
