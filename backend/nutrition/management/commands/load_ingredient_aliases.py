"""
Load the hand-checked ingredient aliases (everyday name -> CoFID food).

    python manage.py load_ingredient_aliases

Run `load_cofid` first, because every alias points at a CoFID food code.
Running it again updates existing aliases instead of duplicating them.
"""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nutrition.models import CofidFood, IngredientAlias

DEFAULT_CSV = Path(__file__).resolve().parents[2] / "data" / "ingredient_aliases.csv"


class Command(BaseCommand):
    help = "Load hand-checked ingredient aliases that link everyday names to CoFID foods."

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(DEFAULT_CSV))

    def handle(self, *args, **options):
        path = Path(options["file"])
        if not path.exists():
            raise CommandError(f"CSV not found: {path}")

        foods = {food.food_code: food for food in CofidFood.objects.all()}
        if not foods:
            raise CommandError("No CoFID foods in the database. Run `python manage.py load_cofid` first.")

        saved, missing_codes = 0, []
        with path.open(encoding="utf-8", newline="") as handle, transaction.atomic():
            for row in csv.DictReader(handle):
                alias = row["alias"].strip().lower()
                food = foods.get(row["food_code"].strip())
                if food is None:
                    missing_codes.append(f"{alias} -> {row['food_code']}")
                    continue
                IngredientAlias.objects.update_or_create(
                    alias=alias, defaults={"food": food, "notes": (row.get("notes") or "").strip()}
                )
                saved += 1

        self.stdout.write(self.style.SUCCESS(f"Aliases loaded: {saved}. Total aliases: {IngredientAlias.objects.count()}."))
        if missing_codes:
            self.stdout.write(self.style.WARNING("Skipped, food code not found: " + "; ".join(missing_codes)))
