from django.contrib import admin
from django.db.models import Avg, Count
from django.shortcuts import render
from django.urls import include, path

from recipes.models import Recipe


def home_view(request):
    """
    Landing page view.

    This fetches public/community recipes from the database so they can be
    displayed in the automatic recipe slider on the homepage.
    """

    public_recipes = (
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
            feedback_total=Count("feedback", distinct=True),
        )
        .order_by(
            "-public_shared_at",
            "-created_at",
        )[:8]
    )

    return render(
        request,
        "pages/home.html",
        {
            "public_recipes": public_recipes,
        },
    )


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home_view, name="home"),
    path("", include("accounts.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("recipes/", include("recipes.urls")),
]