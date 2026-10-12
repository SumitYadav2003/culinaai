"""
Dashboard, pantry, history and fridge scanner pages after the redesign,
and the ingredient counting behind "Ingredients you use most".
"""

import datetime

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from recipes.analytics_service import split_ingredients
from recipes.models import FridgeScan, PantryItem, Recipe, RecipeHistory
from recipes.tests.test_insights_and_gates import RECIPE_TEXT


class IngredientCountingTests(SimpleTestCase):
    def test_one_ingredient_per_line_keeps_preparation_out(self):
        text = "- 4 chicken thighs\n- 1 large aubergine, cubed\n- 2 tbsp fresh coriander, chopped\n- 3 garlic cloves, crushed"
        self.assertEqual(split_ingredients(text), ["chicken thighs", "aubergine", "coriander", "garlic"])

    def test_a_single_line_is_split_at_commas(self):
        self.assertEqual(split_ingredients("chicken, rice, tomatoes"), ["chicken", "rice", "tomatoes"])

    def test_numbers_and_brackets_are_dropped(self):
        self.assertEqual(split_ingredients("1. 200 g paneer (cubed)\n2. 2 tortillas"), ["paneer", "tortillas"])
        self.assertEqual(split_ingredients(""), [])


class AccountPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        Recipe.objects.create(
            user=cls.user, title="Grilled Chicken Burger", is_saved=True,
            ingredients_text="- 2 chicken breasts\n- 1 tomato, sliced", instructions_text=RECIPE_TEXT,
            cooking_time_minutes=25, difficulty="easy",
        )
        cls.history = RecipeHistory.objects.create(
            user=cls.user, title="Grilled Chicken Burger", recipe_text=RECIPE_TEXT,
            ingredients_text="chicken, burger bun", allergies="peanuts",
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_dashboard_is_short_and_counts_real_ingredients(self):
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("Hi cook", html)
        self.assertIn("Your latest recipes", html)
        self.assertIn("Grilled Chicken Burger", html)
        self.assertIn("Chicken breasts", html)
        self.assertNotIn("<li><span>Sliced</span></li>", html)
        for old in ("your AI kitchen is online", "Personal Analytics Dashboard", "chart.js"):
            self.assertNotIn(old, html)

    def test_pantry_add_one_item_and_several(self):
        url = reverse("pantry_list")
        soon = (timezone.localdate() + datetime.timedelta(days=1)).isoformat()
        response = self.client.post(url, {
            "pantry_action": "single_add", "ingredient_name": "spinach", "quantity": "200",
            "unit": "g", "category": "vegetable", "expiry_date": soon, "is_available": "on",
        }, follow=True)
        self.assertContains(response, "Added spinach to your pantry.")
        self.assertTrue(PantryItem.objects.get(ingredient_name="spinach").is_available)

        response = self.client.post(url, {
            "pantry_action": "bulk_add",
            "bulk_ingredient_name": ["rice", ""], "bulk_quantity": ["1", ""], "bulk_unit": ["kg", "pcs"],
            "bulk_category": ["grain", "other"], "bulk_expiry_date": ["", ""], "bulk_notes": ["", ""],
        }, follow=True)
        self.assertContains(response, "Added 1 item to your pantry.")

        html = self.client.get(url).content.decode()
        self.assertIn("Use these first", html)
        self.assertIn("<strong>spinach</strong> in 1 day", html)
        self.assertIn("1 kg", html)

    def test_history_list_and_entry(self):
        html = self.client.get(reverse("recipe_history")).content.decode()
        self.assertIn(reverse("recipe_history_detail", args=[self.history.id]), html)

        html = self.client.get(reverse("recipe_history_detail", args=[self.history.id])).content.decode()
        self.assertIn("You were avoiding:", html)
        self.assertIn("data-culina-recipe-output data-title-shown", html)
        self.assertIn(reverse("save_history_recipe", args=[self.history.id]), html)

        response = self.client.post(reverse("save_history_recipe", args=[self.history.id]), follow=True)
        self.assertContains(response, "Saved. You&#x27;ll find it in Saved recipes.")

    def test_fridge_scanner_pages(self):
        html = self.client.get(reverse("fridge_scan_upload")).content.decode()
        self.assertIn("Scan your fridge", html)
        self.assertNotIn("AI Refrigerator Scanner", html)

        scan = FridgeScan.objects.create(
            user=self.user, detected_items=["Milk", "Eggs"], scan_status=FridgeScan.STATUS_COMPLETED,
        )
        html = self.client.get(reverse("fridge_scan_confirm", args=[scan.id])).content.decode()
        self.assertIn("Check what was found", html)
        self.assertIn("Milk\nEggs", html)

        response = self.client.post(
            reverse("fridge_scan_confirm", args=[scan.id]),
            {"confirmed_items_text": "Milk\nEggs\nButter", "action": "add_to_pantry"}, follow=True,
        )
        self.assertContains(response, "Added 3 items to your pantry.")

        html = self.client.get(reverse("fridge_scan_history")).content.decode()
        self.assertIn("Milk, Eggs, Butter", html)
