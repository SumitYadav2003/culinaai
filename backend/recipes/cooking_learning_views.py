"""
Endpoints for learning from how the user cooks (cooking_learning_service.py).

- record:   cooking mode sends a snapshot of the session (JSON, or a form field
            "payload" when the page is closing and the browser uses sendBeacon)
- settings: learning on/off and the voice's English
- forget:   delete the user's cooking history
"""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .cooking_learning_service import ENGLISH_CODES, forget_history, get_settings, record_session
from .models import Recipe

MAX_PAYLOAD_BYTES = 64 * 1024


def wants_json(request):
    return request.headers.get("x-requested-with") == "fetch" or "application/json" in request.headers.get("accept", "")


def back_to(request, fallback="dashboard"):
    target = request.POST.get("next") or ""
    if url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(target)
    return redirect(fallback)


@login_required
@require_POST
def cooking_record_view(request, recipe_id):
    recipe = get_object_or_404(Recipe.objects.select_related("cuisine"), id=recipe_id, user=request.user, is_saved=True)

    raw = request.POST.get("payload") if request.POST.get("payload") else request.body
    if not raw or len(raw) > MAX_PAYLOAD_BYTES:
        return JsonResponse({"saved": False, "error": "Empty or too large."}, status=400)
    try:
        payload = json.loads(raw)
        session = record_session(request.user, recipe, payload)
    except (ValueError, TypeError):
        return JsonResponse({"saved": False, "error": "Could not read the cooking data."}, status=400)

    if session is None:
        return JsonResponse({"saved": False, "learning": False})
    return JsonResponse({"saved": True, "session_id": session.id})


@login_required
@require_POST
def cooking_settings_view(request):
    settings_row = get_settings(request.user)
    changed = []

    learn = request.POST.get("learn")
    if learn in ("on", "off"):
        settings_row.learn_from_cooking = learn == "on"
        changed.append("learn_from_cooking")

    english = request.POST.get("english")
    if english in ENGLISH_CODES:
        settings_row.english = english
        changed.append("english")

    if changed:
        settings_row.save(update_fields=changed + ["updated_at"])

    if wants_json(request):
        return JsonResponse({"learning": settings_row.learn_from_cooking, "english": settings_row.english})

    if "learn_from_cooking" in changed:
        messages.success(
            request,
            "Learning from your cooking is on." if settings_row.learn_from_cooking
            else "Learning from your cooking is off. Nothing new will be recorded.",
        )
    return back_to(request)


@login_required
@require_POST
def cooking_forget_view(request):
    count = forget_history(request.user)

    if wants_json(request):
        return JsonResponse({"deleted": count})

    messages.success(request, f"Deleted your cooking history ({count} session{'s' if count != 1 else ''}).")
    return back_to(request)
