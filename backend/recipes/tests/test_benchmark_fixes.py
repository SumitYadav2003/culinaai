"""
Fixes for what the first evaluation benchmark (9 October 2026) found:

- the allergy gate failed a safe tree-nut-free Indian recipe three times on wording
  like "respects your tree nut allergy", so the safe fallback was shown;
- the difficulty gate counted "overnight" in the storage advice as a hard method;
- "Everyday healthy" stayed high in fat for mince dishes after three tries;
- common ingredients (jasmine rice, fish sauce, flour tortillas...) had no food match;
- the report counted a retry request on the last attempt, which can't be retried.
"""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from nutrition.services import IngredientInput, calculate_nutrition, resolve_ingredients
from recipes import evaluation_service as ev
from recipes.ai_service import build_recipe_prompt
from recipes.insight_service import build_insights, meal_style_correction
from recipes.models import RecipeHistory
from recipes.recipe_quality_engine import check_allergy_safety, check_difficulty_match
from recipes.tests.test_generation_flow import FORM, structure_result
from recipes.tests.test_insights_and_gates import RECIPE_TEXT

TREE_NUTS = {"allergies": "tree nuts", "difficulty": "easy"}


class AllergyWordingTests(SimpleTestCase):
    def assert_safe(self, preferences, text):
        result = check_allergy_safety(preferences, text)
        self.assertTrue(result["passed"], f"{text!r} was failed for {result['details'].get('conflicting_terms')}")

    def assert_unsafe(self, preferences, text, term):
        result = check_allergy_safety(preferences, text)
        self.assertFalse(result["passed"], f"{text!r} should fail")
        self.assertIn(term, result["details"]["conflicting_terms"])

    def test_saying_an_allergen_is_left_out_is_safe(self):
        for text in [
            "This curry is free of tree nuts, respecting your allergy.",
            "It respects your tree nut allergy.",
            "Suitable for anyone with a tree nut allergy.",
            "It excludes tree nuts as requested.",
            "This recipe is tree nut-free.",
            "Unlike a classic korma, it skips cashews and almonds.",
            "Instead of cashews, the sauce is thickened with yoghurt.",
            "Safe for people allergic to nuts.",
            "Leaves out the usual cashew paste.",
            "Contains no dairy products or nuts.",
            "Without any almonds, walnuts or pistachios.",
            # Wording that already passed before the fix.
            "Made without tree nuts.",
            "Contains no tree nuts.",
            "Nut-free and full of flavour.",
            "The user-provided restricted ingredients have been excluded from this recipe.",
        ]:
            with self.subTest(text=text):
                self.assert_safe(TREE_NUTS, text)

    def test_using_an_allergen_still_fails(self):
        for text, term in [
            ("Garnish with toasted almonds.", "almonds"),
            ("Instead of yoghurt, use cashews.", "cashews"),
            ("No time? Add a handful of cashews.", "cashews"),
            ("A no-fuss cashew curry.", "cashew"),  # passed before the fix
            ("Top with almonds (skip if allergic).", "almonds"),
            ("Blend cashews into the sauce. Nut-free option: use seeds.", "cashews"),
            ("Without the yoghurt it is bland, so add almonds.", "almonds"),
            ("Stir in 2 tbsp almond butter.", "almond"),
            ("Use cashews rather than yoghurt.", "cashews"),
            ("Serve with pesto.", "pesto"),  # pesto usually hides cashews
        ]:
            with self.subTest(text=text):
                self.assert_unsafe(TREE_NUTS, text, term)

    def test_other_allergies(self):
        dairy = {"allergies": "dairy"}
        self.assert_safe(dairy, "Use olive oil instead of butter, so it stays dairy-free.")
        self.assert_safe(dairy, "Made without butter or cream.")
        self.assert_unsafe(dairy, "Serve with a dollop of yoghurt.", "yoghurt")
        peanuts = {"allergies": "peanuts"}
        self.assert_safe(peanuts, "No peanuts or peanut oil are used, so it suits a peanut allergy.")
        self.assert_unsafe(peanuts, "Finish with a spoon of peanut butter.", "peanut butter")


class DifficultyTests(SimpleTestCase):
    def test_overnight_outside_the_method_or_optional_is_not_hard(self):
        text = (
            "STEPS:\n1. Marinate the chicken for 20 minutes, or overnight if you have time.\n2. Cook for 20 minutes.\n"
            "STORAGE ADVICE:\nKeep in the fridge overnight, or freeze for up to a month."
        )
        self.assertTrue(check_difficulty_match({"difficulty": "easy"}, text)["passed"])

    def test_a_method_that_needs_overnight_is_still_hard(self):
        text = "STEPS:\n1. Marinate the chicken overnight.\n2. Cook for 20 minutes."
        result = check_difficulty_match({"difficulty": "easy"}, text)
        self.assertFalse(result["passed"])
        self.assertEqual(result["details"]["complex_terms_found"], ["overnight"])

    def test_prompt_asks_not_to_name_allergens_in_the_summary(self):
        prompt = build_recipe_prompt(dict(FORM, cuisine="Indian", meal_type="Dinner", diet_preferences=[],
                                          allergies="tree nuts", cooking_equipment=["Stove / Hob"]))
        self.assertIn("For allergies, only say that the restricted ingredients were left out.", prompt)


def bolognese(beef="beef mince"):
    items = [(beef, 250), ("spaghetti", 160), ("chopped tomatoes", 400), ("onion", 100), ("garlic", 6),
             ("olive oil", 15), ("parmesan", 20)]
    return {"structure": {"servings": 2, "ingredients": [
        {"name": name, "grams": grams, "display": f"{grams} g"} for name, grams in items
    ]}, "warnings": []}


EVERYDAY = {"meal_style": "Everyday healthy", "servings": 2, "allergies": "None provided", "diet_preferences": []}


class FoodDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with open("/dev/null", "w") as quiet:
            call_command("load_food_data", stdout=quiet)

    def test_common_ingredients_now_match(self):
        expected = {
            "jasmine rice": "Rice, Thai fragrant, raw",
            "flour tortillas": "Tortilla, wheat, soft",
            "red chili powder": "Chilli powder",
            "chinese egg noodles": "Noodles, egg, dried, raw",
            "rice vinegar": "Vinegar",
            "fish sauce": "Fish sauce, ready-to-serve",
            "oyster sauce": "Oyster sauce, ready-to-serve",
            "chilli paste": "Chilli sauce",
            "ginger paste": "Ginger, fresh",
            "minced beef": "Beef, mince, raw",
            "5% fat beef mince": "Beef, mince, raw, extra lean",
            "lean lamb mince": "Lamb, mince, raw",
        }
        for name, food in expected.items():
            with self.subTest(name=name):
                resolved = resolve_ingredients([IngredientInput(name, 100)])[0]
                self.assertIsNotNone(resolved.food, f"{name} has no match")
                self.assertEqual(resolved.food.name, food)

    def test_lean_mince_however_it_is_written(self):
        # What the meal-style note asks for has to be matched, or the retry can't be checked.
        for name in ["lean beef mince (5% fat)", "extra-lean beef mince (5% fat)", "beef mince, 5% fat",
                     "5% fat minced beef"]:
            with self.subTest(name=name):
                self.assertEqual(resolve_ingredients([IngredientInput(name, 100)])[0].food.name,
                                 "Beef, mince, raw, extra lean")
        self.assertEqual(resolve_ingredients([IngredientInput("beef mince (20% fat)", 100)])[0].food.name,
                         "Beef, mince, raw")

    def test_fish_sauce_is_very_salty(self):
        result = calculate_nutrition([IngredientInput("fish sauce", 100)], 1)
        self.assertAlmostEqual(result.per_100g["salt_g"], 19.63, places=2)
        self.assertEqual(result.matched[0].source, "USDA FoodData Central")

    def test_meal_style_correction_gives_numbers_and_sources(self):
        insights = build_insights(bolognese(), EVERYDAY, "")
        self.assertFalse(insights["meal_style"]["met"])
        note = meal_style_correction(insights)
        self.assertIn("Saturated fat: 11.9 g per serving; it must be 6 g or less.", note)
        self.assertIn("Most of it comes from beef mince (250 g in the recipe, 8.7 g per serving)", note)
        self.assertIn("extra-lean 5% fat mince", note)

    def test_the_suggested_change_really_meets_everyday_healthy(self):
        lean = build_insights(bolognese("5% fat beef mince"), EVERYDAY, "")
        self.assertTrue(lean["meal_style"]["met"])
        self.assertEqual(meal_style_correction(lean), "")


class FailedDetailsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with open("/dev/null", "w") as quiet:
            call_command("load_food_data", stdout=quiet)
        cls.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")

    def setUp(self):
        self.client.force_login(self.user)
        ai_swaps = patch("recipes.swap_suggestion_service.ask_ai_for_swaps", return_value=None)
        ai_swaps.start()
        self.addCleanup(ai_swaps.stop)

    @patch("recipes.views.generate_recipe_image_base64", side_effect=RuntimeError("images off in tests"))
    @patch("recipes.views.extract_recipe_structure", side_effect=structure_result)
    @patch("recipes.views.generate_ai_recipe")
    def test_the_words_a_failed_check_found_are_saved(self, generate, extract, image):
        generate.side_effect = [
            {"prompt": "p1", "recipe_text": RECIPE_TEXT + "\nCHEF TIPS:\nGarnish with toasted almonds."},
            {"prompt": "p2", "recipe_text": RECIPE_TEXT},
        ]
        self.client.post(reverse("generate_recipe"), dict(FORM, allergies="tree nuts"), follow=True)

        first = RecipeHistory.objects.get(user=self.user).validation_attempt_history[0]
        self.assertIn("Allergy Safety", first["failed_checks"])
        self.assertEqual(first["failed_details"]["Allergy Safety"]["conflicting_terms"], ["almonds"])

        report = ev.quality_summary([ev.history_row(RecipeHistory.objects.get(user=self.user))])
        self.assertEqual(report["objections"]["Allergy Safety"], [("almonds", 1)])


class ReportCountTests(SimpleTestCase):
    def test_a_retry_request_on_the_last_attempt_is_not_counted(self):
        history = [
            {"score": 90, "passed": True, "retry_for": ["Meal Style"]},
            {"score": 90, "passed": True, "retry_for": ["Meal Style"]},
            {"score": 90, "passed": True, "retry_for": ["Meal Style"]},
        ]
        row = {"id": 1, "insights": {}, "attempts": 3, "attempt_history": history, "quality_score": 90,
               "allergies": "", "diets": [], "cuisine": ""}
        self.assertEqual(ev.quality_summary([row])["retry_for"], [("Meal Style", 2)])
