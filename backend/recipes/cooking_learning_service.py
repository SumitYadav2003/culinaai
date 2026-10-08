"""
Learning from how the user cooks, part 1: recording and the cooking profile.

Cooking mode sends a small summary of each session (how long each step was
open, whether the timer was used, steps the user asked to hear again, the
"Had trouble?" choice, and how the dish turned out). This file checks and
saves it, and works out the "Your cooking profile" card on the dashboard.

Everything here is plain code. No AI call, and nothing the browser sends is
trusted as-is: step text comes from the recipe on the server, and every
number is clamped.
"""

from statistics import median

from django.db import transaction
from django.db.models import Count, Q, Sum

from .cooking_mode_service import build_cooking_mode_context
from .models import CookingSession, CookingSettings, CookingStepRecord

# Accents the hands-free voice can listen for (Web Speech API language tags).
ENGLISH_CHOICES = [
    ("en-GB", "English (UK)"),
    ("en-US", "English (US)"),
    ("en-IN", "English (India)"),
    ("en-AU", "English (Australia)"),
    ("en-IE", "English (Ireland)"),
    ("en-CA", "English (Canada)"),
    ("en-NZ", "English (New Zealand)"),
    ("en-ZA", "English (South Africa)"),
]
ENGLISH_CODES = {code for code, _ in ENGLISH_CHOICES}

MAX_STEP_SECONDS = 6 * 60 * 60  # a step left open overnight shouldn't count as hours of cooking
MAX_REPEATS = 50
MAX_NOTE_LENGTH = 300

# Which steps count towards "your pace": the step says how long it takes, the
# user stayed on it at least this long, and not absurdly longer than planned.
PACE_MIN_SECONDS = 30
PACE_MAX_RATIO = 4
PACE_MIN_STEPS = 3

TROUBLE_WORDS = dict(CookingStepRecord.TROUBLE_CHOICES)
OUTCOME_WORDS = dict(CookingSession.OUTCOME_CHOICES)


def get_settings(user):
    settings_row, _ = CookingSettings.objects.get_or_create(user=user)
    return settings_row


def to_int(value, low, high, default=0):
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def clean_note(value):
    """The cook's own words about a step: plain text, one line, at most 300 characters."""
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:MAX_NOTE_LENGTH]


def record_session(user, recipe, payload):
    """
    Save one snapshot of a cooking session. Cooking mode sends the whole
    session each time (not just what changed), so saving the same snapshot
    twice is harmless. Returns the session, or None if learning is off.
    """
    if not get_settings(user).learn_from_cooking:
        return None
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object.")

    steps = build_cooking_mode_context(recipe)["cooking_steps"]
    by_number = {step["number"]: step for step in steps}

    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list):
        raise ValueError("Expected a list of steps.")

    with transaction.atomic():
        session = None
        session_id = payload.get("session_id")
        if session_id:
            session = CookingSession.objects.filter(id=to_int(session_id, 0, 2**31 - 1), user=user, recipe=recipe).first()
        if session is None:
            session = CookingSession(user=user, recipe=recipe)

        session.recipe_title = recipe.title[:200]
        session.cuisine_name = recipe.cuisine.name[:120] if recipe.cuisine_id else ""
        session.steps_total = len(steps)
        session.voice_used = session.voice_used or bool(payload.get("voice_used"))
        if payload.get("outcome") in OUTCOME_WORDS:
            session.outcome = payload["outcome"]
        session.save()

        for item in raw_steps:
            if not isinstance(item, dict):
                continue
            number = to_int(item.get("number"), 0, 10_000)
            step = by_number.get(number)
            if step is None:
                continue  # a step that isn't in this recipe
            trouble = item.get("trouble") if item.get("trouble") in TROUBLE_WORDS else ""
            values = {
                "text": step["text"][:1000],
                "planned_minutes": to_int(step["timer_minutes"], 0, 32767),
                "timer_from_text": bool(step.get("timer_from_text")),
                "seconds_open": to_int(item.get("seconds"), 0, MAX_STEP_SECONDS),
                "timer_used": bool(item.get("timer_used")),
                "repeats": to_int(item.get("repeats"), 0, MAX_REPEATS),
                "trouble": trouble,
                "went_fine": bool(item.get("went_fine")) and not trouble,
                "note": clean_note(item.get("note")),
                "completed": bool(item.get("completed")),
            }
            CookingStepRecord.objects.update_or_create(session=session, number=number, defaults=values)

        # Totals from everything saved for this session, not just this snapshot.
        totals = session.steps.aggregate(seconds=Sum("seconds_open"), completed=Count("id", filter=Q(completed=True)))
        completed = totals["completed"] or 0
        session.steps_completed = completed
        session.active_seconds = totals["seconds"] or 0
        session.finished = bool(steps) and completed == len(steps)
        session.save(update_fields=["steps_completed", "active_seconds", "finished", "updated_at"])

    return session


def forget_history(user):
    """Delete every cooking session (and its steps) for this user. Returns how many sessions went."""
    sessions = CookingSession.objects.filter(user=user)
    count = sessions.count()
    sessions.delete()
    return count


# ---------------------------------------------------------------------------
# The dashboard's "Your cooking profile" card
# ---------------------------------------------------------------------------

def pace_ratio(records):
    """
    How long the user takes compared with the recipe, as a median ratio
    (1.3 = 30% longer). Only steps whose own text gives a time, that were
    completed, and stayed open a sensible length. None if fewer than 3.
    """
    ratios = []
    for record in records:
        planned = record.planned_minutes * 60
        if not (record.timer_from_text and record.completed and planned):
            continue
        if record.seconds_open < PACE_MIN_SECONDS or record.seconds_open > planned * PACE_MAX_RATIO + 600:
            continue
        ratios.append(record.seconds_open / planned)
    if len(ratios) < PACE_MIN_STEPS:
        return None, len(ratios)
    return round(median(ratios), 2), len(ratios)


def pace_words(ratio):
    if ratio is None:
        return ""
    if 0.85 <= ratio <= 1.15:
        return "About the same as the recipe times"
    percent = round(abs(ratio - 1) * 100 / 5) * 5
    return f"About {percent}% {'longer' if ratio > 1 else 'quicker'} than the recipe times"


def short_step(text, words=9):
    parts = str(text or "").split()
    return " ".join(parts[:words]) + ("…" if len(parts) > words else "")


def build_cooking_profile(user):
    """Plain values for the dashboard card. Works the same whether learning is on or off."""
    settings_row = get_settings(user)
    sessions = list(CookingSession.objects.filter(user=user, steps_completed__gte=1)[:200])
    records = list(
        CookingStepRecord.objects.filter(session__in=sessions).select_related("session").order_by("-session__started_at", "number")
    )

    ratio, paced_steps = pace_ratio(records)
    trouble_counts = {key: 0 for key in TROUBLE_WORDS}
    for record in records:
        if record.trouble:
            trouble_counts[record.trouble] += 1

    outcomes = {key: 0 for key in OUTCOME_WORDS}
    for session in sessions:
        if session.outcome:
            outcomes[session.outcome] += 1

    recent_trouble = [
        {
            "step": short_step(record.text),
            "number": record.number,
            "reason": TROUBLE_WORDS[record.trouble] if record.trouble else ("Went fine" if record.went_fine else "Your note"),
            "trouble": bool(record.trouble),
            "note": record.note,
            "recipe": record.session.recipe_title,
        }
        for record in records if record.trouble or record.note
    ][:4]

    repeated = sum(1 for record in records if record.repeats >= 2)
    top_trouble = max(trouble_counts.items(), key=lambda pair: pair[1])

    return {
        "learning": settings_row.learn_from_cooking,
        "cooked": len(sessions),
        "finished": sum(1 for session in sessions if session.finished),
        "voice_sessions": sum(1 for session in sessions if session.voice_used),
        "steps": len(records),
        "pace": {"ratio": ratio, "words": pace_words(ratio), "steps": paced_steps, "needed": PACE_MIN_STEPS},
        "trouble": [
            {"reason": TROUBLE_WORDS[key], "count": count} for key, count in trouble_counts.items()
        ],
        "trouble_total": sum(trouble_counts.values()),
        "top_trouble": TROUBLE_WORDS[top_trouble[0]] if top_trouble[1] else "",
        "recent_trouble": recent_trouble,
        "repeated_steps": repeated,
        "went_fine": sum(1 for record in records if record.went_fine),
        "notes": sum(1 for record in records if record.note),
        "outcomes": [{"key": key, "label": OUTCOME_WORDS[key], "count": outcomes[key]} for key in OUTCOME_WORDS],
        "rated": sum(outcomes.values()),
    }
