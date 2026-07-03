from django.urls import path

from .views import (
    community_recipe_detail_view,
    community_recipes_view,
    delete_saved_recipe_confirm_view,
    delete_saved_recipe_view,
    edit_saved_recipe_view,
    favourite_recipes_view,
    generate_recipe_view,
    modify_saved_recipe_view,
    print_saved_recipe_view,
    quality_dashboard_view,
    quality_recipe_evidence_view,
    save_generated_recipe_view,
    save_modified_recipe_view,
    saved_recipe_detail_view,
    saved_recipes_view,
    send_recipe_email_view,
    submit_community_recipe_feedback_view,
    submit_recipe_feedback_view,
    toggle_community_recipe_view,
    toggle_favourite_recipe_view,
)


urlpatterns = [
    path("generate/", generate_recipe_view, name="generate_recipe"),
    path("save-generated/", save_generated_recipe_view, name="save_generated_recipe"),

    # Community recipe sharing.
    path(
        "community/<int:recipe_id>/",
        community_recipe_detail_view,
        name="community_recipe_detail",
    ),
    path(
        "community/<int:recipe_id>/feedback/",
        submit_community_recipe_feedback_view,
        name="submit_community_recipe_feedback",
    ),

    # Staff-only quality dashboard.
    path(
        "quality-dashboard/",
        quality_dashboard_view,
        name="quality_dashboard",
    ),
    path(
        "quality-dashboard/recipe/<int:recipe_id>/",
        quality_recipe_evidence_view,
        name="quality_recipe_evidence",
    ),

    # Saved recipes.
    path("saved/", saved_recipes_view, name="saved_recipes"),

    # Specific saved recipe actions must stay before the general detail route.
    path(
        "saved/<int:recipe_id>/edit/",
        edit_saved_recipe_view,
        name="edit_saved_recipe",
    ),
    path(
        "saved/<int:recipe_id>/print/",
        print_saved_recipe_view,
        name="print_saved_recipe",
    ),
    path(
        "saved/<int:recipe_id>/community/",
        toggle_community_recipe_view,
        name="toggle_community_recipe",
    ),
    path(
        "saved/<int:recipe_id>/",
        saved_recipe_detail_view,
        name="saved_recipe_detail",
    ),

    # Favourites.
    path(
        "favourite/<int:recipe_id>/",
        toggle_favourite_recipe_view,
        name="toggle_favourite_recipe",
    ),
    path("favourites/", favourite_recipes_view, name="favourite_recipes"),

    # Rating, feedback and email.
    path(
        "feedback/<int:recipe_id>/",
        submit_recipe_feedback_view,
        name="submit_recipe_feedback",
    ),
    path(
        "email/<int:recipe_id>/",
        send_recipe_email_view,
        name="send_recipe_email",
    ),

    # AI recipe modification.
    path(
        "modify/<int:recipe_id>/",
        modify_saved_recipe_view,
        name="modify_saved_recipe",
    ),
    path(
        "save-modified/<int:recipe_id>/",
        save_modified_recipe_view,
        name="save_modified_recipe",
    ),

    # Delete saved recipe.
    path(
        "delete/<int:recipe_id>/confirm/",
        delete_saved_recipe_confirm_view,
        name="delete_saved_recipe_confirm",
    ),
    path(
        "delete/<int:recipe_id>/",
        delete_saved_recipe_view,
        name="delete_saved_recipe",
    ),
]