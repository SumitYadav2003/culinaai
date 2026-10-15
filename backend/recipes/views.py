"""
The recipe pages used to live in this one file (4,400 lines). They are now split by
part of the site, and this file re-exports them so `from .views import ...` keeps working:

- generate_views.py   making a recipe, versions, quick changes, saving
- saved_views.py      saved recipes, the recipe page, favourites, cooking mode, changing a saved recipe
- history_views.py    every recipe that was made
- community_views.py  sharing and rating recipes
- pantry_views.py     the pantry
- quality_views.py    the staff quality dashboard
- recipe_helpers.py   helpers the pages share

The meal plan, fridge scanner and cooking-learning pages were already in their own files
(meal_plan_views.py, fridge_scanner_views.py, cooking_learning_views.py).

New code should import from the file that defines a view, not from here.
"""

# ruff: noqa: F401

from .recipe_helpers import (
    build_modified_recipe_validation_preferences,
    build_recipe_insights,
    build_validation_attempt_row,
    create_recipe_history_entry,
    extract_recipe_title,
    failed_check_details,
    get_storage_url,
    recipe_email_body,
    save_generated_recipe_image,
    send_recipe_email_safely,
)
from .generate_views import (
    CHANGE_CHOICES,
    RECIPE_CHANGES,
    SPICE_ORDER,
    UTENSIL_CHOICES,
    build_change_preferences,
    build_version_preferences,
    change_generated_recipe_view,
    email_generated_recipe_view,
    generate_recipe_version_view,
    generate_recipe_view,
    run_recipe_generation,
    save_generated_recipe_view,
)
from .history_views import (
    delete_recipe_history_view,
    recipe_history_detail_view,
    recipe_history_view,
    save_history_recipe_view,
)
from .saved_views import (
    ask_cooking_assistant_view,
    cooking_mode_view,
    delete_saved_recipe_confirm_view,
    delete_saved_recipe_view,
    edit_saved_recipe_view,
    favourite_recipes_view,
    modify_saved_recipe_view,
    print_saved_recipe_view,
    save_modified_recipe_view,
    saved_recipe_detail_view,
    saved_recipes_view,
    send_recipe_email_view,
    submit_recipe_feedback_view,
    toggle_favourite_recipe_view,
    unsave_recipe_view,
)
from .community_views import (
    community_recipe_detail_view,
    community_recipes_view,
    submit_community_recipe_feedback_view,
    toggle_community_recipe_view,
)
from .quality_views import (
    quality_dashboard_view,
    quality_recipe_evidence_view,
)
from .pantry_views import (
    pantry_item_delete_view,
    pantry_item_update_view,
    pantry_list_view,
)
