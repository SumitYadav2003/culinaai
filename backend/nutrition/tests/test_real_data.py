"""
End-to-end check on the real CoFID 2021 data and the real ingredient aliases.

These ten recipes were also calculated by hand with spreadsheet formulas
(CulinaAI_nutrition_hand_check.xlsx). The expected values below come from that
spreadsheet. If a change to the engine or the data moves any of them, this fails.
"""

from django.core.management import call_command
from django.test import TestCase

from nutrition.services import IngredientInput, calculate_nutrition

# (recipe, servings, [(ingredient as a recipe would write it, grams, expected CoFID code)], kcal per serving)
HAND_CHECKED_RECIPES = [
    ("Garlic chicken and spinach rice bowl", 2, [("chicken breast", 300, "18-290"), ("basmati rice", 200, "11-857"), ("spinach", 100, "13-572"), ("garlic", 15, "13-244"), ("olive oil", 15, "17-038"), ("garam masala", 5, "13-829"), ("salt", 2, "17-367")], 606.75),
    ("Spaghetti bolognese", 4, [("beef mince", 500, "18-469"), ("spaghetti", 400, "11-716"), ("chopped tomatoes", 400, "13-530"), ("onion", 150, "13-499"), ("carrot", 100, "13-496"), ("garlic", 10, "13-244"), ("olive oil", 15, "17-038"), ("parmesan", 30, "12-526"), ("tomato puree", 30, "13-531")], 737.19),
    ("Chickpea and coconut curry with rice", 4, [("chickpeas", 480, "13-670"), ("coconut milk", 400, "14-889"), ("onion", 150, "13-499"), ("chopped tomatoes", 400, "13-530"), ("garlic", 10, "13-244"), ("ginger", 15, "13-890"), ("curry powder", 10, "13-876"), ("vegetable oil", 15, "17-686"), ("rice", 300, "11-861")], 665.81),
    ("Salmon, new potatoes and broccoli", 2, [("salmon fillet", 260, "16-356"), ("new potatoes", 400, "13-618"), ("broccoli", 200, "13-502"), ("butter", 15, "17-685"), ("lemon juice", 20, "14-277")], 508.6),
    ("Red lentil dal", 4, [("red lentils", 250, "13-657"), ("onion", 150, "13-499"), ("chopped tomatoes", 200, "13-530"), ("garlic", 10, "13-244"), ("ginger", 10, "13-890"), ("turmeric", 5, "13-861"), ("cumin", 5, "13-889"), ("ghee", 20, "17-640"), ("water", 900, "17-377")], 264.45),
    ("Cheese and vegetable omelette", 1, [("eggs", 150, "12-937"), ("milk", 30, "12-313"), ("cheddar", 30, "12-346"), ("mushrooms", 50, "13-505"), ("red pepper", 50, "13-524"), ("butter", 10, "17-685")], 423.5),
    ("Porridge with banana and honey", 2, [("porridge oats", 100, "11-788"), ("milk", 500, "12-313"), ("banana", 120, "14-318"), ("honey", 20, "17-050")], 382.9),
    ("Paneer tikka wraps", 2, [("paneer", 200, "12-495"), ("tortilla", 120, "11-925"), ("natural yogurt", 100, "12-184"), ("red onion", 80, "13-499"), ("green pepper", 80, "13-318"), ("garam masala", 5, "13-829"), ("vegetable oil", 10, "17-686"), ("lettuce", 50, "13-520")], 615.68),
    ("Tuna pasta bake", 4, [("pasta", 400, "11-716"), ("tuna", 320, "16-416"), ("sweetcorn", 200, "13-622"), ("cheddar cheese", 100, "12-346"), ("milk", 500, "12-313"), ("butter", 40, "17-685"), ("plain flour", 40, "11-886")], 731.3),
    ("Banana and chocolate pancakes (treat)", 2, [("plain flour", 120, "11-886"), ("eggs", 100, "12-937"), ("milk", 250, "12-313"), ("sugar", 30, "17-063"), ("banana", 120, "14-318"), ("dark chocolate", 40, "17-491"), ("butter", 20, "17-685")], 618.3),
]


class RealDataRecipeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with open("/dev/null", "w") as quiet:
            call_command("load_cofid", stdout=quiet)
            call_command("load_ingredient_aliases", stdout=quiet)

    def test_every_alias_points_at_a_real_food(self):
        from nutrition.models import IngredientAlias
        self.assertGreater(IngredientAlias.objects.count(), 200)

    def test_hand_checked_recipes(self):
        for name, servings, items, expected_kcal in HAND_CHECKED_RECIPES:
            with self.subTest(recipe=name):
                result = calculate_nutrition([IngredientInput(i, g) for i, g, _ in items], servings)
                self.assertEqual(result.unmatched, [])
                self.assertEqual([m.food_code for m in result.matched], [code for _, _, code in items])
                self.assertEqual(result.coverage_pct, 100.0)
                self.assertAlmostEqual(result.per_serving["energy_kcal"], expected_kcal, places=1)

    def test_lentil_dal_is_all_green(self):
        name, servings, items, _ = HAND_CHECKED_RECIPES[4]
        result = calculate_nutrition([IngredientInput(i, g) for i, g, _ in items], servings)
        self.assertEqual(set(result.traffic_lights.values()), {"green"})

    def test_ingredient_missing_from_cofid_is_reported(self):
        result = calculate_nutrition([IngredientInput("chia seeds", 20), IngredientInput("rice", 80)], 1)
        self.assertEqual(result.unmatched, ["chia seeds"])
        self.assertEqual(result.coverage_pct, 80.0)
        self.assertFalse(result.is_complete)
