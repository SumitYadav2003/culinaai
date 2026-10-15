"""
Pages for the weekly meal plan and its shopping list. See meal_plan_service.py
for how the list is worked out. Nothing here calls the AI.
"""

import logging
import time
from datetime import date, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .meal_plan_service import (
    build_shopping_list,
    build_week,
    copy_week,
    long_day,
    parse_week,
    recipe_base_servings,
    shopping_list_text,
    week_label,
    week_start_for,
)
from .models import FavouriteRecipe, MealPlanEntry, Recipe, ShoppingListCheck, ShoppingListExtra

logger = logging.getLogger(__name__)

# How far ahead (and back) a meal can be planned.
PLAN_DAYS_AHEAD = 365
PLAN_DAYS_BACK = 31
EMAIL_WAIT_SECONDS = 60


def plan_url(week_start):
    return f"{reverse('meal_plan')}?week={week_start.isoformat()}"


def shopping_url(week_start):
    return f"{reverse('shopping_list')}?week={week_start.isoformat()}"


def safe_next(request, fallback):
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return fallback


def read_date(value):
    """A plan date from the form, or None if it's missing, invalid or too far away."""

    try:
        day = date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    today = timezone.localdate()
    if not (today - timedelta(days=PLAN_DAYS_BACK) <= day <= today + timedelta(days=PLAN_DAYS_AHEAD)):
        return None
    return day


def read_servings(value, default):
    try:
        servings = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(servings, 1), MealPlanEntry.MAX_SERVINGS)


def read_meal(value):
    meals = dict(MealPlanEntry.MEAL_CHOICES)
    return value if value in meals else MealPlanEntry.MEAL_DINNER


def day_options(chosen, count=14):
    """The days offered in the "Which day?" menu: two weeks that include the chosen day."""

    today = timezone.localdate()
    if today - timedelta(days=PLAN_DAYS_BACK) <= chosen <= today + timedelta(days=count - 1):
        start = min(today, chosen)
    else:
        start = week_start_for(chosen)
    options = []
    for n in range(count):
        day = start + timedelta(days=n)
        label = long_day(day, today)
        options.append({"value": day.isoformat(), "label": label[:1].upper() + label[1:]})
    return options


@login_required
def meal_plan_view(request):
    week_start = parse_week(request.GET.get("week"))
    days = build_week(request.user, week_start)
    planned = sum(len(day["entries"]) for day in days)
    this_week = week_start_for(timezone.localdate())

    return render(request, "recipes/meal_plan.html", {
        "days": days,
        "week_start": week_start,
        "week_label": week_label(week_start),
        "previous_week": week_start - timedelta(days=7),
        "next_week": week_start + timedelta(days=7),
        "this_week": this_week,
        "is_this_week": week_start == this_week,
        "planned_count": planned,
        "has_saved_recipes": Recipe.objects.filter(user=request.user, is_saved=True).exists(),
        "last_week_has_plan": MealPlanEntry.objects.filter(
            user=request.user,
            recipe__is_saved=True,
            date__gte=week_start - timedelta(days=7),
            date__lt=week_start,
        ).exists(),
        "meal_choices": MealPlanEntry.MEAL_CHOICES,
        "max_servings": MealPlanEntry.MAX_SERVINGS,
    })


@login_required
def meal_plan_add_view(request):
    """
    Add a saved recipe to the plan. Opened from a recipe ("Add to plan", with
    ?recipe=) or from a day on the plan ("Add a meal", with ?date=).
    """

    recipe = None
    recipe_id = request.POST.get("recipe") or request.GET.get("recipe")
    if recipe_id:
        recipe = Recipe.objects.filter(id=recipe_id, user=request.user, is_saved=True).first()
        if recipe is None and request.method == "POST":
            messages.error(request, "Choose one of your saved recipes.")
            return redirect("meal_plan_add")

    today = timezone.localdate()
    chosen_date = read_date(request.GET.get("date")) or today
    errors = {}

    if request.method == "POST":
        day = read_date(request.POST.get("date"))
        if recipe is None:
            errors["recipe"] = "Choose a recipe."
        if day is None:
            errors["date"] = "Choose a day in the next year."
        if not errors:
            meal = read_meal(request.POST.get("meal"))
            servings = read_servings(request.POST.get("servings"), recipe_base_servings(recipe))
            MealPlanEntry.objects.create(user=request.user, recipe=recipe, date=day, meal=meal, servings=servings)
            messages.success(
                request,
                f'Added "{recipe.title}" to {long_day(day, today)}, '
                f"{dict(MealPlanEntry.MEAL_CHOICES)[meal].lower()}, for {servings}.",
            )
            return redirect(safe_next(request, plan_url(week_start_for(day))))
        chosen_date = read_date(request.POST.get("date")) or chosen_date

    saved = Recipe.objects.filter(user=request.user, is_saved=True).order_by("title")
    favourite_ids = set(FavouriteRecipe.objects.filter(user=request.user).values_list("recipe_id", flat=True))

    return render(request, "recipes/meal_plan_add.html", {
        "recipe": recipe,
        "favourites": [r for r in saved if r.id in favourite_ids],
        "others": [r for r in saved if r.id not in favourite_ids],
        "has_saved_recipes": saved.exists(),
        "day_options": day_options(chosen_date),
        "chosen_date": chosen_date.isoformat(),
        "chosen_meal": read_meal(request.POST.get("meal") or request.GET.get("meal") or MealPlanEntry.MEAL_DINNER),
        "servings": read_servings(request.POST.get("servings"), recipe_base_servings(recipe) if recipe else 2),
        "base_servings": recipe_base_servings(recipe) if recipe else None,
        "meal_choices": MealPlanEntry.MEAL_CHOICES,
        "max_servings": MealPlanEntry.MAX_SERVINGS,
        "next": safe_next(request, ""),
        "back_url": safe_next(request, plan_url(week_start_for(chosen_date))),
        "errors": errors,
    })


@login_required
@require_POST
def meal_plan_update_view(request, entry_id):
    """Change the servings, day or meal of one planned meal."""

    entry = get_object_or_404(MealPlanEntry, id=entry_id, user=request.user)
    entry.servings = read_servings(request.POST.get("servings"), entry.servings)
    if request.POST.get("date"):
        entry.date = read_date(request.POST.get("date")) or entry.date
    if request.POST.get("meal"):
        entry.meal = read_meal(request.POST.get("meal"))
    entry.save()
    messages.success(request, f'Updated "{entry.recipe.title}".')
    return redirect(safe_next(request, plan_url(week_start_for(entry.date))))


@login_required
@require_POST
def meal_plan_remove_view(request, entry_id):
    entry = get_object_or_404(MealPlanEntry, id=entry_id, user=request.user)
    week_start = week_start_for(entry.date)
    title = entry.recipe.title
    entry.delete()
    messages.info(request, f'Took "{title}" off the plan.')
    return redirect(safe_next(request, plan_url(week_start)))


@login_required
@require_POST
def meal_plan_copy_view(request):
    """Copy last week's meals into this week."""

    week_start = parse_week(request.POST.get("week"))
    added = copy_week(request.user, week_start - timedelta(days=7), week_start)
    if added:
        messages.success(request, f"Copied {added} meal{'s' if added != 1 else ''} from last week.")
    else:
        messages.info(request, "Nothing to copy: those meals are already on this week.")
    return redirect(plan_url(week_start))


@login_required
def shopping_list_view(request):
    week_start = parse_week(request.GET.get("week"))
    shopping = build_shopping_list(request.user, week_start)
    return render(request, "recipes/shopping_list.html", {
        "shopping": shopping,
        "week_start": week_start,
        "week_label": week_label(week_start),
        "previous_week": week_start - timedelta(days=7),
        "next_week": week_start + timedelta(days=7),
        "is_this_week": week_start == week_start_for(timezone.localdate()),
        "list_text": shopping_list_text(shopping, week_start),
    })


def wants_json(request):
    return request.headers.get("x-requested-with") == "fetch"


@login_required
@require_POST
def shopping_toggle_view(request):
    """Tick or untick an item. Works with JavaScript (returns JSON) and without (redirects back)."""

    week_start = parse_week(request.POST.get("week"))
    key = (request.POST.get("key") or "").strip()[:200]
    done = False
    if key:
        check = ShoppingListCheck.objects.filter(user=request.user, week_start=week_start, item_key=key)
        if check.exists():
            check.delete()
        else:
            ShoppingListCheck.objects.create(user=request.user, week_start=week_start, item_key=key)
            done = True
    if wants_json(request):
        return JsonResponse({"ok": bool(key), "done": done})
    return redirect(shopping_url(week_start))


@login_required
@require_POST
def shopping_extra_add_view(request):
    week_start = parse_week(request.POST.get("week"))
    name = " ".join((request.POST.get("name") or "").split())[:120]
    if name:
        ShoppingListExtra.objects.create(user=request.user, week_start=week_start, name=name)
    else:
        messages.error(request, "Type what you want to add.")
    return redirect(f"{shopping_url(week_start)}#extras")


@login_required
@require_POST
def shopping_extra_toggle_view(request, extra_id):
    extra = get_object_or_404(ShoppingListExtra, id=extra_id, user=request.user)
    extra.done = not extra.done
    extra.save(update_fields=["done"])
    if wants_json(request):
        return JsonResponse({"ok": True, "done": extra.done})
    return redirect(shopping_url(extra.week_start))


@login_required
@require_POST
def shopping_extra_remove_view(request, extra_id):
    extra = get_object_or_404(ShoppingListExtra, id=extra_id, user=request.user)
    week_start = extra.week_start
    extra.delete()
    return redirect(f"{shopping_url(week_start)}#extras")


@login_required
@require_POST
def shopping_clear_ticks_view(request):
    week_start = parse_week(request.POST.get("week"))
    ShoppingListCheck.objects.filter(user=request.user, week_start=week_start).delete()
    ShoppingListExtra.objects.filter(user=request.user, week_start=week_start).update(done=False)
    messages.info(request, "Cleared the ticks.")
    return redirect(shopping_url(week_start))


@login_required
@require_POST
def shopping_email_view(request):
    """Emails the list to the user's own address. Once a minute at most."""

    week_start = parse_week(request.POST.get("week"))
    back = shopping_url(week_start)

    if not request.user.email:
        messages.error(request, "Add an email address on your profile first.")
        return redirect(back)

    last_sent = request.session.get("shopping_email_sent_at") or 0
    if time.time() - last_sent < EMAIL_WAIT_SECONDS:
        messages.info(request, "We've just sent it. Check your inbox, or try again in a minute.")
        return redirect(back)

    shopping = build_shopping_list(request.user, week_start)
    try:
        send_mail(
            subject=f"Your shopping list for {week_label(week_start)}",
            message=shopping_list_text(shopping, week_start),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[request.user.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Couldn't email a shopping list")
        messages.error(request, "We couldn't send the email just now. Please try again in a few minutes.")
        return redirect(back)

    request.session["shopping_email_sent_at"] = time.time()
    messages.success(request, f"Sent the list to {request.user.email}.")
    return redirect(back)
