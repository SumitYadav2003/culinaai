"""
Load CoFID foods from the cleaned CSV into the database.

    python manage.py load_cofid
    python manage.py load_cofid --file path/to/cofid_2021.csv

The CSV is created from the official Excel file by scripts/extract_cofid.py.
Running this command again updates existing foods instead of duplicating them.
"""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nutrition.models import CofidFood
from nutrition.services import NUTRIENTS

DEFAULT_CSV = Path(__file__).resolve().parents[2] / "data" / "cofid_2021.csv"


def to_number(value):
    """'12.5' -> 12.5, '' -> None (not measured)."""
    value = (value or "").strip()
    return float(value) if value else None


class Command(BaseCommand):
    help = "Load CoFID 2021 foods from the cleaned CSV into the database."

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(DEFAULT_CSV), help="Path to the cleaned CoFID CSV.")

    def handle(self, *args, **options):
        path = Path(options["file"])
        if not path.exists():
            raise CommandError(f"CSV not found: {path}. Run scripts/extract_cofid.py first.")

        created = updated = skipped = 0
        with path.open(encoding="utf-8", newline="") as handle, transaction.atomic():
            for row in csv.DictReader(handle):
                code = (row.get("food_code") or "").strip()
                name = (row.get("name") or "").strip()
                if not code or not name:
                    skipped += 1
                    continue

                values = {"name": name, "food_group": (row.get("food_group") or "").strip()}
                values.update({n: to_number(row.get(n)) for n in NUTRIENTS})

                _, was_created = CofidFood.objects.update_or_create(food_code=code, defaults=values)
                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"CoFID load finished: {created} created, {updated} updated, {skipped} skipped. "
            f"Total foods: {CofidFood.objects.count()}."
        ))
