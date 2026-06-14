from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .forms import RecipeGenerationForm


@login_required
def generate_recipe_view(request):
    if request.method == "POST":
        form = RecipeGenerationForm(request.POST)

        if form.is_valid():
            # AI generation will be connected in the next stage.
            cleaned_data = form.cleaned_data

            return render(
                request,
                "recipes/generate.html",
                {
                    "form": form,
                    "preview_data": cleaned_data,
                    "generation_preview": True,
                },
            )
    else:
        form = RecipeGenerationForm()

    return render(
        request,
        "recipes/generate.html",
        {
            "form": form,
            "generation_preview": False,
        },
    )