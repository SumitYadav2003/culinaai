"""
Load all nutrition data in the right order:

    python manage.py load_food_data

1. CoFID 2021 foods (UK government)
2. USDA foods for common ingredients CoFID doesn't cover
3. Hand-checked ingredient aliases
4. Carbon footprints (Poore & Nemecek 2018) and which foods they apply to

Safe to run again: everything is updated, nothing is duplicated.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand

from nutrition.management.commands.load_cofid import DATA_DIR
from nutrition.models import CofidFood


class Command(BaseCommand):
    help = "Load CoFID foods, the USDA supplement, ingredient aliases and carbon data."

    def handle(self, *args, **options):
        call_command("load_cofid", stdout=self.stdout)
        call_command(
            "load_cofid",
            file=str(DATA_DIR / "usda_supplement.csv"),
            source=CofidFood.SOURCE_USDA,
            stdout=self.stdout,
        )
        call_command("load_ingredient_aliases", stdout=self.stdout)
        call_command("load_carbon", stdout=self.stdout)
