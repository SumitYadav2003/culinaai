"""
Load ingredient prices (pounds per kg) onto the foods:

    python manage.py load_prices

Reads data/ingredient_prices.csv, which is exported from the price workbook by
scripts/export_prices.py. Run after `load_cofid`. Safe to run again.
"""

import csv

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nutrition.management.commands.load_cofid import DATA_DIR
from nutrition.models import CofidFood


class Command(BaseCommand):
    help = "Load ingredient prices per kg (ONS averages and UK supermarket averages)."

    def handle(self, *args, **options):
        foods = {food.food_code: food for food in CofidFood.objects.all()}
        if not foods:
            raise CommandError("No foods in the database. Run `python manage.py load_cofid` first.")

        priced, no_price, missing = 0, 0, []
        with (DATA_DIR / "ingredient_prices.csv").open(encoding="utf-8", newline="") as handle, transaction.atomic():
            # Start clean, so a food taken out of the CSV doesn't keep an old price.
            CofidFood.objects.update(price_per_kg_gbp=None, price_source="", price_note="")
            for row in csv.DictReader(handle):
                food = foods.get(row["food_code"])
                if food is None:
                    missing.append(row["food_code"])
                    continue
                price = row["price_per_kg_gbp"].strip()
                food.price_per_kg_gbp = float(price) if price else None
                food.price_source = row["source"].strip()
                food.price_note = row["note"].strip()[:255]
                food.save(update_fields=["price_per_kg_gbp", "price_source", "price_note"])
                if price:
                    priced += 1
                else:
                    no_price += 1

        self.stdout.write(self.style.SUCCESS(f"Prices loaded: {priced}. Listed without a price: {no_price}."))
        if missing:
            self.stdout.write(self.style.WARNING("Skipped, food code not found: " + ", ".join(missing)))
