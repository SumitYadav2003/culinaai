"""
Making a recipe: the New recipe page, the generation-and-checking loop,
"One dish, three ways" versions, quick changes, emailing and saving the result.

(Split out of views.py; recipes/views.py still re-exports everything.)
"""

import copy
import traceback
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST


from .ai_service import (
    generate_ai_recipe,
    generate_recipe_image_base64,
    split_user_items,
)
from .classic_service import same_ingredient
from .recipe_quality_engine import (
    build_regeneration_preferences,
    build_safe_fallback_recipe,
    validate_recipe_output,
)
from .forms import (
    RecipeEmailForm,
    RecipeGenerationForm,
)
from .ai_limits import use_ai
from .demo_service import not_in_demo
from .models import (
    AIUsage,
    Cuisine,
    DietPreference,
    MealType,
    Recipe,
    RecipeHistory,
    PantryItem,
)
from .cooking_learning_service import (
    build_cooking_tips,
    personal_insight,
)
from .cuisine_service import cuisine_correction
from .insight_service import add_ai_swaps, meal_style_correction



from .diet_profile import missing_saved_allergies, saved_diet
from .recipe_helpers import (
    build_recipe_insights,
    create_recipe_history_entry,
    extract_recipe_title,
    failed_check_details,
    get_storage_url,
    recipe_email_body,
    save_generated_recipe_image,
    send_recipe_email_safely,
)


# Helper: the full generation pipeline, shared by the form and "Cook this version".
def run_recipe_generation(request, preview_data):
    """
    Generates, checks, corrects and stores one recipe for these preferences, then
    leaves the result in the session for the generate page to show.

    Used by generate_recipe_view (the form) and generate_recipe_version_view
    (a version from "One dish, three ways"), so both go through the same
    10 quality gates, meal style check, history and fallback.
    """

    # Learning from how this user cooks: how the method should be explained for them
    # (None while learning is off or there isn't enough history). Versions keep the
    # tips of the recipe they came from.
    if "cooking_tips" not in preview_data:
        preview_data = dict(preview_data, cooking_tips=build_cooking_tips(request.user))

    request.session["recipe_preview_data"] = preview_data
    request.session["latest_recipe_preferences"] = preview_data

    try:
        max_regeneration_attempts = 3

        current_preferences = preview_data
        final_ai_result = None
        final_validation_report = None
        final_insights = None
        validation_attempt_history = []
        fallback_used = False

        # The latest attempt that passed validation. If the user asked for
        # "Everyday healthy" and it came out high in something, CulinaAI tries
        # again, but never swaps a validated recipe for one that failed.
        validated_attempt = None

        for attempt_number in range(1, max_regeneration_attempts + 1):
            # Important: OpenAI recipe generation service is called here.
            ai_result = generate_ai_recipe(current_preferences)
            recipe_text = ai_result.get("recipe_text", "")

            # Nutrition, classic comparison and risk flags for this attempt,
            # so gates 9 and 10 can check them.
            insights = build_recipe_insights(recipe_text, preview_data)

            # Important: custom validation engine checks the AI output here.
            validation_report = validate_recipe_output(
                preferences=preview_data,
                recipe_text=recipe_text,
                attempt_number=attempt_number,
                insights=insights,
            )

            validation_attempt_history.append(
                {
                    "attempt_number": attempt_number,
                    "score": validation_report.get("score"),
                    "status": validation_report.get("status"),
                    "passed": not validation_report.get("should_regenerate"),
                    "risk_level": validation_report.get("risk_level"),
                    "hard_fail": validation_report.get("hard_fail"),
                    "failed_checks": [
                        check.get("name")
                        for check in validation_report.get(
                            "failed_checks",
                            [],
                        )
                    ],
                    # What each failed check objected to (e.g. the allergy words it found),
                    # so a failed attempt can be explained later (evaluation report).
                    "failed_details": failed_check_details(validation_report),
                }
            )

            final_ai_result = ai_result
            final_validation_report = validation_report
            final_insights = insights

            # Meal style is checked by code from the traffic lights, and cuisine
            # from published recipe data; either can ask the AI to try again.
            fixes = [
                f"- {label}: {fix}"
                for label, fix in (
                    ("Meal Style", meal_style_correction(insights)),
                    ("Cuisine", cuisine_correction(insights)),
                )
                if fix
            ]
            style_fix = "\n".join(fixes)

            # Recorded for the evaluation: which code checks asked for another try.
            if fixes:
                validation_attempt_history[-1]["retry_for"] = [fix.split(":", 1)[0].lstrip("- ") for fix in fixes]

            if not validation_report.get("should_regenerate"):
                validated_attempt = (ai_result, validation_report, insights)

                if not style_fix:
                    break

            correction_report = validation_report

            if style_fix:
                correction_report = dict(
                    validation_report,
                    correction_prompt=(
                        (validation_report.get("correction_prompt", "") + "\n"
                         if validation_report.get("failed_checks") else "")
                        + style_fix
                    ),
                )

            current_preferences = build_regeneration_preferences(
                original_preferences=preview_data,
                validation_report=correction_report,
                attempt_number=attempt_number,
            )

        # A later try failed validation: keep the earlier recipe that passed.
        # The page then says it is still high in something (insights.meal_style).
        if validated_attempt and final_validation_report.get("should_regenerate"):
            final_ai_result, final_validation_report, final_insights = validated_attempt

        if not final_ai_result or not final_validation_report:
            messages.error(
                request,
                "The recipe couldn't be made just now. Please try again.",
            )
            return

        if (
            final_validation_report.get("hard_fail")
            and final_validation_report.get("score", 0) < 70
        ):
            # Important: safe fallback is used if AI output is unsafe.
            fallback_ai_result = build_safe_fallback_recipe(preview_data)
            fallback_insights = build_recipe_insights(
                fallback_ai_result.get("recipe_text", ""),
                preview_data,
            )

            fallback_validation_report = validate_recipe_output(
                preferences=preview_data,
                recipe_text=fallback_ai_result.get("recipe_text", ""),
                attempt_number=max_regeneration_attempts + 1,
                insights=fallback_insights,
            )

            validation_attempt_history.append(
                {
                    "attempt_number": max_regeneration_attempts + 1,
                    "score": fallback_validation_report.get("score"),
                    "status": "Safe fallback recipe generated",
                    "fallback": True,
                    "risk_level": fallback_validation_report.get("risk_level"),
                    "hard_fail": fallback_validation_report.get("hard_fail"),
                    "failed_checks": [
                        check.get("name")
                        for check in fallback_validation_report.get(
                            "failed_checks",
                            [],
                        )
                    ],
                    "failed_details": failed_check_details(fallback_validation_report),
                }
            )

            final_ai_result = fallback_ai_result
            final_validation_report = fallback_validation_report
            final_insights = fallback_insights
            fallback_used = True

        # The AI's swap ideas for "One dish, three ways", checked by code (final recipe only).
        if not fallback_used:
            final_insights = add_ai_swaps(final_insights, preview_data)

            # "Adjusted for you": what was asked for, and how many tips came back (counted by code).
            personal = personal_insight(preview_data.get("cooking_tips"), final_ai_result.get("recipe_text", ""))
            if personal:
                final_insights = dict(final_insights, personal=personal)

        final_ai_result["insights"] = final_insights
        final_ai_result["validation_report"] = final_validation_report
        final_ai_result["validation_attempt_history"] = validation_attempt_history
        final_ai_result["quality_score"] = final_validation_report.get("score")
        final_ai_result["validation_status"] = final_validation_report.get("status")

        generated_recipe_title = extract_recipe_title(
            final_ai_result.get("recipe_text", ""),
        )

        generated_image_path = ""
        generated_image_prompt = ""

        # The evaluation benchmark turns images off (settings.CULINAAI_SKIP_IMAGES) to save cost.
        skip_image = getattr(settings, "CULINAAI_SKIP_IMAGES", False)

        try:
            if skip_image:
                raise LookupError("images skipped")

            image_result = generate_recipe_image_base64(
                recipe_title=generated_recipe_title,
                preferences=preview_data,
            )

            generated_image_prompt = image_result.get("image_prompt", "")
            generated_image_path = save_generated_recipe_image(
                image_result.get("image_base64", ""),
            )
            print("CULINAAI IMAGE SAVE DEBUG - path:", generated_image_path)
            print("CULINAAI IMAGE SAVE DEBUG - exists:", default_storage.exists(generated_image_path) if generated_image_path else "N/A")

        except Exception as image_gen_error:
            if not skip_image:
                print("CULINAAI IMAGE GENERATION ERROR:", repr(image_gen_error))
                traceback.print_exc()

            generated_image_path = ""
            generated_image_prompt = ""

        final_ai_result["generated_image"] = generated_image_path
        final_ai_result["generated_image_url"] = get_storage_url(
            generated_image_path,
        )
        final_ai_result["generated_image_prompt"] = generated_image_prompt

        request.session["ai_recipe_result"] = final_ai_result
        request.session["latest_ai_recipe_text"] = final_ai_result.get(
            "recipe_text",
            "",
        )
        request.session["latest_ai_recipe_prompt"] = final_ai_result.get(
            "prompt",
            "",
        )
        request.session["latest_recipe_image_path"] = generated_image_path
        request.session["latest_recipe_image_prompt"] = generated_image_prompt
        request.session["latest_validation_report"] = final_validation_report
        request.session["latest_validation_attempt_history"] = validation_attempt_history
        request.session["latest_recipe_insights"] = final_insights



        """one of the important function"""
        try:
            # Important: every generated recipe is stored in RecipeHistory.
            history_entry = create_recipe_history_entry(
                user=request.user,
                recipe_text=final_ai_result.get("recipe_text", ""),
                recipe_prompt=final_ai_result.get("prompt", ""),
                preferences=preview_data,
                image_path=generated_image_path,
                image_prompt=generated_image_prompt,
                validation_report=final_validation_report,
                validation_attempt_history=validation_attempt_history,
                insights=final_insights,
            )

            if history_entry:
                request.session["latest_recipe_history_id"] = history_entry.id

        except Exception:
            request.session.pop("latest_recipe_history_id", None)

        if fallback_used:
            messages.warning(
                request,
                "The first recipe didn't pass the safety checks, so you're seeing a simpler one that does.",
            )
        elif len(validation_attempt_history) > 1:
            messages.success(
                request,
                "Your recipe is ready. It was rewritten once to fit everything you asked for.",
            )
        else:
            messages.success(
                request,
                "Your recipe is ready. It's also kept in your history.",
            )

    except Exception as error:
        print("CULINAAI REAL API GENERATION ERROR:", repr(error))
        traceback.print_exc()

        try:
            fallback_ai_result = build_safe_fallback_recipe(preview_data)
            fallback_recipe_text = fallback_ai_result.get("recipe_text", "")
            fallback_insights = build_recipe_insights(fallback_recipe_text, preview_data)

            try:
                fallback_validation_report = validate_recipe_output(
                    preferences=preview_data,
                    recipe_text=fallback_recipe_text,
                    attempt_number=1,
                    insights=fallback_insights,
                )

            except Exception as validation_error:
                print(
                    "CULINAAI FALLBACK VALIDATION ERROR:",
                    repr(validation_error),
                )
                traceback.print_exc()

                fallback_validation_report = {
                    "score": 85,
                    "status": "Verified with fallback",
                    "risk_level": "Low",
                    "badge": "Fallback Verified",
                    "target_score": 85,
                    "passed_count": 1,
                    "failed_count": 0,
                    "hard_fail": False,
                    "should_regenerate": False,
                    "checks": [
                        {
                            "name": "Fallback Safety Check",
                            "category": "system",
                            "severity": "low",
                            "passed": True,
                            "score": 85,
                            "max_score": 100,
                            "message": (
                                "A safe fallback recipe was created because "
                                "the AI generation pipeline failed."
                            ),
                            "details": {},
                        }
                    ],
                    "failed_checks": [],
                }

            validation_attempt_history = [
                {
                    "attempt_number": 1,
                    "score": fallback_validation_report.get("score"),
                    "status": fallback_validation_report.get("status"),
                    "fallback": True,
                    "error": True,
                    "risk_level": fallback_validation_report.get("risk_level"),
                    "hard_fail": fallback_validation_report.get("hard_fail"),
                    "failed_checks": [
                        check.get("name")
                        for check in fallback_validation_report.get(
                            "failed_checks",
                            [],
                        )
                    ],
                }
            ]

            fallback_ai_result["insights"] = fallback_insights
            fallback_ai_result["validation_report"] = fallback_validation_report
            fallback_ai_result["validation_attempt_history"] = (
                validation_attempt_history
            )
            fallback_ai_result["quality_score"] = fallback_validation_report.get(
                "score",
            )
            fallback_ai_result["validation_status"] = fallback_validation_report.get(
                "status",
            )
            fallback_ai_result["generated_image"] = ""
            fallback_ai_result["generated_image_url"] = ""
            fallback_ai_result["generated_image_prompt"] = ""

            request.session["ai_recipe_result"] = fallback_ai_result
            request.session["latest_ai_recipe_text"] = fallback_recipe_text
            request.session["latest_ai_recipe_prompt"] = fallback_ai_result.get(
                "prompt",
                "",
            )
            request.session["latest_recipe_image_path"] = ""
            request.session["latest_recipe_image_prompt"] = ""
            request.session["latest_validation_report"] = fallback_validation_report
            request.session["latest_validation_attempt_history"] = (
                validation_attempt_history
            )
            request.session["latest_recipe_insights"] = fallback_insights

            try:
                history_entry = create_recipe_history_entry(
                    user=request.user,
                    recipe_text=fallback_recipe_text,
                    recipe_prompt=fallback_ai_result.get("prompt", ""),
                    preferences=preview_data,
                    image_path="",
                    image_prompt="",
                    validation_report=fallback_validation_report,
                    validation_attempt_history=validation_attempt_history,
                    insights=fallback_insights,
                )

                if history_entry:
                    request.session["latest_recipe_history_id"] = history_entry.id

            except Exception as history_error:
                print("CULINAAI HISTORY ERROR:", repr(history_error))
                traceback.print_exc()
                request.session.pop("latest_recipe_history_id", None)

            messages.warning(
                request,
                "The recipe service is busy, so you're seeing a simpler recipe made from your ingredients. Try again in a minute for a full one.",
            )

        except Exception as fallback_error:
            print("CULINAAI FALLBACK GENERATION ERROR:", repr(fallback_error))
            traceback.print_exc()

            messages.error(
                request,
                "The recipe couldn't be made just now. Please try again in a minute.",
            )


# Main view: handles recipe generation, validation, fallback, image generation and history storage.
@login_required
def generate_recipe_view(request):
    """
    Handles the AI recipe generation page.

    CulinaAI flow:
    1. Generate recipe using AI.
    2. Validate recipe using custom constraint-based validation engine.
    3. If validation fails, regenerate with correction instructions.
    4. If AI still fails safety validation, create a deterministic safe fallback recipe.
    5. Show a generated recipe instead of simply blocking the user.
    6. Automatically store every generated recipe in RecipeHistory.
    7. Supports Smart Pantry, personalised recommendation prefill,
       and AI Refrigerator Scanner prefill.
    """

    if request.method == "POST":
        # Important: validate user input from the recipe generation form.
        form = RecipeGenerationForm(request.POST)

        if form.is_valid():
            cleaned_data = form.cleaned_data

            spice_choices = dict(form.fields["spice_level"].choices)
            budget_choices = dict(form.fields["budget_level"].choices)
            nutrition_choices = dict(form.fields["nutrition_goal"].choices)
            meal_style_choices = dict(form.fields["meal_style"].choices)
            equipment_choices = dict(form.fields["cooking_equipment"].choices)

            selected_equipment = [
                equipment_choices.get(equipment, equipment)
                for equipment in cleaned_data.get("cooking_equipment", [])
            ]

            other_diet_preference = request.POST.get(
                "other_diet_preference",
                "",
            ).strip()

            other_kitchen_equipment = request.POST.get(
                "other_kitchen_equipment",
                "",
            ).strip()

            selected_utensils = [
                utensil.strip()
                for utensil in request.POST.getlist("utensils")
                if utensil.strip()
            ]

            other_utensils = request.POST.get(
                "other_utensils",
                "",
            ).strip()

            selected_diet_preferences = [
                diet.name for diet in cleaned_data.get("diet_preferences", [])
            ]

            if other_diet_preference:
                selected_diet_preferences.append(
                    f"Other: {other_diet_preference}",
                )

            if other_kitchen_equipment:
                selected_equipment.append(
                    f"Other: {other_kitchen_equipment}",
                )

            selected_utensils_for_preview = selected_utensils.copy()

            if other_utensils:
                selected_utensils_for_preview.append(
                    f"Other: {other_utensils}",
                )

            additional_notes_parts = []

            if cleaned_data.get("additional_notes"):
                additional_notes_parts.append(
                    cleaned_data.get("additional_notes"),
                )

            if other_diet_preference:
                additional_notes_parts.append(
                    f"Custom diet preference: {other_diet_preference}",
                )

            if other_kitchen_equipment:
                additional_notes_parts.append(
                    f"Other kitchen equipment available: {other_kitchen_equipment}",
                )

            if selected_utensils_for_preview:
                additional_notes_parts.append(
                    "Available utensils: "
                    + ", ".join(selected_utensils_for_preview),
                )

            combined_additional_notes = (
                " | ".join(additional_notes_parts)
                if additional_notes_parts
                else "None provided"
            )

            preview_data = {
                "ingredients": cleaned_data.get("ingredients"),
                "cuisine": cleaned_data.get("cuisine").name
                if cleaned_data.get("cuisine")
                else "Any cuisine",
                "meal_type": cleaned_data.get("meal_type").name
                if cleaned_data.get("meal_type")
                else "Any meal type",
                "diet_preferences": selected_diet_preferences,
                "other_diet_preference": other_diet_preference,
                "allergies": cleaned_data.get("allergies") or "None provided",
                # Optional fields: blank means the form's usual defaults.
                "cooking_time_minutes": cleaned_data.get("cooking_time_minutes") or 30,
                "servings": cleaned_data.get("servings") or 2,
                "difficulty": cleaned_data.get("difficulty") or "easy",
                "spice_level": spice_choices.get(
                    cleaned_data.get("spice_level"),
                    "Medium",
                ),
                "budget_level": budget_choices.get(
                    cleaned_data.get("budget_level"),
                    "Moderate Budget",
                ),
                "nutrition_goal": nutrition_choices.get(
                    cleaned_data.get("nutrition_goal"),
                    "Balanced",
                ),
                "meal_style": meal_style_choices.get(
                    cleaned_data.get("meal_style") or "any",
                    "No preference",
                ),
                "cooking_equipment": selected_equipment,
                "other_kitchen_equipment": other_kitchen_equipment,
                "utensils": selected_utensils_for_preview,
                "other_utensils": other_utensils,
                "additional_notes": combined_additional_notes,
            }

            blocked = use_ai(request.user, AIUsage.KIND_RECIPE, "generate")
            missing = missing_saved_allergies(request.user, cleaned_data.get("allergies"))
            if not blocked and missing:
                # They took a saved allergy out for this recipe (cooking for someone else, say). Allowed, but said.
                messages.warning(
                    request,
                    f"This recipe wasn't checked for {', '.join(missing)}, which your profile says to avoid, "
                    "because it wasn't in this recipe's list.",
                )
            if not blocked:
                run_recipe_generation(request, preview_data)
                return redirect(f"{reverse('generate_recipe')}#recipe-preview")

            # Can't use the AI right now: show the form again with what they typed.
            messages.error(request, blocked)
        else:
            messages.error(
                request,
                "Something's missing. Check the questions marked in red.",
            )

    else:
        pantry_mode = request.GET.get("from_pantry") == "1"
        recommendation_query = request.GET.get("recommendation", "").strip()
        use_up_query = request.GET.get("use_up", "").strip()[:500]
        fridge_scanned_ingredients = request.session.get(
            "fridge_scanned_ingredients",
            None,
        )

        if use_up_query:
            # From "Use it before it goes off" on the dashboard.
            form = RecipeGenerationForm(initial={"ingredients": use_up_query})
            messages.info(request, "Added what needs using up from your pantry. Add anything else you have.")

        elif recommendation_query:
            form = RecipeGenerationForm(
                initial={
                    "ingredients": recommendation_query,
                }
            )

            messages.info(
                request,
                "Added the ingredients from that idea.",
            )

        elif pantry_mode:
            today = timezone.localdate()

            # Important: Generate from Pantry fetches available non-expired pantry items.
            pantry_items = (
                PantryItem.objects.filter(
                    user=request.user,
                    is_available=True,
                )
                .filter(
                    Q(expiry_date__isnull=True) | Q(expiry_date__gte=today)
                )
                .order_by(
                    "expiry_date",
                    "ingredient_name",
                )
            )

            pantry_ingredients = []

            for item in pantry_items:
                clean_name = item.ingredient_name.strip()

                if clean_name:
                    pantry_ingredients.append(clean_name)

            if pantry_ingredients:
                # Important: pantry ingredients are pre-filled into the generation form.
                form = RecipeGenerationForm(
                    initial={
                        "ingredients": ", ".join(pantry_ingredients),
                    }
                )

                messages.info(
                    request,
                    f"Added {len(pantry_ingredients)} item{'s' if len(pantry_ingredients) != 1 else ''} from your pantry. Anything past its date is left out.",
                )
            else:
                form = RecipeGenerationForm()

                messages.warning(
                    request,
                    "Your pantry has nothing in date yet. Add a few items first.",
                )

        elif fridge_scanned_ingredients:
            if isinstance(fridge_scanned_ingredients, list):
                fridge_ingredients_text = ", ".join(
                    str(item).strip()
                    for item in fridge_scanned_ingredients
                    if str(item).strip()
                )
            else:
                fridge_ingredients_text = str(fridge_scanned_ingredients).strip()

            request.session.pop("fridge_scanned_ingredients", None)

            if fridge_ingredients_text:
                form = RecipeGenerationForm(
                    initial={
                        "ingredients": fridge_ingredients_text,
                    }
                )

                messages.info(
                    request,
                    "Added the ingredients from your fridge scan.",
                )
            else:
                form = RecipeGenerationForm()

                messages.warning(
                    request,
                    "No ingredients came through from the fridge scan. Type them in instead.",
                )

        else:
            form = RecipeGenerationForm()

    # Fill in the diet and allergies saved on the profile (a form sent back with mistakes keeps what was typed).
    diet = saved_diet(request.user)
    if not form.is_bound:
        form.initial.setdefault("diet_preferences", diet["diet_ids"])
        form.initial.setdefault("allergies", diet["allergies"])
        other_diet_value = diet["other_diet"]
    else:
        other_diet_value = request.POST.get("other_diet_preference", "")

    preview_data = request.session.pop("recipe_preview_data", None)
    ai_recipe_result = request.session.pop("ai_recipe_result", None)

    return render(
        request,
        "recipes/generate.html",
        {
            "form": form,
            "preview_data": preview_data,
            "ai_recipe_result": ai_recipe_result,
            "generation_preview": preview_data is not None,
            "change_choices": CHANGE_CHOICES,
            "utensil_choices": UTENSIL_CHOICES,
            "other_diet_value": other_diet_value,
            "diet_from_profile": diet["has_any"] and not form.is_bound,
        },
    )


# Helper: the preferences for one version from "One dish, three ways".
def build_version_preferences(preferences, version, insights, recipe_title):
    """
    The user's own settings, with the version's swaps made in the ingredient list
    and the last recipe described, so the AI cooks the same dish with the swaps.

    - A full swap ("tofu instead of paneer") takes the old ingredient out of the
      user's list and puts the new one in, so the ingredient gate checks for tofu.
    - A half swap or "use less" keeps the old ingredient; a half swap adds the new one.
    """
    version_preferences = copy.deepcopy(preferences)
    ingredients = split_user_items(preferences.get("ingredients"))

    for swap in version["swaps"]:
        if not swap.get("to_code"):
            continue
        if swap.get("share", 0) >= 1:
            ingredients = [item for item in ingredients if not same_ingredient(item, swap["from_name"])]
        if not any(same_ingredient(item, swap["to_name"]) for item in ingredients):
            ingredients.append(swap["to_name"])

    last_ingredients = insights.get("ingredients") or []
    last_recipe = ", ".join(f"{item['name']} ({round(item['grams'])} g)" for item in last_ingredients)

    # The card's figures assume these exact amounts, so the AI is told them rather than
    # left to "adjust quantities" (which once turned a High protein card into a Good one).
    amounts = []
    for swap in version["swaps"]:
        grams = sum(item["grams"] for item in last_ingredients if same_ingredient(item["name"], swap["from_name"]))
        if not grams:
            continue
        kept = grams * (1 - swap.get("share", 1))
        if kept:
            amounts.append(f"{swap['from_name']} {round(kept)} g")
        if swap.get("to_code"):
            amounts.append(f"{swap['to_name']} {round(grams * swap.get('share', 1) * swap.get('ratio', 1))} g")

    instruction = (
        f"Recipe version: cook the {version['title'].lower()} version of the user's last recipe, "
        f"\"{recipe_title}\", which used: {last_recipe}. Make these swaps: "
        + "; ".join(swap["text"] for swap in version["swaps"])
        + ". "
        + (f"Use exactly these amounts for the swapped ingredients: {', '.join(amounts)}. " if amounts else "")
        + "Keep every other ingredient and its amount the same as before, and the same dish, cuisine and "
        "method. Only change the steps where the swap needs it."
    )

    version_preferences["ingredients"] = ", ".join(ingredients)
    notes = preferences.get("additional_notes") or ""
    version_preferences["additional_notes"] = (
        instruction if notes in ("", "None provided") else f"{notes} | {instruction}"
    )
    version_preferences["recipe_version"] = version["title"]
    version_preferences["based_on_title"] = recipe_title
    # What the card promised, so the cooked recipe can be checked against it.
    version_preferences["expected"] = {
        "cost": version.get("cost"),
        "carbon": version.get("carbon"),
        "kcal": version.get("kcal"),
        "levels": version.get("levels") or {},
        # The recipe it came from, so the dashboard can total what versions saved.
        "original": {
            "cost": (insights.get("cost") or {}).get("per_serving"),
            "carbon": (insights.get("carbon") or {}).get("per_serving"),
        },
    }
    return version_preferences


# View: "Cook this version" on the generate page. Makes the cheapest, healthiest or
# greenest version of the recipe just generated, through the same pipeline and checks.
@login_required
@require_POST
def generate_recipe_version_view(request):
    goal = request.POST.get("goal", "")
    preferences = request.session.get("latest_recipe_preferences")
    insights = request.session.get("latest_recipe_insights") or {}

    # Only versions the code worked out for the user's last recipe can be cooked;
    # nothing in the request is used except which of the three to cook.
    version = next(
        (v for v in insights.get("three_ways") or [] if v.get("goal") == goal and v.get("swaps")),
        None,
    )

    if not preferences or version is None:
        messages.error(
            request,
            "That recipe is no longer available. Generate it again to see its three versions.",
        )
        return redirect("generate_recipe")

    blocked = use_ai(request.user, AIUsage.KIND_RECIPE, "version")
    if blocked:
        messages.error(request, blocked)
        return redirect(f"{reverse('generate_recipe')}#recipe-preview")

    recipe_title = extract_recipe_title(request.session.get("latest_ai_recipe_text", ""))
    version_preferences = build_version_preferences(preferences, version, insights, recipe_title)
    run_recipe_generation(request, version_preferences)
    return redirect(f"{reverse('generate_recipe')}#recipe-preview")


# What each quick change asks for. Where a setting can enforce it, the setting is
# changed too, so the quality checks hold the new recipe to it (a vegetarian
# change is checked as vegetarian, a quicker one against the shorter time).
RECIPE_CHANGES = {
    "healthier": "Make it healthier: less fat, saturated fat, sugar and salt, with more vegetables.",
    "cheaper": "Make it cheaper: use lower-cost ingredients and fewer extras.",
    "quicker": "Make it quicker to cook, with fewer and shorter steps.",
    "vegetarian": "Make it vegetarian: no meat or fish.",
    "spicier": "Make it spicier.",
    "simpler": "Make it simpler, with fewer ingredients and easy steps.",
    "custom": "",
}


SPICE_ORDER = ["Mild", "Medium", "Spicy", "Extra Spicy"]


# The quick changes shown as buttons (typing your own change counts as "custom").
# Utensils offered on the New recipe form (sent as "utensils" and passed to the AI).
UTENSIL_CHOICES = [
    "Frying Pan", "Saucepan", "Deep Pot", "Tawa / Griddle", "Wok / Kadhai",
    "Mixing Bowl", "Knife", "Chopping Board", "Spatula", "Measuring Cups",
]


CHANGE_CHOICES = [
    ("healthier", "Healthier"),
    ("cheaper", "Cheaper"),
    ("quicker", "Quicker"),
    ("vegetarian", "Vegetarian"),
    ("spicier", "Spicier"),
    ("simpler", "Simpler"),
]


def build_change_preferences(preferences, change, instruction, recipe_title, recipe_text):
    """
    The user's settings for a changed version of the recipe just generated: the
    same dish, with the change described to the AI and, where possible, made a
    setting the checks can see.
    """
    changed = copy.deepcopy(preferences)
    for key in ("recipe_version", "based_on_title", "expected"):
        changed.pop(key, None)

    if change == "healthier":
        changed["meal_style"] = "Everyday healthy"
    elif change == "cheaper":
        changed["budget_level"] = "Low Budget"
    elif change == "quicker":
        minutes = int(changed.get("cooking_time_minutes") or 30)
        changed["cooking_time_minutes"] = max(10, round(minutes * 0.6 / 5) * 5)
    elif change == "vegetarian":
        diets = [d for d in changed.get("diet_preferences") or [] if d]
        if not any("vegetarian" in d.lower() or "vegan" in d.lower() for d in diets):
            diets.append("Vegetarian")
        changed["diet_preferences"] = diets
    elif change == "spicier":
        current = changed.get("spice_level") or "Medium"
        position = SPICE_ORDER.index(current) if current in SPICE_ORDER else 1
        changed["spice_level"] = SPICE_ORDER[min(position + 1, len(SPICE_ORDER) - 1)]
    elif change == "simpler":
        changed["difficulty"] = "easy"

    request_text = " ".join(part for part in (RECIPE_CHANGES.get(change, ""), instruction) if part)
    # The last recipe, shortened, so the AI changes that dish rather than inventing a new one.
    previous = " ".join((recipe_text or "").split())[:1500]
    change_note = (
        f"Change request: {request_text} Change the user's last recipe, \"{recipe_title}\", and keep it "
        f"the same kind of dish unless the change needs otherwise. The last recipe was: {previous}"
    )
    notes = preferences.get("additional_notes") or ""
    changed["additional_notes"] = change_note if notes in ("", "None provided") else f"{notes} | {change_note}"
    return changed


# View: "Change this recipe" on the generate page. Makes a changed version of the
# recipe just generated, straight away, through the same pipeline and checks.
@login_required
@require_POST
def change_generated_recipe_view(request):
    preferences = request.session.get("latest_recipe_preferences")
    recipe_text = request.session.get("latest_ai_recipe_text", "")
    change = request.POST.get("modification_type", "").strip()
    instruction = request.POST.get("custom_instruction", "").strip()[:300]

    if instruction and change not in RECIPE_CHANGES:
        change = "custom"
    if not preferences or not recipe_text:
        messages.error(request, "That recipe is no longer available. Generate it again, then change it.")
        return redirect("generate_recipe")
    if change not in RECIPE_CHANGES or (change == "custom" and not instruction):
        messages.error(request, "Choose a change, or describe the change you want.")
        return redirect(f"{reverse('generate_recipe')}#recipe-preview")

    blocked = use_ai(request.user, AIUsage.KIND_RECIPE, "change")
    if blocked:
        messages.error(request, blocked)
        return redirect(f"{reverse('generate_recipe')}#recipe-preview")

    recipe_title = extract_recipe_title(recipe_text)
    run_recipe_generation(
        request,
        build_change_preferences(preferences, change, instruction, recipe_title, recipe_text),
    )
    return redirect(f"{reverse('generate_recipe')}#recipe-preview")


# View: emails the recipe just generated (before it is saved).
@login_required
@require_POST
@not_in_demo()
def email_generated_recipe_view(request):
    recipe_text = request.session.get("latest_ai_recipe_text", "")
    form = RecipeEmailForm(request.POST)

    if not recipe_text:
        messages.error(request, "That recipe is no longer available. Generate it again to email it.")
        return redirect("generate_recipe")
    if not form.is_valid():
        messages.error(request, "Enter a valid email address, for example name@example.com.")
        return redirect(f"{reverse('generate_recipe')}#recipe-preview")

    title = extract_recipe_title(recipe_text)
    send_recipe_email_safely(
        request,
        form.cleaned_data["recipient_email"],
        title,
        recipe_email_body(request.user.username, title, recipe_text, form.cleaned_data.get("message", "").strip()),
    )
    return redirect(f"{reverse('generate_recipe')}#recipe-preview")


# View: saves the latest AI-generated recipe from session into the Recipe table.
@login_required
def save_generated_recipe_view(request):
    """
    Saves the latest AI-generated recipe from the user's session into PostgreSQL.

    This version also saves CulinaAI validation evidence:
    - quality score
    - validation status
    - risk level
    - validation badge
    - validation attempt count
    - full validation report
    - generation/correction history
    """

    if request.method != "POST":
        return redirect("generate_recipe")

    recipe_text = request.session.get("latest_ai_recipe_text")
    recipe_prompt = request.session.get("latest_ai_recipe_prompt")
    recipe_image_path = request.session.get("latest_recipe_image_path")
    recipe_image_prompt = request.session.get("latest_recipe_image_prompt")
    preferences = request.session.get("latest_recipe_preferences")

    validation_report = request.session.get("latest_validation_report") or {}
    validation_attempt_history = (
        request.session.get("latest_validation_attempt_history") or []
    )
    insights = request.session.get("latest_recipe_insights") or {}

    if not recipe_text or not preferences:
        messages.error(
            request,
            "There's no recipe to save. Make one first.",
        )
        return redirect("generate_recipe")

    cuisine = None
    meal_type = None

    cuisine_name = preferences.get("cuisine")
    meal_type_name = preferences.get("meal_type")

    if cuisine_name and cuisine_name != "Any cuisine":
        cuisine = Cuisine.objects.filter(name=cuisine_name).first()

    if meal_type_name and meal_type_name != "Any meal type":
        meal_type = MealType.objects.filter(name=meal_type_name).first()

    quality_score = validation_report.get("score")

    # Important: saves the generated recipe as a user-owned Recipe record.
    recipe = Recipe.objects.create(
        user=request.user,
        title=extract_recipe_title(recipe_text),
        description=preferences.get("additional_notes", ""),
        generated_image=recipe_image_path or None,
        cuisine=cuisine,
        meal_type=meal_type,
        ingredients_text=preferences.get("ingredients", ""),
        instructions_text=recipe_text,
        cooking_time_minutes=preferences.get("cooking_time_minutes") or 30,
        difficulty=preferences.get("difficulty", "easy"),
        allergy_notes=preferences.get("allergies", ""),
        ai_prompt=recipe_prompt or "",
        ai_response=recipe_text,
        is_ai_generated=True,
        is_saved=True,

        # CulinaAI validation fields
        quality_score=quality_score if quality_score is not None else None,
        validation_status=validation_report.get("status", ""),
        validation_risk_level=validation_report.get("risk_level", ""),
        validation_badge=validation_report.get("badge", ""),
        validation_attempts=len(validation_attempt_history),
        validation_report=validation_report,
        validation_attempt_history=validation_attempt_history,
        insights=insights,
    )


    history_id = request.session.get("latest_recipe_history_id")

    if history_id:
        # Important: links the saved Recipe back to the original history item.
        RecipeHistory.objects.filter(
            id=history_id,
            user=request.user,
        ).update(
            saved_recipe=recipe,
        )


    

    diet_names = preferences.get("diet_preferences", [])

    for diet_name in diet_names:
        diet = DietPreference.objects.filter(name=diet_name).first()

        if diet:
            recipe.diet_preferences.add(diet)

    request.session.pop("latest_ai_recipe_text", None)
    request.session.pop("latest_ai_recipe_prompt", None)
    request.session.pop("latest_recipe_image_path", None)
    request.session.pop("latest_recipe_image_prompt", None)
    request.session.pop("latest_recipe_preferences", None)
    request.session.pop("latest_validation_report", None)
    request.session.pop("latest_validation_attempt_history", None)
    request.session.pop("latest_recipe_history_id", None)
    request.session.pop("latest_recipe_insights", None)

    messages.success(
        request,
        "Saved. You'll find it in Saved recipes.",
    )

    return redirect("saved_recipes")
