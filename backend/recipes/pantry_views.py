"""
The pantry: list, add (one or several), edit and delete.

(Split out of views.py; recipes/views.py still re-exports everything.)
"""

from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone


from .forms import (
    PantryItemForm,
)
from .models import (
    PantryItem,
)

from .recommendation_service import get_personalised_recommendations




# View: manages Smart Pantry items, bulk add, expiry insights and recommendations.
@login_required
def pantry_list_view(request):
    """
    Displays the logged-in user's Smart Pantry items and handles adding new items.

    Supports:
    - single pantry item add
    - bulk pantry item add
    - expiry insight
    - personalised recommendations
    """
    #gives today dates
    today = timezone.localdate()
    soon_date = today + timedelta(days=3)

    if request.method == "POST":
        pantry_action = request.POST.get("pantry_action", "single_add")

        if pantry_action == "bulk_add":
            ingredient_names = request.POST.getlist("bulk_ingredient_name")
            quantities = request.POST.getlist("bulk_quantity")
            units = request.POST.getlist("bulk_unit")
            categories = request.POST.getlist("bulk_category")
            expiry_dates = request.POST.getlist("bulk_expiry_date")
            notes_list = request.POST.getlist("bulk_notes")

            added_count = 0
            error_rows = []

            row_count = max(
                len(ingredient_names),
                len(quantities),
                len(units),
                len(categories),
                len(expiry_dates),
                len(notes_list),
            )

            for index in range(row_count):
                ingredient_name = (
                    ingredient_names[index].strip()
                    if index < len(ingredient_names)
                    else ""
                )

                quantity = (
                    quantities[index].strip()
                    if index < len(quantities)
                    else ""
                )

                unit = (
                    units[index].strip()
                    if index < len(units) and units[index].strip()
                    else "other"
                )

                category = (
                    categories[index].strip()
                    if index < len(categories) and categories[index].strip()
                    else "other"
                )

                expiry_date = (
                    expiry_dates[index].strip()
                    if index < len(expiry_dates)
                    else ""
                )

                notes = (
                    notes_list[index].strip()
                    if index < len(notes_list)
                    else ""
                )

                row_has_data = any(
                    [
                        ingredient_name,
                        quantity,
                        expiry_date,
                        notes,
                    ]
                )

                if not row_has_data:
                    continue

                if not ingredient_name:
                    error_rows.append(index + 1)
                    continue

                item_form = PantryItemForm(
    {
        "ingredient_name": ingredient_name,
        "quantity": quantity or "",
        "unit": unit or "other",
        "category": category or "other",
        "expiry_date": expiry_date or "",
        "notes": notes or "",
        "is_available": "on",
    }
)

                if item_form.is_valid():
                    pantry_item = item_form.save(commit=False)
                    pantry_item.user = request.user
                    pantry_item.save()
                    added_count += 1
                else:
                    error_rows.append(index + 1)

            if added_count:
                messages.success(
                    request,
                    f"Added {added_count} item{'s' if added_count > 1 else ''} to your pantry.",
                )

            if error_rows:
                messages.error(
                    request,
                    "Some rows weren't added. Check row "
                    + ", ".join(str(row) for row in error_rows)
                    + ".",
                )

            if not added_count and not error_rows:
                messages.info(
                    request,
                    "Nothing was added because all the rows were empty.",
                )

            return redirect("pantry_list")

        form = PantryItemForm(request.POST)

        if form.is_valid():
            # Important: commit=False lets us attach the logged-in user before saving.
            pantry_item = form.save(commit=False)
            pantry_item.user = request.user
            pantry_item.save()

            messages.success(
                request,
                f"Added {pantry_item.ingredient_name} to your pantry.",
            )
            return redirect("pantry_list")

        messages.error(
            request,
            "That item couldn't be added. Check the details and try again.",
        )

    else:
        form = PantryItemForm()

    # Important: pantry page only displays items belonging to the logged-in user.
    pantry_items = PantryItem.objects.filter(
        user=request.user,
    ).order_by(
        "expiry_date",
        "ingredient_name",
    )

    available_pantry_items = pantry_items.filter(
        is_available=True,
    )

    #expired items calculation
    expired_items = available_pantry_items.filter(
        expiry_date__lt=today,
    )

    #expiring soon items
    expiring_soon_items = available_pantry_items.filter(
        expiry_date__gte=today,
        expiry_date__lte=soon_date,
    )

    priority_pantry_items = (
        available_pantry_items.filter(
            expiry_date__gte=today,
        )
        .order_by("expiry_date", "ingredient_name")[:5]
    )

    # Important: recommendation service builds pantry/user-based suggestions.
    personalised_recommendations = get_personalised_recommendations(
        request.user,
        limit=4,
    )

    context = {
        "form": form,
        "unit_choices": PantryItem.UNIT_CHOICES,
        "category_choices": PantryItem.CATEGORY_CHOICES,
        "pantry_items": pantry_items,
        "total_items": pantry_items.count(), #items for counting are displayed here
        "available_items_count": available_pantry_items.count(),
        "expired_items_count": expired_items.count(),
        "expiring_soon_count": expiring_soon_items.count(),
        "expired_items": expired_items,
        "expiring_soon_items": expiring_soon_items,
        "priority_pantry_items": priority_pantry_items,
        "personalised_recommendations": personalised_recommendations,
    }

    return render(request, "recipes/pantry_list.html", context)


# View: updates only the logged-in user’s own pantry item.
@login_required
def pantry_item_update_view(request, item_id):
    """
    Allows a logged-in user to update only their own pantry item.
    """

    # Important: ownership check prevents users editing another user’s pantry item.
    pantry_item = get_object_or_404(
        PantryItem,
        id=item_id,
        user=request.user,
    )

    if request.method == "POST":
        form = PantryItemForm(request.POST, instance=pantry_item)

        if form.is_valid():
            updated_item = form.save()

            messages.success(
                request,
                f"Saved your changes to {updated_item.ingredient_name}.",
            )
            return redirect("pantry_list")

        messages.error(
            request,
            "Your changes weren't saved. Check the details and try again.",
        )

    else:
        form = PantryItemForm(instance=pantry_item)

    context = {
        "form": form,
        "pantry_item": pantry_item,
    }

    return render(request, "recipes/pantry_item_form.html", context)


# View: deletes only the logged-in user’s own pantry item.
@login_required
def pantry_item_delete_view(request, item_id):
    """
    Allows a logged-in user to delete only their own pantry item.
    """

    pantry_item = get_object_or_404(
        PantryItem,
        id=item_id,
        user=request.user,
    )

    if request.method == "POST":
        item_name = pantry_item.ingredient_name
        # Important: deletes the selected pantry item after ownership is verified.
        pantry_item.delete()

        messages.success(
            request,
            f"Removed {item_name} from your pantry.",
        )
        return redirect("pantry_list")

    context = {
        "pantry_item": pantry_item,
    }

    return render(request, "recipes/pantry_item_confirm_delete.html", context)
