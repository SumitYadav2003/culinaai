from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import FridgeScanConfirmForm, FridgeScanUploadForm
from .fridge_scanner_service import scan_fridge_image
from .models import FridgeScan, PantryItem


def normalise_ingredient_list_for_comparison(items):
    """
    Normalises ingredient lists so we can check whether the user has actually
    changed the confirmed ingredient list before saving again.
    """

    if not items:
        return []

    return [
        str(item).strip().lower()
        for item in items
        if str(item).strip()
    ]


def add_confirmed_items_to_pantry(user, confirmed_items):
    """
    Adds confirmed fridge scan ingredients into the user's pantry.

    Duplicate pantry items are skipped using case-insensitive matching.
    Fridge scanner only detects ingredient names, so expiry dates are not
    automatically added. Users can edit pantry items later to add expiry dates.
    """

    created_count = 0
    skipped_count = 0

    for item in confirmed_items:
        ingredient_name = item.strip()

        if not ingredient_name:
            continue

        already_exists = PantryItem.objects.filter(
            user=user,
            ingredient_name__iexact=ingredient_name,
        ).exists()

        if already_exists:
            skipped_count += 1
            continue

        PantryItem.objects.create(
            user=user,
            ingredient_name=ingredient_name,
            quantity=None,
            unit="pcs",
            category="other",
            is_available=True,
            notes=(
                "Added from AI Refrigerator Scanner. "
                "Expiry date was not detected from the image. "
                "Edit this pantry item to add an expiry date for expiry tracking."
            ),
        )

        created_count += 1

    return created_count, skipped_count


@login_required
def fridge_scan_upload_view(request):
    """
    Allows the user to upload a refrigerator image.

    Professional validation flow:
    - User uploads an image.
    - FridgeScan record is created.
    - AI scanner validates whether the image is food/fridge/pantry related.
    - Invalid images are rejected with a clear validation message.
    - Valid images are redirected to confirmation page.
    """

    if request.method == "POST":
        form = FridgeScanUploadForm(request.POST, request.FILES)

        if form.is_valid():
            fridge_scan = form.save(commit=False)
            fridge_scan.user = request.user
            fridge_scan.scan_status = FridgeScan.STATUS_PENDING
            fridge_scan.save()

            scan_result = scan_fridge_image(fridge_scan)

            detected_items = scan_result.get("detected_items", [])
            detected_count = len(detected_items)
            validation = scan_result.get("validation", {})
            result_message = scan_result.get("message", "")

            if scan_result.get("success"):
                confidence = validation.get("confidence")
                image_quality = validation.get("image_quality", "unknown")
                image_context = validation.get("image_context", "food image")

                if detected_count > 0:
                    messages.success(
                        request,
                        (
                            f"Fridge scan validated successfully. "
                            f"{detected_count} possible ingredient(s) were detected."
                        ),
                    )

                    if confidence is not None:
                        messages.info(
                            request,
                            (
                                f"Image context: {image_context}. "
                                f"Image quality: {image_quality}. "
                                f"Validation confidence: {confidence}%."
                            ),
                        )

                else:
                    messages.warning(
                        request,
                        (
                            "The image was accepted as food-related, but no clear ingredients "
                            "were detected. You can still enter the ingredient list manually."
                        ),
                    )

                if fridge_scan.error_message:
                    messages.warning(
                        request,
                        fridge_scan.error_message,
                    )

                return redirect("fridge_scan_confirm", scan_id=fridge_scan.id)

            messages.error(
                request,
                result_message
                or (
                    "The image failed refrigerator scanner validation. "
                    "Please upload a clear refrigerator, pantry, grocery, or food storage image."
                ),
            )

            return redirect("fridge_scan_upload")

        messages.error(
            request,
            "Please upload a valid JPG, PNG, or WEBP image within the allowed file size.",
        )

    else:
        form = FridgeScanUploadForm()

    recent_scans = FridgeScan.objects.filter(
        user=request.user,
    )[:5]

    context = {
        "form": form,
        "recent_scans": recent_scans,
    }

    return render(request, "recipes/fridge_scan_upload.html", context)


@login_required
def fridge_scan_confirm_view(request, scan_id):
    """
    Allows the user to confirm or edit AI-detected fridge ingredients.

    Safety rule:
    - Failed scans cannot be used for pantry or recipe generation.
    - User must confirm detected ingredients before use.
    - If user edits and saves the list, the confirmed edited list is shown again.
    - Repeated Save Confirmation without any list changes is blocked.
    """

    fridge_scan = get_object_or_404(
        FridgeScan,
        id=scan_id,
        user=request.user,
    )

    if fridge_scan.scan_status == FridgeScan.STATUS_FAILED:
        messages.error(
            request,
            fridge_scan.error_message
            or (
                "This scan failed validation and cannot be used. "
                "Please upload a clearer refrigerator or food-related image."
            ),
        )

        return redirect("fridge_scan_upload")

    if request.method == "POST":
        form = FridgeScanConfirmForm(
            request.POST,
            detected_items=(
                fridge_scan.confirmed_items
                if fridge_scan.confirmed_items
                else fridge_scan.detected_items
            ),
        )

        if form.is_valid():
            confirmed_items = form.get_confirmed_items_list()
            action = request.POST.get("action")

            previous_confirmed_items = fridge_scan.confirmed_items or []

            normalised_previous_items = normalise_ingredient_list_for_comparison(
                previous_confirmed_items,
            )

            normalised_new_items = normalise_ingredient_list_for_comparison(
                confirmed_items,
            )

            list_already_saved = (
                bool(previous_confirmed_items)
                and normalised_previous_items == normalised_new_items
            )

            if action == "save_only" and list_already_saved:
                messages.info(
                    request,
                    (
                        "This ingredient list is already saved. "
                        "Edit, add, or remove an ingredient before saving again."
                    ),
                )

                return redirect("fridge_scan_confirm", scan_id=fridge_scan.id)

            fridge_scan.confirmed_items = confirmed_items
            fridge_scan.scan_status = FridgeScan.STATUS_COMPLETED
            fridge_scan.error_message = ""
            fridge_scan.save(
                update_fields=[
                    "confirmed_items",
                    "scan_status",
                    "error_message",
                    "updated_at",
                ]
            )

            if action == "add_to_pantry":
                created_count, skipped_count = add_confirmed_items_to_pantry(
                    request.user,
                    confirmed_items,
                )

                if created_count > 0:
                    messages.success(
                        request,
                        (
                            f"{created_count} ingredient(s) added to your pantry. "
                            "Expiry dates cannot be detected from the refrigerator image, "
                            "so please edit the new pantry items and add expiry dates to enable "
                            "Expired, Expiring Soon, and Priority Ingredients tracking."
                        ),
                    )

                if skipped_count > 0:
                    messages.info(
                        request,
                        f"{skipped_count} duplicate pantry item(s) were skipped.",
                    )

                if created_count == 0 and skipped_count == 0:
                    messages.warning(
                        request,
                        (
                            "No valid ingredients were added to pantry. "
                            "Please check the confirmed list and try again."
                        ),
                    )

                return redirect("pantry_list")

            if action == "generate_recipe":
                request.session["fridge_scanned_ingredients"] = confirmed_items
                request.session.modified = True

                messages.success(
                    request,
                    "Confirmed fridge ingredients are ready for recipe generation.",
                )

                return redirect("generate_recipe")

            messages.success(
                request,
                "Your edited ingredient list has been saved successfully.",
            )

            return redirect("fridge_scan_confirm", scan_id=fridge_scan.id)

        messages.error(
            request,
            "Please check the confirmed ingredient list and try again.",
        )

    else:
        form_prefill_items = (
            fridge_scan.confirmed_items
            if fridge_scan.confirmed_items
            else fridge_scan.detected_items
        )

        form = FridgeScanConfirmForm(
            detected_items=form_prefill_items,
        )

    context = {
        "form": form,
        "fridge_scan": fridge_scan,
        "detected_items": fridge_scan.detected_items,
        "confirmed_items": fridge_scan.confirmed_items,
    }

    return render(request, "recipes/fridge_scan_confirm.html", context)


@login_required
def fridge_scan_history_view(request):
    """
    Shows the user's previous refrigerator scans.
    """

    fridge_scans = FridgeScan.objects.filter(
        user=request.user,
    )

    context = {
        "fridge_scans": fridge_scans,
    }

    return render(request, "recipes/fridge_scan_history.html", context)


@login_required
@require_POST
def fridge_scan_delete_view(request, scan_id):
    """
    Deletes a user's fridge scan.

    Security:
    - Only the owner of the scan can delete it.
    - The uploaded image file is also removed from storage if it exists.
    """

    fridge_scan = get_object_or_404(
        FridgeScan,
        id=scan_id,
        user=request.user,
    )

    if fridge_scan.image:
        fridge_scan.image.delete(save=False)

    fridge_scan.delete()

    messages.success(
        request,
        "Fridge scan deleted successfully.",
    )

    return redirect("fridge_scan_history")