from django.urls import path

from .views import (
    favourite_recipes_view,
    generate_recipe_view,
    save_generated_recipe_view,
    saved_recipe_detail_view,
    saved_recipes_view,
    send_recipe_email_view,
    submit_recipe_feedback_view,
    toggle_favourite_recipe_view,
    modify_saved_recipe_view,
    save_modified_recipe_view,
)

urlpatterns = [
    path("generate/", generate_recipe_view, name="generate_recipe"),
    path("save-generated/", save_generated_recipe_view, name="save_generated_recipe"),
    path("saved/", saved_recipes_view, name="saved_recipes"),
    path("saved/<int:recipe_id>/", saved_recipe_detail_view, name="saved_recipe_detail"),
    path("favourite/<int:recipe_id>/", toggle_favourite_recipe_view, name="toggle_favourite_recipe"),
    path("favourites/", favourite_recipes_view, name="favourite_recipes"),
    path("feedback/<int:recipe_id>/", submit_recipe_feedback_view, name="submit_recipe_feedback"),
    path("email/<int:recipe_id>/", send_recipe_email_view, name="send_recipe_email"),
    path("modify/<int:recipe_id>/", modify_saved_recipe_view, name="modify_saved_recipe"),
    path("save-modified/<int:recipe_id>/", save_modified_recipe_view, name="save_modified_recipe"),
]