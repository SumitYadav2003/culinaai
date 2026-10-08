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

import re
from statistics import median

from django.db import transaction
from django.db.models import Count, Q, Sum

from .cooking_mode_service import build_cooking_mode_context, step_kind
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
        session.timers_adjusted = bool(payload.get("timers_adjusted"))
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
# Your pace
# ---------------------------------------------------------------------------

SESSION_PACE_MIN = 2  # finished dishes needed when there aren't enough timed steps
ADJUST_MIN, ADJUST_MAX = 0.75, 1.6  # never squeeze or stretch a timer more than this
NO_CHANGE = (0.9, 1.1)  # within 10% of the recipe: leave timers alone


def step_pace(records):
    """
    Ratios of time taken to time written, from completed steps whose own text
    gives a time. Waiting steps (bake, simmer, rest...) are left out: the oven
    doesn't go faster for a quicker cook. Steps left open for absurdly long, or
    clicked past in under 30 seconds, are left out too.
    """
    ratios = []
    for record in records:
        planned = record.planned_minutes * 60
        if not (record.timer_from_text and record.completed and planned):
            continue
        if step_kind(record.text) == "waiting":
            continue
        if record.seconds_open < PACE_MIN_SECONDS or record.seconds_open > planned * PACE_MAX_RATIO + 600:
            continue
        ratios.append(record.seconds_open / planned)
    return ratios


def finished_sessions(user):
    """Finished cooking sessions with the total of their step timers (as written in the recipe)."""
    return list(
        CookingSession.objects.filter(user=user, finished=True)
        .annotate(planned_minutes=Sum("steps__planned_minutes"))[:60]
    )


def session_pace(sessions):
    """Whole finished dishes: time in cooking mode against the recipe's own step times."""
    ratios = []
    for session in sessions:
        minutes = getattr(session, "planned_minutes", None) or 0
        if not (session.finished and minutes) or session.active_seconds < 120:
            continue
        ratio = session.active_seconds / (minutes * 60)
        if 0.25 <= ratio <= PACE_MAX_RATIO:
            ratios.append(ratio)
    return ratios


def pace_for(records, sessions):
    """
    The cook's pace as {"ratio", "source", "count"}, or None if there isn't
    enough history. Timed steps are used when there are at least 3; otherwise
    at least 2 finished dishes.
    """
    ratios = step_pace(records)
    if len(ratios) >= PACE_MIN_STEPS:
        return {"ratio": round(median(ratios), 2), "source": "steps", "count": len(ratios)}
    dishes = session_pace(sessions)
    if len(dishes) >= SESSION_PACE_MIN:
        return {"ratio": round(median(dishes), 2), "source": "dishes", "count": len(dishes)}
    return None


def user_pace(user):
    records = CookingStepRecord.objects.filter(session__user=user, completed=True).order_by("-session__started_at")[:300]
    return pace_for(list(records), finished_sessions(user))


def pace_words(ratio):
    if ratio is None:
        return ""
    if NO_CHANGE[0] <= ratio <= NO_CHANGE[1]:
        return "About the same as the recipe times"
    percent = round(abs(ratio - 1) * 100 / 5) * 5
    return f"About {percent}% {'longer' if ratio > 1 else 'quicker'} than the recipe times"


def timer_adjustment(user):
    """
    How much to scale hands-on step timers in cooking mode for this cook, or
    None (learning off, not enough history, or pace within 10% of the recipe).
    """
    if not get_settings(user).learn_from_cooking:
        return None
    pace = user_pace(user)
    if not pace:
        return None
    applied = round(min(ADJUST_MAX, max(ADJUST_MIN, pace["ratio"])), 2)
    if NO_CHANGE[0] <= applied <= NO_CHANGE[1]:
        return None
    percent = round(abs(applied - 1) * 100 / 5) * 5
    return dict(pace, applied=applied, percent=percent, longer=applied > 1)


def join_words(items):
    """"a", "a and b", "a, b and c"."""
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def short_step(text, words=9):
    parts = str(text or "").split()
    return " ".join(parts[:words]) + ("…" if len(parts) > words else "")


# ---------------------------------------------------------------------------
# Tips for new recipes, from the cook's history
# ---------------------------------------------------------------------------

TIPS_MIN_STEPS = 6  # completed or answered steps needed before recipes are adjusted
TIPS_MIN_REPORTS = 2  # the same problem at least twice, so one bad day doesn't count


def quoted_note(text, limit=80):
    """The cook's own words, made safe to quote inside a prompt: one line, no quotes."""
    cleaned = " ".join(str(text or "").replace('"', "").replace("“", "").replace("”", "").split())
    return cleaned[:limit].rstrip()


def build_cooking_tips(user):
    """
    What the next recipe should do differently for this cook, worked out by
    code from their cooking history. Returns None, or:
        {"lines": [...] for the AI prompt, "reasons": [...] for the page, "examples": [...]}
    The AI writes the wording; these lines only change how the method is explained.
    """
    if not get_settings(user).learn_from_cooking:
        return None

    records = list(
        CookingStepRecord.objects.filter(session__user=user)
        .filter(Q(completed=True) | ~Q(trouble="") | Q(went_fine=True))
        .order_by("-session__started_at", "number")[:80]
    )
    if len(records) < TIPS_MIN_STEPS:
        return None

    technique = [r for r in records if r.trouble == CookingStepRecord.TROUBLE_TECHNIQUE]
    unclear = [r for r in records if r.trouble == CookingStepRecord.TROUBLE_UNCLEAR]
    longer = [r for r in records if r.trouble == CookingStepRecord.TROUBLE_LONGER]
    repeated = [r for r in records if r.repeats >= 2]
    pace = pace_for(records, finished_sessions(user))

    lines, reasons, examples = [], [], []

    if len(technique) >= TIPS_MIN_REPORTS:
        for record in technique[:3]:
            examples.append(quoted_note(record.note) if record.note else quoted_note(short_step(record.text, 8)))
        quoted = "; ".join(f'"{example}"' for example in examples)
        lines.append(
            f"This cook has found these steps tricky before: {quoted}. When this recipe uses a similar "
            "technique, explain how to do it in one extra sentence, and how to tell it is done right, at the "
            "end of that same numbered step, starting with 'Tip:'."
        )
        reasons.append("extra help with techniques you've found tricky")

    if len(unclear) + len(repeated) >= TIPS_MIN_REPORTS:
        lines.append(
            "Steps have sometimes been unclear to this cook. Keep one main action per numbered step, name the "
            "pan size and heat level, and say what the food should look like when the step is done."
        )
        reasons.append("clearer step wording")

    if len(longer) >= TIPS_MIN_REPORTS or (pace and pace["ratio"] >= 1.2):
        lines.append(
            "This cook usually takes longer than recipe times on hands-on work. Keep the total time realistic "
            "for a home cook, and start the method by getting ingredients chopped and measured."
        )
        reasons.append("realistic prep times")

    if not lines:
        return None
    return {"lines": lines, "reasons": reasons, "examples": examples}


STEPS_SECTION = re.compile(r"STEPS:\s*(.*?)(?:\n[A-Z][A-Z &/]+:\s*\n|\Z)", re.DOTALL)
TIP_LINE = re.compile(r"\bTip:", re.IGNORECASE)


def personal_insight(cooking_tips, recipe_text):
    """
    The "Adjusted for you" note for a recipe: what CulinaAI asked for, and how
    many "Tip:" lines actually came back in the method (counted by code).
    """
    if not cooking_tips:
        return None
    match = STEPS_SECTION.search(recipe_text or "")
    steps_text = match.group(1) if match else ""
    return {
        "reasons": cooking_tips.get("reasons", []),
        "summary": join_words(cooking_tips.get("reasons", [])),
        "examples": cooking_tips.get("examples", []),
        "tips_found": len(TIP_LINE.findall(steps_text)),
    }


# ---------------------------------------------------------------------------
# The dashboard's "Your cooking profile" card
# ---------------------------------------------------------------------------

def build_cooking_profile(user):
    """Plain values for the dashboard card. Works the same whether learning is on or off."""
    settings_row = get_settings(user)
    sessions = list(CookingSession.objects.filter(user=user, steps_completed__gte=1)[:200])
    records = list(
        CookingStepRecord.objects.filter(session__in=sessions).select_related("session").order_by("-session__started_at", "number")
    )

    pace = pace_for([r for r in records if r.completed], finished_sessions(user))
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

    # What CulinaAI currently does with this (nothing while learning is off).
    adjustment = timer_adjustment(user)
    tips = build_cooking_tips(user)
    using = []
    if adjustment:
        using.append(
            f"Hands-on step timers get {adjustment['percent']}% {'more' if adjustment['longer'] else 'less'} time "
            "in cooking mode. Oven, simmering and resting times stay as the recipe says."
        )
    if tips:
        using.append("New recipes are written with " + join_words(tips["reasons"]) + ".")

    return {
        "learning": settings_row.learn_from_cooking,
        "cooked": len(sessions),
        "finished": sum(1 for session in sessions if session.finished),
        "voice_sessions": sum(1 for session in sessions if session.voice_used),
        "steps": len(records),
        "pace": {
            "ratio": pace["ratio"] if pace else None,
            "words": pace_words(pace["ratio"]) if pace else "",
            "source": pace["source"] if pace else "",
            "count": pace["count"] if pace else len(step_pace(records)),
            "needed": PACE_MIN_STEPS,
        },
        "using": using,
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
