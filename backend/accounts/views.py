from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from recipes.models import FavouriteRecipe, Recipe, RecipeFeedback, RecipeRating

from .forms import LoginForm, SignUpForm


def signup_view(request):
    """
    Create a new user account.

    After successful signup, the user is redirected to the login page.
    The user is not automatically logged in after registration.
    """

    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = SignUpForm(request.POST)

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Your CulinaAI account has been created successfully. Please log in to continue.",
            )
            return redirect("login")

        messages.error(request, "Please correct the errors below.")
    else:
        form = SignUpForm()

    return render(request, "accounts/signup.html", {"form": form})


def login_view(request):
    """
    Log in an existing user.

    Normal login redirects to dashboard.
    If the user was redirected from a protected page, they are safely sent back there.
    """

    if request.user.is_authenticated:
        return redirect("dashboard")

    next_url = request.GET.get("next") or request.POST.get("next")

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)

        if form.is_valid():
            user = form.get_user()
            login(request, user)

            if next_url and url_has_allowed_host_and_scheme(
                url=next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)

            return redirect("dashboard")

        messages.error(request, "Invalid username or password.")
    else:
        form = LoginForm()

    return render(
        request,
        "accounts/login.html",
        {
            "form": form,
            "next": next_url,
        },
    )


def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect("home")


@login_required
def profile_summary_view(request):
    """
    Display a professional account summary page for the logged-in user.

    This page is different from the dashboard:
    - Dashboard = recipe workflow and quick actions.
    - Profile summary = account identity, personal statistics and account actions.
    """

    saved_recipes = Recipe.objects.filter(user=request.user)
    favourite_recipes = FavouriteRecipe.objects.filter(user=request.user)
    ratings = RecipeRating.objects.filter(user=request.user)
    feedback_entries = RecipeFeedback.objects.filter(user=request.user)

    total_saved_recipes = saved_recipes.count()
    total_favourite_recipes = favourite_recipes.count()
    total_ratings = ratings.count()
    total_feedback = feedback_entries.count()

    original_recipe_count = saved_recipes.filter(original_recipe__isnull=True).count()
    modified_recipe_count = saved_recipes.filter(original_recipe__isnull=False).count()

    recent_recipes = saved_recipes.order_by("-created_at")[:4]

    context = {
        "total_saved_recipes": total_saved_recipes,
        "total_favourite_recipes": total_favourite_recipes,
        "total_ratings": total_ratings,
        "total_feedback": total_feedback,
        "original_recipe_count": original_recipe_count,
        "modified_recipe_count": modified_recipe_count,
        "recent_recipes": recent_recipes,
    }

    return render(request, "accounts/profile_summary.html", context)