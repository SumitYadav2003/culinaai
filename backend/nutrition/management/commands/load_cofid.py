"""
Load foods from a cleaned CSV into the database.

    python manage.py load_cofid                      # CoFID 2021 (default file)
    python manage.py load_cofid --file data/usda_supplement.csv --source "USDA FoodData Central"

The CoFID CSV is created from the official Excel file by scripts/extract_cofid.py.
Running this command again updates existing foods instead of duplicating them.
To load everything (CoFID, USDA supplement, aliases) in one go, use `load_food_data`.
"""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nutrition.models import CofidFood
from nutrition.services import NUTRIENTS

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DEFAULT_CSV = DATA_DIR / "cofid_2021.csv"


def to_number(value):
    """'12.5' -> 12.5, '' -> None (not measured)."""
    value = (value or "").strip()
    return float(value) if value else None


class Command(BaseCommand):
    help = "Load foods (CoFID 2021 by default) from a cleaned CSV into the database."

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(DEFAULT_CSV), help="Path to the cleaned food CSV.")
        parser.add_argument("--source", default=CofidFood.SOURCE_COFID, help="Where these values come from.")

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

                values = {
                    "name": name,
                    "food_group": (row.get("food_group") or "").strip(),
                    "source": options["source"],
                }
                values.update({n: to_number(row.get(n)) for n in NUTRIENTS})

                _, was_created = CofidFood.objects.update_or_create(food_code=code, defaults=values)
                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"{options['source']}: {created} created, {updated} updated, {skipped} skipped. "
            f"Total foods: {CofidFood.objects.count()}."
        ))
