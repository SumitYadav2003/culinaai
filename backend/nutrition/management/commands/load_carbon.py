"""
Load the carbon footprint data:

    python manage.py load_carbon

1. carbon_poore_nemecek_2018.csv: kg CO2e per kg for 43 food categories
2. carbon_food_map.csv: which category each CoFID food counts as

Run after `load_cofid` (the map points at CoFID food codes). Safe to run again.
"""

import csv

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nutrition.management.commands.load_cofid import DATA_DIR
from nutrition.models import CarbonCategory, CofidFood

STAGES = ["land_use_change", "farm", "animal_feed", "processing", "transport", "retail", "packaging", "losses"]


class Command(BaseCommand):
    help = "Load Poore & Nemecek (2018) carbon categories and link CoFID foods to them."

    def handle(self, *args, **options):
        with transaction.atomic():
            categories = self.load_categories()
            linked, missing = self.link_foods(categories)

        self.stdout.write(self.style.SUCCESS(f"Carbon categories: {len(categories)}. Foods linked: {linked}."))
        if missing:
            self.stdout.write(self.style.WARNING("Skipped: " + "; ".join(missing)))

    def load_categories(self):
        categories = {}
        with (DATA_DIR / "carbon_poore_nemecek_2018.csv").open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                values = {stage: float(row[stage]) for stage in STAGES}
                values["kg_co2e_per_kg"] = float(row["kg_co2e_per_kg"])
                category, _ = CarbonCategory.objects.update_or_create(name=row["category"], defaults=values)
                categories[category.name] = category
        return categories

    def link_foods(self, categories):
        foods = {food.food_code: food for food in CofidFood.objects.all()}
        if not foods:
            raise CommandError("No foods in the database. Run `python manage.py load_cofid` first.")

        # Start clean, so a food taken out of the map doesn't keep an old category.
        CofidFood.objects.update(carbon_category=None, carbon_note="")
        linked, missing = 0, []
        with (DATA_DIR / "carbon_food_map.csv").open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                food = foods.get(row["food_code"])
                category = categories.get(row["carbon_category"])
                if food is None or category is None:
                    missing.append(f"{row['food_code']} -> {row['carbon_category']}")
                    continue
                food.carbon_category = category
                food.carbon_note = row["notes"].strip()
                food.save(update_fields=["carbon_category", "carbon_note"])
                linked += 1
        return linked, missing
