from django.urls import path

from .views import generate_recipe_view


urlpatterns = [
    path("generate/", generate_recipe_view, name="generate_recipe"),
]