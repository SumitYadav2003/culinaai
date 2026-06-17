from django.urls import path

from .views import (
    generate_recipe_view,
    save_generated_recipe_view,
    saved_recipes_view,
)


urlpatterns = [
    path("generate/", generate_recipe_view, name="generate_recipe"),
    path("save-generated/", save_generated_recipe_view, name="save_generated_recipe"),
    path("saved/", saved_recipes_view, name="saved_recipes"),
]