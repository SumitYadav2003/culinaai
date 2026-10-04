"""
End to end through the real views, with only the AI calls mocked:
generate -> gates 9 and 10 per attempt -> history -> save -> saved recipe page.
"""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from recipes.models import Recipe, RecipeHistory
from recipes.tests.test_insights_and_gates import RECIPE_TEXT, burger_structure, suggestion

FORM = {
    "ingredients": "chicken breast, burger bun, tomato, greek yogurt",
    "allergies": "",
    "cooking_time_minutes": 30,
    "servings": 2,
    "difficulty": "easy",
    "spice_level": "mild",
    "budget_level": "medium",
    "nutrition_goal": "balanced",
    "meal_style": "any",
    "cooking_equipment": ["stove"],
}


def structure_result(*args, **kwargs):
    structure = burger_structure([suggestion("lettuce", "not_in_your_ingredients")])
    structure["ingredients"].append({"name": "worcestershire sauce", "display": "1 tsp", "grams": 5})
    return {"structure": structure, "warnings": []}


class GenerationFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with open("/dev/null", "w") as quiet:
            call_command("load_food_data", stdout=quiet)
        cls.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")

    def setUp(self):
        self.client.force_login(self.user)
        # No real AI call for swap ideas in tests (tests that need some patch it themselves).
        ai_swaps = patch("recipes.swap_suggestion_service.ask_ai_for_swaps", return_value=None)
        self.ask_ai_for_swaps = ai_swaps.start()
        self.addCleanup(ai_swaps.stop)

    @patch("recipes.views.generate_recipe_image_base64", side_effect=RuntimeError("images off in tests"))
    @patch("recipes.views.extract_recipe_structure", side_effect=structure_result)
    @patch("recipes.views.generate_ai_recipe")
    def test_generate_check_save_and_show(self, generate, extract, image):
        generate.side_effect = [
            {"prompt": "p1", "recipe_text": RECIPE_TEXT + "\nCHEF TIPS:\nGarlic boosts immunity."},
            {"prompt": "p2", "recipe_text": RECIPE_TEXT},
        ]

        response = self.client.post(reverse("generate_recipe"), FORM, follow=True)

        # Gate 9 rejected the first attempt's health claim, so the recipe was regenerated.
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(extract.call_count, 2)
        history = RecipeHistory.objects.get(user=self.user)
        self.assertEqual(history.validation_attempts, 2)
        failed_first = history.validation_attempt_history[0]["failed_checks"]
        self.assertIn("Health Claims", failed_first)

        # Insights were worked out and stored with the history item.
        self.assertTrue(history.insights["available"])
        self.assertEqual(history.insights["tag"], "everyday")
        self.assertIn("Cereals containing gluten", history.insights["allergens"])

        # The generate page shows the panel, with the hidden allergen in red.
        html = response.content.decode()
        self.assertIn("culina-insights", html)
        self.assertIn("Worcestershire sauce usually contains anchovies (fish).", html)

        # Saving keeps the insights, and the saved page offers "Add it back".
        self.client.post(reverse("save_generated_recipe"))
        recipe = Recipe.objects.get(user=self.user)
        self.assertEqual(recipe.insights, history.insights)
        detail = self.client.get(reverse("saved_recipe_detail", args=[recipe.id])).content.decode()
        self.assertIn("Compared with the classic", detail)
        self.assertIn("Add lettuce back into the recipe", detail)

    @patch("recipes.views.generate_recipe_image_base64", side_effect=RuntimeError("images off in tests"))
    @patch("recipes.views.extract_recipe_structure", return_value=None)
    @patch("recipes.views.generate_ai_recipe", return_value={"prompt": "p", "recipe_text": RECIPE_TEXT})
    def test_a_failed_extraction_never_blocks_the_recipe(self, generate, extract, image):
        response = self.client.post(reverse("generate_recipe"), FORM, follow=True)
        history = RecipeHistory.objects.get(user=self.user)
        self.assertFalse(history.insights["available"])
        self.assertIn("Nutrition could not be worked out for this recipe.", response.content.decode())
