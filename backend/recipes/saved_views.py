"""
Saved recipes: the list, the recipe page, favourites, cooking mode, the cooking
assistant, changing a saved recipe, ratings, email, print, edit and delete.

(Split out of views.py; recipes/views.py still re-exports everything.)
"""

import json
import traceback
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.utils.http import url_has_allowed_host_and_scheme
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .cooking_chat_service import ask_cooking_assistant


from .ai_service import (
    generate_recipe_image_base64,
    modify_ai_recipe,
)
from .recipe_quality_engine import (
    validate_recipe_output,
)
from .forms import (
    RecipeEmailForm,
    RecipeFeedbackForm,
    RecipeModifyForm,
    SavedRecipeEditForm,
)
from .ai_limits import use_ai
from .demo_service import not_in_demo
from .pagination import paginate
from .models import (
    AIUsage,
    Cuisine,
    FavouriteRecipe,
    MealType,
    Recipe,
    RecipeFeedback,
    RecipeRating,
)
from .shopping_service import build_shopping_list_context, extract_ingredient_items
from .cooking_learning_service import (
    ENGLISH_CHOICES,
    get_settings as get_cooking_settings,
    timer_adjustment,
)
from .cooking_mode_service import adjust_step_timers
from .insight_service import add_ai_swaps


from .cooking_mode_service import build_cooking_mode_context

from .cooking_chat_service import build_cooking_chat_context
from .recipe_helpers import (
    build_modified_recipe_validation_preferences,
    build_recipe_insights,
    build_validation_attempt_row,
    extract_recipe_title,
    get_storage_url,
    recipe_email_body,
    save_generated_recipe_image,
    send_recipe_email_safely,
)
from .generate_views import CHANGE_CHOICES


# View: displays saved recipes for the logged-in user with search and filters.
@login_required
def saved_recipes_view(request):
    """
    Displays saved recipes for the logged-in user with search and filter support.
    """

    recipes = (
        # Important: only saved recipes belonging to this user are listed.
        Recipe.objects.filter(
            user=request.user,
            is_saved=True,
        )
        .select_related("cuisine", "meal_type")
        .order_by("-created_at")
    )

    search_query = request.GET.get("q", "").strip()
    cuisine_id = request.GET.get("cuisine", "").strip()
    meal_type_id = request.GET.get("meal_type", "").strip()
    difficulty = request.GET.get("difficulty", "").strip()

    if search_query:
        recipes = recipes.filter(title__icontains=search_query)

    if cuisine_id:
        recipes = recipes.filter(cuisine_id=cuisine_id)

    if meal_type_id:
        recipes = recipes.filter(meal_type_id=meal_type_id)

    if difficulty:
        recipes = recipes.filter(difficulty=difficulty)

    # Which of these recipes are favourites, for the heart on each card.
    favourite_ids = set(
        FavouriteRecipe.objects.filter(user=request.user).values_list("recipe_id", flat=True)
    )

    page_obj, page_query = paginate(request, recipes, 12)

    context = {
        "recipes": page_obj,
        "page_obj": page_obj,
        "page_query": page_query,
        "total_count": page_obj.paginator.count,
        "favourite_ids": favourite_ids,
        "favourite_count": len(favourite_ids),
        "cuisines": Cuisine.objects.all().order_by("name"),
        "meal_types": MealType.objects.all().order_by("name"),
        "difficulty_choices": Recipe.DIFFICULTY_CHOICES,
        "search_query": search_query,
        "selected_cuisine": cuisine_id,
        "selected_meal_type": meal_type_id,
        "selected_difficulty": difficulty,
    }

    return render(request, "recipes/saved_recipes.html", context)


# AJAX view: sends a recipe-specific user question to the AI cooking assistant service.
@login_required
@require_POST
def ask_cooking_assistant_view(request, recipe_id):
    """
    Handles AJAX requests for the AI Cooking Chat Assistant.

    The assistant is:
    - recipe-aware
    - pantry-aware
    - chat-history aware
    - saved to database
    """

    recipe = get_object_or_404(
        Recipe.objects.select_related(
            "cuisine",
            "meal_type",
        ).prefetch_related(
            "diet_preferences",
        ),
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    try:
        data = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        data = request.POST

    question = data.get("question", "").strip()
    quick_prompt_key = data.get("quick_prompt_key", "").strip()

    if question or quick_prompt_key:
        blocked = use_ai(request.user, AIUsage.KIND_QUESTION, "question")
        if blocked:
            # 200 with success false: the chat shows the error text under the box.
            return JsonResponse({"success": False, "reply": "", "error": blocked})

    # Important: cooking assistant service handles AI chat logic.
    result = ask_cooking_assistant(
        user=request.user,
        recipe=recipe,
        question=question,
        quick_prompt_key=quick_prompt_key,
    )

    response_data = {
        "success": result.success,
        "reply": result.reply,
        "session_id": result.session.id,
        "error": result.error,
    }

    if result.user_message:
        response_data["user_message"] = {
            "id": result.user_message.id,
            "sender": result.user_message.sender,
            "message": result.user_message.message,
            "created_at": result.user_message.created_at.strftime("%d %b %Y, %H:%M"),
        }

    if result.assistant_message:
        response_data["assistant_message"] = {
            "id": result.assistant_message.id,
            "sender": result.assistant_message.sender,
            "message": result.assistant_message.message,
            "created_at": result.assistant_message.created_at.strftime("%d %b %Y, %H:%M"),
        }

    return JsonResponse(response_data)


# View: shows one saved recipe with favourites, feedback, email, shopping list and chat context.
@login_required
def saved_recipe_detail_view(request, recipe_id):
    """
    Displays one saved recipe in full detail for the logged-in user.

    Includes:
    - recipe detail
    - favourite status
    - rating and feedback
    - email recipe form
    - AI modify recipe form
    - pantry-aware shopping list
    - AI cooking chat assistant context
    """

    recipe = get_object_or_404(
        Recipe.objects.select_related(
            "cuisine",
            "meal_type",
            "original_recipe",
        ).prefetch_related(
            "diet_preferences",
        ),
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    is_favourite = FavouriteRecipe.objects.filter(
        user=request.user,
        recipe=recipe,
    ).exists()

    user_rating = RecipeRating.objects.filter(
        user=request.user,
        recipe=recipe,
    ).first()

    user_feedback_items = RecipeFeedback.objects.filter(
        user=request.user,
        recipe=recipe,
    ).order_by("-id")[:5]

    feedback_form = RecipeFeedbackForm(
        initial={
            "rating": str(user_rating.rating) if user_rating else "5",
        }
    )

    email_form = RecipeEmailForm()
    modify_form = RecipeModifyForm()

    # Important: shopping service compares recipe ingredients with pantry items.
    shopping_context = build_shopping_list_context(
        recipe=recipe,
        user=request.user,
    )

    # Important: chat context prepares previous messages and quick prompts.
    cooking_chat_context = build_cooking_chat_context(
        user=request.user,
        recipe=recipe,
    )

    modified_recipe_preview = request.session.get("modified_recipe_preview")
    preview_already_displayed = request.session.get(
        "modified_recipe_preview_displayed",
        False,
    )

    if modified_recipe_preview:
        preview_recipe_id = modified_recipe_preview.get("recipe_id")

        if preview_recipe_id != recipe.id:
            modified_recipe_preview = None

        elif preview_already_displayed:
            request.session.pop("modified_recipe_preview", None)
            request.session.pop("modified_recipe_preview_displayed", None)
            modified_recipe_preview = None

        else:
            request.session["modified_recipe_preview_displayed"] = True

    context = {
        "recipe": recipe,
        "is_favourite": is_favourite,
        "feedback_form": feedback_form,
        "email_form": email_form,
        "modify_form": modify_form,
        "change_choices": CHANGE_CHOICES,
        "modified_recipe_preview": modified_recipe_preview,
        "user_rating": user_rating,
        "user_feedback_items": user_feedback_items,
        "original_recipe": recipe.original_recipe,
        "is_modified_version": recipe.is_modified_version,

        # Pantry-aware shopping list.
        "shopping_categories": shopping_context["shopping_categories"],
        "shopping_total_items": shopping_context["shopping_total_items"],
        "shopping_total_categories": shopping_context[
            "shopping_total_categories"
        ],
        "pantry_available_items": shopping_context["pantry_available_items"],
        "pantry_missing_items": shopping_context["pantry_missing_items"],
        "pantry_available_count": shopping_context["pantry_available_count"],
        "pantry_missing_count": shopping_context["pantry_missing_count"],
        "pantry_match_score": shopping_context["pantry_match_score"],
        "pantry_has_matches": shopping_context["pantry_has_matches"],
    }

    context.update(cooking_chat_context)

    return render(
        request,
        "recipes/saved_recipe_detail.html",
        context,
    )


# View: lets the owner edit saved recipe title and personal notes only.
@login_required
def edit_saved_recipe_view(request, recipe_id):
    """
    Allows the logged-in user to edit only the saved recipe title and personal notes.
    """

    recipe = get_object_or_404(
        Recipe,
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    if request.method == "POST":
        form = SavedRecipeEditForm(request.POST, instance=recipe)

        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Saved your changes.",
            )
            return redirect("saved_recipe_detail", recipe_id=recipe.id)

        messages.error(request, "Something needs fixing. Check the form below.")
    else:
        form = SavedRecipeEditForm(instance=recipe)

    return render(
        request,
        "recipes/edit_saved_recipe.html",
        {
            "form": form,
            "recipe": recipe,
        },
    )


# View: displays step-by-step cooking mode for one saved recipe.
@login_required
def cooking_mode_view(request, recipe_id):
    """
    Displays an interactive step-by-step cooking mode for a saved recipe.

    Features:
    - step-by-step recipe guidance
    - progress tracking
    - mark step as completed
    - built-in cooking timer
    """

    recipe = get_object_or_404(
        Recipe.objects.select_related(
            "cuisine",
            "meal_type",
        ).prefetch_related(
            "diet_preferences",
        ),
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    # Important: cooking mode service converts instructions into guided steps.
    context = build_cooking_mode_context(
        recipe=recipe,
    )

    # Learning from how the user cooks, and the hands-free voice (cooking_learning_service.py).
    cooking_settings = get_cooking_settings(request.user)

    # Hands-on step timers adjusted to the cook's pace (waiting and hob steps never change).
    adjustment = timer_adjustment(request.user)
    adjusted_steps = adjust_step_timers(context["cooking_steps"], adjustment["applied"]) if adjustment else 0
    if adjusted_steps:
        context["cooking_steps_json"] = json.dumps(context["cooking_steps"])
    context["timer_adjustment"] = adjustment if adjusted_steps else None

    context.update(
        {
            "learning": cooking_settings.learn_from_cooking,
            "english_choices": ENGLISH_CHOICES,
            "cooking_config": {
                "learning": cooking_settings.learn_from_cooking,
                "english": cooking_settings.english,
                "estimated_minutes": context["estimated_total_minutes"],
                "timers_adjusted": bool(adjusted_steps),
                "ingredients": extract_ingredient_items(recipe.ingredients_text)[:60],
                "record_url": reverse("cooking_record", args=[recipe.id]),
                "settings_url": reverse("cooking_settings"),
            },
        }
    )

    return render(request, "recipes/cooking_mode.html", context)


# View: displays all favourite recipes for the logged-in user with filters.
@login_required
def favourite_recipes_view(request):
    """
    Displays all favourite recipes for the logged-in user.
    """

    search_query = request.GET.get("q", "").strip()
    selected_cuisine = request.GET.get("cuisine", "").strip()
    selected_meal_type = request.GET.get("meal_type", "").strip()
    selected_difficulty = request.GET.get("difficulty", "").strip()

    favourite_recipes = (
        # Important: only this user’s favourite saved recipes are listed.
        FavouriteRecipe.objects.filter(
            user=request.user,
            recipe__is_saved=True,
        )
        .select_related(
            "recipe",
            "recipe__cuisine",
            "recipe__meal_type",
        )
        .prefetch_related(
            "recipe__diet_preferences",
        )
        .order_by("-created_at")
    )

    if search_query:
        favourite_recipes = favourite_recipes.filter(
            Q(recipe__title__icontains=search_query)
            | Q(recipe__description__icontains=search_query)
            | Q(recipe__ingredients_text__icontains=search_query)
            | Q(recipe__instructions_text__icontains=search_query)
            | Q(recipe__cuisine__name__icontains=search_query)
            | Q(recipe__meal_type__name__icontains=search_query)
            | Q(recipe__diet_preferences__name__icontains=search_query)
        )

    if selected_cuisine:
        favourite_recipes = favourite_recipes.filter(
            recipe__cuisine_id=selected_cuisine,
        )

    if selected_meal_type:
        favourite_recipes = favourite_recipes.filter(
            recipe__meal_type_id=selected_meal_type,
        )

    if selected_difficulty:
        favourite_recipes = favourite_recipes.filter(
            recipe__difficulty=selected_difficulty,
        )

    favourite_recipes = favourite_recipes.distinct()
    page_obj, page_query = paginate(request, favourite_recipes, 12)

    cuisines = Cuisine.objects.all().order_by("name")
    meal_types = MealType.objects.all().order_by("name")

    difficulties = [
        ("easy", "Easy"),
        ("medium", "Medium"),
        ("hard", "Hard"),
    ]

    has_active_filters = any(
        [
            search_query,
            selected_cuisine,
            selected_meal_type,
            selected_difficulty,
        ]
    )

    return render(
        request,
        "recipes/favourite_recipes.html",
        {
            "favourite_recipes": page_obj,
            "page_obj": page_obj,
            "page_query": page_query,
            "total_count": page_obj.paginator.count,
            "cuisines": cuisines,
            "meal_types": meal_types,
            "difficulties": difficulties,
            "search_query": search_query,
            "selected_cuisine": selected_cuisine,
            "selected_meal_type": selected_meal_type,
            "selected_difficulty": selected_difficulty,
            "has_active_filters": has_active_filters,
        },
    )


# View: saves or updates rating and feedback for a saved recipe.
@login_required
def submit_recipe_feedback_view(request, recipe_id):
    """
    Saves or updates a user's rating and optional feedback comment for a saved recipe.
    """

    if request.method != "POST":
        return redirect("saved_recipe_detail", recipe_id=recipe_id)

    recipe = get_object_or_404(
        Recipe,
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    form = RecipeFeedbackForm(request.POST)

    if form.is_valid():
        rating_value = int(form.cleaned_data["rating"])
        comment = form.cleaned_data.get("comment", "").strip()

        # Important: one rating per user per recipe is updated or created.
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
            "Thanks, your rating is saved.",
        )
    else:
        messages.error(
            request,
            "Choose a rating from 1 to 5.",
        )

    return redirect("saved_recipe_detail", recipe_id=recipe.id)


# View: sends a saved recipe to an email address provided by the user.
@login_required
@not_in_demo()
def send_recipe_email_view(request, recipe_id):
    """
    Sends a saved recipe to a user-provided email address.
    """

    if request.method != "POST":
        return redirect("saved_recipe_detail", recipe_id=recipe_id)

    recipe = get_object_or_404(
        Recipe,
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    form = RecipeEmailForm(request.POST)

    if form.is_valid():
        send_recipe_email_safely(
            request,
            form.cleaned_data["recipient_email"],
            recipe.title,
            recipe_email_body(
                request.user.username,
                recipe.title,
                recipe.instructions_text or recipe.ingredients_text,
                form.cleaned_data.get("message", "").strip(),
            ),
        )
    else:
        messages.error(request, "Enter a valid email address, for example name@example.com.")

    return redirect("saved_recipe_detail", recipe_id=recipe.id)


# View: toggles a saved recipe in or out of favourites.
@login_required
def toggle_favourite_recipe_view(request, recipe_id):
    """
    Adds or removes a saved recipe from favourites.
    """

    if request.method != "POST":
        return redirect("saved_recipe_detail", recipe_id=recipe_id)

    recipe = get_object_or_404(
        Recipe,
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    # Important: get_or_create toggles favourite status without duplicates.
    favourite, created = FavouriteRecipe.objects.get_or_create(
        user=request.user,
        recipe=recipe,
    )

    if created:
        messages.success(request, f'Added "{recipe.title}" to favourites.')
    else:
        favourite.delete()
        messages.info(request, f'Removed "{recipe.title}" from favourites.')

    # Go back to the page the heart was pressed on (saved list, favourites or the recipe).
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)

    return redirect("saved_recipe_detail", recipe_id=recipe.id)


# View: generates an AI-modified preview of an existing saved recipe.
@login_required
def modify_saved_recipe_view(request, recipe_id):
    """
    Handles AI-powered modification requests for an existing saved recipe.

    This view does not directly save the modified recipe.
    It only creates a preview and stores it temporarily in the session.

    Updated after principal marker feedback:
    - modified recipe text is generated
    - modified recipe image is generated
    - modified recipe output is validated
    - comparison table rows are stored
    - validation evidence is saved in session for later saving
    """

    if request.method != "POST":
        return redirect("saved_recipe_detail", recipe_id=recipe_id)

    # Important: only the logged-in user's own saved recipe can be modified.
    recipe = get_object_or_404(
        Recipe.objects.select_related(
            "cuisine",
            "meal_type",
        ).prefetch_related(
            "diet_preferences",
        ),
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    data = request.POST.copy()
    # Typing your own change without picking one of the quick changes means "custom".
    if data.get("custom_instruction", "").strip() and not data.get("modification_type"):
        data["modification_type"] = "custom"
    form = RecipeModifyForm(data)

    if form.is_valid():
        modification_type = form.cleaned_data["modification_type"]
        custom_instruction = form.cleaned_data.get("custom_instruction", "").strip()

        blocked = use_ai(request.user, AIUsage.KIND_RECIPE, "modify")
        if blocked:
            messages.error(request, blocked)
            return redirect(f"{reverse('saved_recipe_detail', args=[recipe.id])}#culina-modify-recipe")

        try:
            # Important: AI service creates the modified recipe text
            # and comparison table rows.
            ai_result = modify_ai_recipe(
                recipe=recipe,
                modification_type=modification_type,
                custom_instruction=custom_instruction,
            )

            modified_recipe_text = ai_result.get("modified_recipe_text", "").strip()
            comparison_rows = ai_result.get("comparison_rows", [])

            if not modified_recipe_text:
                messages.error(
                    request,
                    "The change didn't work this time. Please try again.",
                )
                return redirect(
                    f"{reverse('saved_recipe_detail', args=[recipe.id])}#culina-modify-recipe"
                )

            # Important: build validation preferences for the modified recipe.
            # Modified recipes do not come from the normal generation form,
            # so we rebuild the required validation context from the original recipe.
            modified_validation_preferences = build_modified_recipe_validation_preferences(
                recipe=recipe,
                modification_type=modification_type,
                custom_instruction=custom_instruction,
            )

            modified_validation_report = {}
            modified_validation_attempt_history = []

            # Saved recipes don't store servings, so let the modified recipe's own
            # SERVINGS line decide (insight_service falls back to it).
            modified_insights = add_ai_swaps(
                build_recipe_insights(
                    modified_recipe_text,
                    dict(modified_validation_preferences, servings=None),
                ),
                modified_validation_preferences,
            )

            try:
                # Important: validate the AI-modified recipe before showing/saving it.
                # This keeps modified recipes consistent with normal generated recipes.
                validation_report = validate_recipe_output(
                    preferences=modified_validation_preferences,
                    recipe_text=modified_recipe_text,
                    attempt_number=1,
                    insights=modified_insights,
                )

                # Important: copy the validation report and add modification-specific evidence.
                modified_validation_report = dict(validation_report or {})
                modified_validation_report.update(
                    {
                        "type": "ai_recipe_modification",
                        "original_recipe_id": recipe.id,
                        "original_recipe_title": recipe.title,
                        "modification_type": modification_type,
                        "custom_instruction": custom_instruction,
                        "comparison_rows": comparison_rows,
                    }
                )

                modified_validation_attempt_history = [
                    build_validation_attempt_row(
                        modified_validation_report,
                        attempt_number=1,
                    )
                ]

            except Exception as validation_error:
                # Validation failure should be visible in terminal, but it should not
                # completely stop the user from seeing the modified recipe preview.
                print(
                    "CULINAAI MODIFIED RECIPE VALIDATION ERROR:",
                    repr(validation_error),
                )
                traceback.print_exc()

                # Important: fallback validation evidence still records that the
                # modified recipe was generated, but validation could not complete.
                modified_validation_report = {
                    "type": "ai_recipe_modification",
                    "original_recipe_id": recipe.id,
                    "original_recipe_title": recipe.title,
                    "modification_type": modification_type,
                    "custom_instruction": custom_instruction,
                    "comparison_rows": comparison_rows,
                    "score": None,
                    "status": "Validation could not complete",
                    "risk_level": "Unknown",
                    "badge": "Validation Pending",
                    "hard_fail": False,
                    "should_regenerate": False,
                    "checks": [],
                    "failed_checks": [],
                    "validation_error": str(validation_error),
                }

                modified_validation_attempt_history = [
                    build_validation_attempt_row(
                        modified_validation_report,
                        attempt_number=1,
                    )
                ]

            # Important: extract title from modified recipe text for image generation.
            modified_recipe_title = extract_recipe_title(modified_recipe_text)

            generated_image_path = ""
            generated_image_url = ""
            generated_image_prompt = ""

            try:
                # Important: generate a new image for the modified recipe.
                # This is needed because the user may change cuisine/style,
                # for example from Indian style to Chinese style.
                modified_image_preferences = {
                    "ingredients": modified_recipe_text,
                    "cuisine": modified_validation_preferences.get(
                        "cuisine",
                        "modified home-style recipe",
                    ),
                    "meal_type": modified_validation_preferences.get(
                        "meal_type",
                        "meal",
                    ),
                    "diet_preferences": modified_validation_preferences.get(
                        "diet_preferences",
                        [],
                    ),
                }

                image_result = generate_recipe_image_base64(
                    recipe_title=modified_recipe_title,
                    preferences=modified_image_preferences,
                )

                generated_image_prompt = image_result.get("image_prompt", "")

                generated_image_path = save_generated_recipe_image(
                    image_result.get("image_base64", ""),
                )

                generated_image_url = get_storage_url(generated_image_path)

            except Exception as image_error:
                # Image failure should not block recipe modification.
                # The user can still review and save the modified recipe text.
                print("CULINAAI MODIFIED RECIPE IMAGE ERROR:", repr(image_error))
                generated_image_path = ""
                generated_image_url = ""
                generated_image_prompt = ""

            # Important: store the modified preview in session.
            # It will be displayed on saved_recipe_detail.html.
            # The validation evidence is also stored here so save_modified_recipe_view
            # can write it into the Recipe table.
            request.session["modified_recipe_preview"] = {
                "recipe_id": recipe.id,
                "modification_type": modification_type,
                "custom_instruction": custom_instruction,
                "prompt": ai_result.get("prompt", ""),
                "raw_modified_response": ai_result.get("raw_modified_response", ""),
                "modified_recipe_text": modified_recipe_text,
                "comparison_rows": comparison_rows,
                "generated_image": generated_image_path,
                "generated_image_url": generated_image_url,
                "generated_image_prompt": generated_image_prompt,
                "validation_report": modified_validation_report,
                "validation_attempt_history": modified_validation_attempt_history,
                "insights": modified_insights,
                "quality_score": modified_validation_report.get("score"),
                "validation_status": modified_validation_report.get("status", ""),
                "validation_risk_level": modified_validation_report.get("risk_level", ""),
                "validation_badge": modified_validation_report.get("badge", ""),
            }

            request.session["modified_recipe_preview_displayed"] = False

            quality_score = modified_validation_report.get("score")

            if quality_score is not None:
                messages.success(
                    request,
                    "Here's your changed recipe. Save it to keep it.",
                )
            else:
                messages.warning(
                    request,
                    "Here's your changed recipe. It couldn't be fully checked, so read it carefully before you cook.",
                )

        except Exception as error:
            print("CULINAAI RECIPE MODIFICATION ERROR:", repr(error))
            traceback.print_exc()

            messages.error(
                request,
                "The recipe couldn't be changed just now. Please try again in a minute.",
            )

        return redirect(
            f"{reverse('saved_recipe_detail', args=[recipe.id])}#culina-modified-preview"
        )

    messages.error(request, "Choose a change, or describe the change you want.")
    return redirect(
        f"{reverse('saved_recipe_detail', args=[recipe.id])}#culina-modify-recipe"
    )


# View: saves the AI-modified preview as a new recipe linked to the original.
@login_required
def save_modified_recipe_view(request, recipe_id):
    """
    Saves the AI-modified recipe preview as a new saved recipe.

    Important:
    The original recipe is not overwritten.
    A new Recipe record is created and linked back to the original recipe.

    Updated:
    The modified recipe now saves its own validation evidence so saved recipe
    cards do not show "Validation Not Stored" for new modified recipes.
    """

    if request.method != "POST":
        return redirect("saved_recipe_detail", recipe_id=recipe_id)

    # Important: only the owner can save a modified version of their recipe.
    original_recipe = get_object_or_404(
        Recipe.objects.select_related(
            "cuisine",
            "meal_type",
        ).prefetch_related(
            "diet_preferences",
        ),
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    modified_preview = request.session.get("modified_recipe_preview")

    if not modified_preview:
        messages.error(request, "There's no changed recipe to save. It may have expired, so make the change again.")
        return redirect("saved_recipe_detail", recipe_id=original_recipe.id)

    if modified_preview.get("recipe_id") != original_recipe.id:
        messages.error(
            request,
            "That changed recipe belongs to a different recipe. Make the change again.",
        )
        return redirect("saved_recipe_detail", recipe_id=original_recipe.id)

    modified_recipe_text = modified_preview.get("modified_recipe_text", "").strip()
    modification_type = modified_preview.get("modification_type", "")
    custom_instruction = modified_preview.get("custom_instruction", "")
    modification_prompt = modified_preview.get("prompt", "")
    modified_image_path = modified_preview.get("generated_image", "")
    comparison_rows = modified_preview.get("comparison_rows", [])

    validation_report = modified_preview.get("validation_report") or {}
    validation_attempt_history = (
        modified_preview.get("validation_attempt_history") or []
    )

    if not modified_recipe_text:
        messages.error(request, "The changed recipe was empty, so it wasn't saved. Please try again.")
        return redirect("saved_recipe_detail", recipe_id=original_recipe.id)

    # Important: use the new modified recipe image if it was generated.
    # If image generation failed, fall back to the original recipe image path.
    if modified_image_path:
        final_recipe_image = modified_image_path
    elif original_recipe.generated_image:
        final_recipe_image = original_recipe.generated_image.name
    else:
        final_recipe_image = None

    # Important: keep comparison data inside the validation report JSON.
    # This allows saved modified recipes to display the comparison table later
    # without needing a new database column.
    if isinstance(validation_report, dict):
        final_validation_report = dict(validation_report)
    else:
        final_validation_report = {}

    final_validation_report.update(
        {
            "type": "ai_recipe_modification",
            "original_recipe_id": original_recipe.id,
            "original_recipe_title": original_recipe.title,
            "modification_type": modification_type,
            "custom_instruction": custom_instruction,
            "comparison_rows": comparison_rows,
        }
    )

    quality_score = final_validation_report.get("score")
    validation_status = final_validation_report.get("status", "")
    validation_risk_level = final_validation_report.get("risk_level", "")
    validation_badge = final_validation_report.get("badge", "")

    # Important: if validation attempt history is missing for any reason,
    # rebuild a compact attempt row from the final validation report.
    if not validation_attempt_history:
        validation_attempt_history = [
            build_validation_attempt_row(
                final_validation_report,
                attempt_number=1,
            )
        ]

    # Important: modified recipe is saved as a new record,
    # not overwriting the original recipe.
    new_recipe = Recipe.objects.create(
        user=request.user,
        title=extract_recipe_title(modified_recipe_text),
        description=f"Modified version of: {original_recipe.title}",
        generated_image=final_recipe_image,
        cuisine=original_recipe.cuisine,
        meal_type=original_recipe.meal_type,
        original_recipe=original_recipe,
        modification_type=modification_type,
        modification_instruction=custom_instruction,
        ingredients_text=original_recipe.ingredients_text,
        instructions_text=modified_recipe_text,
        cooking_time_minutes=original_recipe.cooking_time_minutes,
        difficulty=original_recipe.difficulty,
        allergy_notes=original_recipe.allergy_notes,
        ai_prompt=modification_prompt,
        ai_response=modified_recipe_text,
        is_ai_generated=True,
        is_saved=True,

        # CulinaAI validation fields for modified recipes.
        quality_score=quality_score if quality_score is not None else None,
        validation_status=validation_status,
        validation_risk_level=validation_risk_level,
        validation_badge=validation_badge,
        validation_attempts=len(validation_attempt_history),
        validation_report=final_validation_report,
        validation_attempt_history=validation_attempt_history,
        insights=modified_preview.get("insights") or {},
    )

    # Important: copy the original diet preferences to the modified recipe.
    for diet in original_recipe.diet_preferences.all():
        new_recipe.diet_preferences.add(diet)

    # Important: clear temporary preview data after saving.
    request.session.pop("modified_recipe_preview", None)
    request.session.pop("modified_recipe_preview_displayed", None)

    messages.success(
        request,
        "Saved as a new recipe. Your original is unchanged.",
    )
    return redirect("saved_recipe_detail", recipe_id=new_recipe.id)


# View: shows confirmation before deleting a saved recipe.
@login_required
def delete_saved_recipe_confirm_view(request, recipe_id):
    """
    Shows a confirmation page before deleting a saved recipe.
    """

    recipe = get_object_or_404(
        Recipe,
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    modified_versions_count = recipe.modified_versions.filter(
        user=request.user,
        is_saved=True,
    ).count()

    context = {
        "recipe": recipe,
        "modified_versions_count": modified_versions_count,
    }

    return render(request, "recipes/delete_saved_recipe_confirm.html", context)


# View: permanently deletes a saved recipe from the user’s library.
@login_required
def delete_saved_recipe_view(request, recipe_id):
    """
    Deletes a saved recipe from the logged-in user's recipe library.
    """

    if request.method != "POST":
        return redirect("delete_saved_recipe_confirm", recipe_id=recipe_id)

    recipe = get_object_or_404(
        Recipe,
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    recipe_title = recipe.title
    recipe.delete()

    messages.success(
        request,
        f'Deleted "{recipe_title}".',
    )

    return redirect("saved_recipes")


# View: renders a clean print/export version of a saved recipe.
@login_required
def print_saved_recipe_view(request, recipe_id):
    """
    Displays a clean print/export version of a saved recipe.
    """

    recipe = get_object_or_404(
        Recipe,
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    return render(
        request,
        "recipes/print_recipe.html",
        {
            "recipe": recipe,
        },
    )


# View: removes a recipe from saved recipes without deleting validation evidence/history.
@login_required
def unsave_recipe_view(request, recipe_id):
    """
    Removes a saved recipe from the user's saved recipe library without
    permanently deleting the recipe record.

    This keeps validation evidence and recipe history in the database,
    but hides the recipe from the saved recipes page.
    """

    if request.method != "POST":
        return redirect("saved_recipe_detail", recipe_id=recipe_id)

    recipe = get_object_or_404(
        Recipe,
        id=recipe_id,
        user=request.user,
        is_saved=True,
    )

    recipe_title = recipe.title

    # Remove favourite connection if the recipe was favourited.
    FavouriteRecipe.objects.filter(
        user=request.user,
        recipe=recipe,
    ).delete()

    # If the recipe was shared publicly, make it private again.
    # Important: unsave hides the recipe but keeps database evidence/history.
    recipe.is_saved = False
    recipe.is_public = False
    recipe.public_shared_at = None

    recipe.save(
        update_fields=[
            "is_saved",
            "is_public",
            "public_shared_at",
            "updated_at",
        ]
    )

    messages.success(
        request,
        f'Removed "{recipe_title}" from your saved recipes.',
    )

    return redirect("saved_recipes")
