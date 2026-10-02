"""
Tests for the nutrition engine.

The foods below are TEST DATA with round numbers so every expected value can
be worked out by hand. They are not real CoFID values.
"""

import csv
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from nutrition.models import CofidFood, IngredientAlias
from nutrition.services import (
    IngredientInput,
    calculate_nutrition,
    find_by_words,
    load_foods_for_matching,
    normalise_name,
    nutrition_claims,
    singular,
    traffic_light,
)


def make_food(code, name, **values):
    defaults = dict(
        energy_kcal=0, energy_kj=0, protein_g=0, fat_g=0, saturates_g=0,
        carbohydrate_g=0, sugars_g=0, fibre_g=0, salt_g=0,
    )
    defaults.update(values)
    return CofidFood.objects.create(food_code=code, name=name, **defaults)


class WordHelperTests(TestCase):
    def test_singular(self):
        self.assertEqual(singular("tomatoes"), "tomato")
        self.assertEqual(singular("onions"), "onion")
        self.assertEqual(singular("berries"), "berry")
        self.assertEqual(singular("grass"), "grass")
        self.assertEqual(singular("peas"), "pea")

    def test_normalise_name(self):
        self.assertEqual(normalise_name("  Red Onions "), "red onion")


class LoadCofidCommandTests(TestCase):
    def write_csv(self, rows):
        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="", encoding="utf-8")
        writer = csv.DictWriter(handle, fieldnames=[
            "food_code", "name", "food_group", "energy_kcal", "energy_kj", "protein_g", "fat_g",
            "saturates_g", "carbohydrate_g", "sugars_g", "fibre_g", "salt_g",
        ])
        writer.writeheader()
        writer.writerows(rows)
        handle.close()
        return Path(handle.name)

    def test_loads_rows_and_keeps_missing_values_empty(self):
        path = self.write_csv([
            {"food_code": "T1", "name": "Test food, raw", "energy_kcal": "100", "protein_g": "", "salt_g": "0.5"},
        ])
        call_command("load_cofid", file=str(path), stdout=open("/dev/null", "w"))
        food = CofidFood.objects.get(food_code="T1")
        self.assertEqual(food.energy_kcal, 100)
        self.assertIsNone(food.protein_g)
        self.assertEqual(food.salt_g, 0.5)

    def test_running_twice_does_not_duplicate(self):
        path = self.write_csv([{"food_code": "T1", "name": "Test food", "energy_kcal": "100"}])
        call_command("load_cofid", file=str(path), stdout=open("/dev/null", "w"))
        call_command("load_cofid", file=str(path), stdout=open("/dev/null", "w"))
        self.assertEqual(CofidFood.objects.filter(food_code="T1").count(), 1)

    def test_rows_without_code_are_skipped(self):
        path = self.write_csv([{"food_code": "", "name": "No code"}])
        call_command("load_cofid", file=str(path), stdout=open("/dev/null", "w"))
        self.assertEqual(CofidFood.objects.count(), 0)


class MatchingTests(TestCase):
    def setUp(self):
        self.raw = make_food("C1", "Chicken, breast, raw")
        self.grilled = make_food("C2", "Chicken, breast, grilled, without skin")
        self.onion = make_food("O1", "Onions, raw")

    def test_every_word_must_appear(self):
        foods = load_foods_for_matching()
        self.assertEqual(find_by_words("chicken breast", foods), self.raw)
        self.assertIsNone(find_by_words("chicken thigh", foods))

    def test_prefers_raw_unless_recipe_says_cooked(self):
        foods = load_foods_for_matching()
        self.assertEqual(find_by_words("chicken breast", foods), self.raw)
        self.assertEqual(find_by_words("grilled chicken breast", foods), self.grilled)

    def test_plurals_match(self):
        foods = load_foods_for_matching()
        self.assertEqual(find_by_words("onion", foods), self.onion)

    def test_alias_wins_over_word_match(self):
        IngredientAlias.objects.create(alias="chicken breast", food=self.grilled)
        result = calculate_nutrition([IngredientInput("Chicken Breast", 100)], servings=1)
        self.assertEqual(result.matched[0].food_code, "C2")
        self.assertEqual(result.matched[0].method, "alias")

    def test_unknown_ingredient_is_listed_not_guessed(self):
        result = calculate_nutrition([IngredientInput("dragon fruit", 50)], servings=1)
        self.assertEqual(result.unmatched, ["dragon fruit"])
        self.assertEqual(result.matched, [])


class CalculationTests(TestCase):
    def setUp(self):
        # 100 g of each: chicken 100 kcal / 20 g protein; rice 300 kcal / 70 g carbs; oil 900 kcal / 100 g fat.
        make_food("C1", "Chicken, breast, raw", energy_kcal=100, energy_kj=420, protein_g=20, fat_g=2, saturates_g=0.5, salt_g=0.2)
        make_food("R1", "Rice, white, raw", energy_kcal=300, energy_kj=1260, protein_g=7, carbohydrate_g=70, fibre_g=1)
        make_food("V1", "Oil, vegetable", energy_kcal=900, energy_kj=3700, fat_g=100, saturates_g=10)

    def test_hand_worked_recipe(self):
        # 300 g chicken + 200 g rice + 10 g oil, 2 servings.
        result = calculate_nutrition([
            IngredientInput("chicken breast", 300),
            IngredientInput("white rice", 200),
            IngredientInput("vegetable oil", 10),
        ], servings=2)

        # Energy: 300 + 600 + 90 = 990 kcal in total, 495 per serving.
        self.assertEqual(result.totals["energy_kcal"], 990)
        self.assertEqual(result.per_serving["energy_kcal"], 495)
        # Protein: 60 + 14 = 74 g total, 37 per serving.
        self.assertEqual(result.per_serving["protein_g"], 37)
        # Fat: 6 + 0 + 10 = 16 g; per 100 g of 510 g dish = 3.14 g.
        self.assertAlmostEqual(result.per_100g["fat_g"], 3.14, places=2)
        self.assertEqual(result.coverage_pct, 100.0)
        self.assertTrue(result.is_complete)
        # 495 kcal is 25% of the 2000 kcal reference intake.
        self.assertEqual(result.percent_reference_intake["energy_kcal"], 25)

    def test_coverage_counts_unmatched_weight(self):
        result = calculate_nutrition([
            IngredientInput("chicken breast", 100),
            IngredientInput("mystery sauce", 100),
        ], servings=1)
        self.assertEqual(result.coverage_pct, 50.0)
        self.assertFalse(result.is_complete)
        # Per 100 g uses matched weight only, so the unknown sauce doesn't dilute it.
        self.assertEqual(result.per_100g["energy_kcal"], 100)

    def test_zero_servings_treated_as_one(self):
        result = calculate_nutrition([IngredientInput("chicken breast", 100)], servings=0)
        self.assertEqual(result.servings, 1)


class TrafficLightTests(TestCase):
    def test_fat_boundaries(self):
        self.assertEqual(traffic_light("fat_g", 3.0, 1, 50), "green")
        self.assertEqual(traffic_light("fat_g", 3.01, 1, 50), "amber")
        self.assertEqual(traffic_light("fat_g", 17.5, 1, 50), "amber")
        self.assertEqual(traffic_light("fat_g", 17.51, 1, 50), "red")

    def test_salt_boundaries(self):
        self.assertEqual(traffic_light("salt_g", 0.3, 0.1, 50), "green")
        self.assertEqual(traffic_light("salt_g", 1.5, 0.1, 50), "amber")
        self.assertEqual(traffic_light("salt_g", 1.51, 0.1, 50), "red")

    def test_large_portion_red_rule(self):
        # Amber per 100 g, but a 400 g portion with 22 g fat is red (over 21 g per portion).
        self.assertEqual(traffic_light("fat_g", 5.5, 22, 400), "red")
        # The portion rule doesn't apply to portions of 100 g or less.
        self.assertEqual(traffic_light("fat_g", 5.5, 22, 100), "amber")


class ClaimTests(TestCase):
    def per_100g(self, **values):
        base = dict(energy_kcal=200, protein_g=0, fat_g=10, saturates_g=5, sugars_g=10, fibre_g=0, salt_g=1)
        base.update(values)
        return base

    def test_protein_claims_by_share_of_energy(self):
        # 200 kcal: 12% = 6 g protein, 20% = 10 g protein.
        self.assertNotIn("Source of protein", nutrition_claims(self.per_100g(protein_g=5.9)))
        self.assertIn("Source of protein", nutrition_claims(self.per_100g(protein_g=6)))
        self.assertIn("High protein", nutrition_claims(self.per_100g(protein_g=10)))
        self.assertNotIn("Source of protein", nutrition_claims(self.per_100g(protein_g=10)))

    def test_fibre_claims(self):
        self.assertIn("Source of fibre", nutrition_claims(self.per_100g(fibre_g=3)))
        self.assertIn("High fibre", nutrition_claims(self.per_100g(fibre_g=6)))

    def test_low_claims(self):
        claims = nutrition_claims(self.per_100g(fat_g=3, saturates_g=1.5, sugars_g=5, salt_g=0.3, energy_kcal=200))
        for claim in ("Low fat", "Low saturated fat", "Low sugars", "Low salt"):
            self.assertIn(claim, claims)

    def test_low_saturates_also_needs_energy_share(self):
        # 1.5 g saturates = 13.5 kcal; in a 100 kcal food that's 13.5% of energy, so no claim.
        self.assertNotIn("Low saturated fat", nutrition_claims(self.per_100g(saturates_g=1.5, energy_kcal=100)))


class CarbonTests(TestCase):
    """Round-number carbon categories, so every figure can be checked by hand."""

    @classmethod
    def setUpTestData(cls):
        from nutrition.models import CarbonCategory

        beef = CarbonCategory.objects.create(name="Test beef", kg_co2e_per_kg=100.0)
        pulses = CarbonCategory.objects.create(name="Test pulses", kg_co2e_per_kg=2.0)
        make_food("T-1", "Beef, mince, raw", carbon_category=beef)
        make_food("T-2", "Lentils, red, raw", carbon_category=pulses)
        make_food("T-3", "Butter, salted")  # no carbon category on purpose
        make_food("17-377", "Water, distilled")  # code the engine treats as negligible

    def test_carbon_per_serving(self):
        # 200 g beef = 20 kg, 300 g lentils = 0.6 kg -> 20.6 kg for 2 servings
        result = calculate_nutrition([IngredientInput("beef mince", 200), IngredientInput("red lentils", 300)], 2)
        self.assertAlmostEqual(result.carbon_kg_total, 20.6)
        self.assertAlmostEqual(result.carbon_kg_per_serving, 10.3)
        self.assertEqual(result.carbon_coverage_pct, 100.0)

    def test_food_without_category_is_reported_not_guessed(self):
        result = calculate_nutrition([IngredientInput("red lentils", 300), IngredientInput("butter", 100)], 1)
        self.assertAlmostEqual(result.carbon_kg_total, 0.6)
        self.assertEqual(result.carbon_unmatched, ["butter"])
        self.assertEqual(result.carbon_coverage_pct, 75.0)
        self.assertIsNone(result.matched[1].carbon_kg)

    def test_water_counts_as_zero_and_covered(self):
        result = calculate_nutrition([IngredientInput("red lentils", 100), IngredientInput("water", 900)], 1)
        self.assertAlmostEqual(result.carbon_kg_total, 0.2)
        self.assertEqual(result.carbon_coverage_pct, 100.0)
        self.assertEqual(result.carbon_unmatched, [])
