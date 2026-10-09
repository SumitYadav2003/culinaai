"""
Runs the fixed benchmark recipes (docs/evaluation/benchmark_cases.json) through
the real generation pipeline: the same AI prompt, 10 quality gates, meal style
and cuisine retries, safe fallback and history as the website, with images off.

    python manage.py run_benchmark --yes             # all 30 cases
    python manage.py run_benchmark --yes --limit 3   # a quick try first
    python manage.py run_benchmark --yes --only thai-allergy,italian-everyday

This calls the OpenAI API and costs money (roughly 1p to 3p per recipe with
gpt-4.1-mini, more when a recipe is retried). It refuses to run without --yes.

The recipes are saved to RecipeHistory under the user "culinaai-benchmark",
and a list of what ran is written to docs/evaluation/results/benchmark_<time>.jsonl.
Then: python manage.py evaluate --benchmark docs/evaluation/results/benchmark_<time>.jsonl
"""

import json
import time
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.management.base import BaseCommand, CommandError
from django.test import RequestFactory, override_settings
from django.utils import timezone

from recipes.models import RecipeHistory
from recipes.views import run_recipe_generation

PROJECT_ROOT = Path(settings.BASE_DIR).parent
CASES_FILE = PROJECT_ROOT / "docs" / "evaluation" / "benchmark_cases.json"
RESULTS_DIR = PROJECT_ROOT / "docs" / "evaluation" / "results"
BENCHMARK_USER = "culinaai-benchmark"

# What the form sends when a field is left alone (generate_recipe_view).
DEFAULTS = {
    "cuisine": "Any cuisine",
    "meal_type": "Any meal type",
    "diet_preferences": [],
    "other_diet_preference": "",
    "allergies": "None provided",
    "cooking_time_minutes": 30,
    "servings": 2,
    "difficulty": "easy",
    "spice_level": "Medium",
    "budget_level": "Moderate Budget",
    "nutrition_goal": "Balanced",
    "meal_style": "No preference",
    "cooking_equipment": [],
    "other_kitchen_equipment": "",
    "utensils": [],
    "other_utensils": "",
    "additional_notes": "",
}


def load_cases(path=CASES_FILE):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)["cases"]


def preview_data_for(case):
    """The case as the form would have sent it."""
    data = dict(DEFAULTS)
    data.update({key: value for key, value in case.items() if key != "id"})
    return data


def benchmark_user():
    user, created = get_user_model().objects.get_or_create(username=BENCHMARK_USER)
    if created:
        user.set_unusable_password()
        user.save()
    return user


def fake_request(user):
    """A logged-in POST request with a session and messages, like the generate form's."""
    request = RequestFactory().post("/recipes/generate/")
    request.user = user
    SessionMiddleware(lambda req: None).process_request(request)
    request.session.save()
    request._messages = FallbackStorage(request)
    return request


def run_case(case, user):
    """Generates one case. Returns the line written to the results file."""
    request = fake_request(user)
    started = time.monotonic()
    with override_settings(CULINAAI_SKIP_IMAGES=True):
        run_recipe_generation(request, preview_data_for(case))
    seconds = round(time.monotonic() - started, 1)

    history_id = request.session.get("latest_recipe_history_id")
    entry = RecipeHistory.objects.filter(id=history_id).first() if history_id else None
    line = {"case": case["id"], "history_id": history_id, "seconds": seconds}
    if entry:
        line.update({
            "title": entry.title,
            "attempts": entry.validation_attempts,
            "score": entry.quality_score,
            "status": entry.validation_status,
        })
    else:
        line["problem"] = "no recipe was saved"
    return line


class Command(BaseCommand):
    help = "Runs the fixed benchmark recipes through the real pipeline (calls the OpenAI API; needs --yes)."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Confirm that the OpenAI API may be called.")
        parser.add_argument("--limit", type=int, default=0, help="Run only the first N cases.")
        parser.add_argument("--only", default="", help="Comma-separated case ids to run.")
        parser.add_argument("--cases", default=str(CASES_FILE), help="Cases file (default: the fixed 30).")

    def handle(self, *args, **options):
        cases = load_cases(options["cases"])
        if options["only"]:
            wanted = {item.strip() for item in options["only"].split(",") if item.strip()}
            unknown = wanted - {case["id"] for case in cases}
            if unknown:
                raise CommandError("Unknown case id(s): " + ", ".join(sorted(unknown)))
            cases = [case for case in cases if case["id"] in wanted]
        if options["limit"]:
            cases = cases[: options["limit"]]

        if not options["yes"]:
            raise CommandError(
                f"This would generate {len(cases)} recipes with the OpenAI API, which costs money. "
                "Run it again with --yes to go ahead."
            )
        if not getattr(settings, "OPENAI_API_KEY", ""):
            raise CommandError("OPENAI_API_KEY is not set, so every case would only get the safe fallback recipe.")

        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = timezone.localtime().strftime("%Y-%m-%d_%H%M")
        out_path = RESULTS_DIR / f"benchmark_{stamp}.jsonl"
        user = benchmark_user()

        self.stdout.write(f"Running {len(cases)} cases (images off). Results: {out_path}")
        with open(out_path, "w", encoding="utf-8") as out:
            for number, case in enumerate(cases, start=1):
                line = run_case(case, user)
                out.write(json.dumps(line) + "\n")
                out.flush()
                summary = line.get("problem") or (
                    f"{line['attempts']} attempt(s), score {line['score']}, {line['seconds']}s"
                )
                self.stdout.write(f"[{number}/{len(cases)}] {case['id']}: {summary}")

        try:
            shown = out_path.relative_to(PROJECT_ROOT)
        except ValueError:
            shown = out_path
        self.stdout.write(self.style.SUCCESS(f"Done. Next: python manage.py evaluate --benchmark {shown}"))
