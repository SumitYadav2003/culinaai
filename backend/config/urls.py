from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.db.models import Avg, Count
from django.shortcuts import render
from django.urls import include, path, re_path
from django.views.static import serve

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


def about_culinaai_view(request):
    """
    Professional About CulinaAI page.
    """

    return render(request, "pages/about_culinaai.html")


def sdg_impact_view(request):
    """
    How CulinaAI relates to four UN Sustainable Development Goals (1, 2, 3, 12):
    one swap worked out live by code, the signed-in user's own figures, and the
    sources and limits behind every number.
    """
    from recipes.impact_service import build_impact_context, swap_example

    context = {"example": swap_example()}
    if request.user.is_authenticated:
        context["impact"] = build_impact_context(request.user)["impact"]
    return render(request, "pages/sdg_impact.html", context)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home_view, name="home"),
    path("about/", about_culinaai_view, name="about_culinaai"),
    path("impact/", sdg_impact_view, name="sdg_impact"),
    path("", include("accounts.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("recipes/", include("recipes.urls")),
]


urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]