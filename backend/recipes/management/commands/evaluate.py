"""
Writes the evaluation report (Markdown) from what CulinaAI has stored. No AI calls.

    python manage.py evaluate                       # everyone's recipes and cooking sessions
    python manage.py evaluate --benchmark docs/evaluation/results/benchmark_2026-10-10_0930.jsonl
    python manage.py evaluate --study docs/evaluation/user_study/responses.csv
    python manage.py evaluate --since 2026-10-01 --exclude-user demo

The report goes to docs/evaluation/results/evaluation_<date>.md unless --out is given.
"""

import csv
import datetime
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from recipes.evaluation_service import build_report, history_row
from recipes.models import CookingSession, CookingStepRecord, RecipeHistory

from .run_benchmark import BENCHMARK_USER, RESULTS_DIR

PROJECT_ROOT = Path(settings.BASE_DIR).parent


def find_file(name):
    """A path as typed, or relative to the project root (so it works from backend/ too)."""
    for path in (Path(name), PROJECT_ROOT / name):
        if path.exists():
            return path
    raise CommandError(f"File not found: {name}")


def read_benchmark(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def read_study(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return [row for row in csv.DictReader(handle) if any((value or "").strip() for value in row.values())]


class Command(BaseCommand):
    help = "Writes the evaluation report from stored recipes, cooking sessions and study answers."

    def add_arguments(self, parser):
        parser.add_argument("--benchmark", default="", help="A benchmark_<time>.jsonl from run_benchmark.")
        parser.add_argument("--study", default="", help="User study answers (CSV, as responses_template.csv).")
        parser.add_argument("--since", default="", help="Only recipes and sessions from this date (YYYY-MM-DD).")
        parser.add_argument("--exclude-user", action="append", default=[],
                            help="Leave out a username (e.g. demo); can be given more than once.")
        parser.add_argument("--out", default="", help="Where to write the report.")

    def handle(self, *args, **options):
        now = timezone.localtime()
        since = None
        if options["since"]:
            try:
                since = datetime.date.fromisoformat(options["since"])
            except ValueError as error:
                raise CommandError("--since must look like 2026-10-01") from error

        benchmark_lines = None
        if options["benchmark"]:
            benchmark_path = find_file(options["benchmark"])
            benchmark_lines = read_benchmark(benchmark_path)
            ids = [line["history_id"] for line in benchmark_lines if line.get("history_id")]
            history = RecipeHistory.objects.filter(id__in=ids)
            sessions = None
            title = "CulinaAI benchmark evaluation"
            scope = f"Benchmark run {benchmark_path.name}: {len(benchmark_lines)} cases."
        else:
            history = RecipeHistory.objects.exclude(user__username=BENCHMARK_USER)
            sessions = CookingSession.objects.exclude(user__username=BENCHMARK_USER)
            if since:
                history = history.filter(created_at__date__gte=since)
                sessions = sessions.filter(started_at__date__gte=since)
            for username in options["exclude_user"]:
                history = history.exclude(user__username=username)
                sessions = sessions.exclude(user__username=username)
            title = "CulinaAI evaluation"
            scope = "Recipes and cooking sessions from real use" + (f" since {since}" if since else "") + (
                f", leaving out {', '.join(options['exclude_user'])}" if options["exclude_user"] else ""
            ) + " (benchmark recipes are not included)."

        rows = [history_row(entry) for entry in history]
        records = None
        if sessions is not None:
            sessions = list(sessions)
            records = list(CookingStepRecord.objects.filter(session__in=[session.id for session in sessions]))

        study_rows = read_study(find_file(options["study"])) if options["study"] else None

        report = build_report(
            title=title,
            scope=scope,
            rows=rows,
            sessions=sessions,
            records=records,
            benchmark_lines=benchmark_lines,
            study_rows=study_rows,
            generated_at=now.strftime("%d %B %Y, %H:%M"),
        )

        if options["out"]:
            out_path = Path(options["out"])
        else:
            RESULTS_DIR.mkdir(parents=True, exist_ok=True)
            kind = "benchmark_report" if benchmark_lines else "evaluation"
            out_path = RESULTS_DIR / f"{kind}_{now.strftime('%Y-%m-%d_%H%M')}.md"
        out_path.write_text(report, encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Report written to {out_path} ({len(rows)} recipes)."))
