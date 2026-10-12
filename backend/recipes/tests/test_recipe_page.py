"""
Recipe pages: changing a saved recipe (the full preview, the original folded
away, saving), changing a recipe straight after generating it, emailing a
recipe, and the one-line check summary. AI calls are mocked.
"""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from recipes.ai_service import modify_ai_recipe, split_modified_recipe_and_comparison
from recipes.check_summary import summarise_checks
from recipes.models import Recipe
from recipes.tests.test_generation_flow import FORM, structure_result
from recipes.tests.test_insights_and_gates import RECIPE_TEXT
from recipes.views import build_change_preferences

COMPARISON = [
    {"area": "Ingredients", "original": "Chicken breast", "modified": "Grilled tofu", "change": "No meat"},
]


def check(name, passed, **details):
    return {"name": name, "passed": passed, "message": f"{name} message", "details": details}


class CheckSummaryTests(SimpleTestCase):
    def test_all_passed_is_one_plain_line(self):
        summary = summarise_checks({"checks": [check("Allergy Safety", True), check("Diet Compliance", True)]})
        self.assertEqual(summary["state"], "ok")
        self.assertEqual(
            summary["headline"],
            "Checked: it fits your allergies, diet, ingredients, cooking time and equipment.",
        )
        self.assertEqual((summary["passed"], summary["total"]), (2, 2))

    def test_a_minor_miss_is_a_note(self):
        summary = summarise_checks({"checks": [
            check("Allergy Safety", True),
            check("Ingredient Match", False, missing_ingredients=["- 2 carrots", "rice"]),
        ]})
        self.assertEqual(summary["state"], "note")
        self.assertEqual(summary["notes"], ["It doesn't use all of your ingredients (2 carrots, rice)."])

    def test_an_allergy_miss_is_a_warning(self):
        summary = summarise_checks({"checks": [
            check("Allergy Safety", False, conflicting_terms=["almonds"]),
            check("Difficulty Match", False),
        ]})
        self.assertEqual(summary["state"], "warning")
        self.assertEqual(summary["notes"], ["It may contain something you're avoiding (almonds)."])

    def test_nothing_to_summarise(self):
        self.assertIsNone(summarise_checks({}))
        self.assertIsNone(summarise_checks(None))
        self.assertIsNone(summarise_checks({"checks": [], "status": "Validation could not complete"}))


AI_CHANGED_RECIPE = """MODIFIED RECIPE TITLE:
Lighter Chicken Burger

WHAT CHANGED:
Grilled instead of fried.

COOKING TIME:
20 minutes

DIFFICULTY:
easy

**COMPARISON TABLE:**
| Change Area | Original Recipe | Modified Recipe | What Changed |
|---|---|---|---|
| Ingredients | Fried chicken, mayo | Grilled chicken, yogurt | Less fat |
| **Cooking Method** | Fried | Grilled | Less oil |
"""


class ComparisonTableTests(SimpleTestCase):
    def test_table_is_split_from_the_recipe(self):
        text, rows = split_modified_recipe_and_comparison(AI_CHANGED_RECIPE)
        self.assertNotIn("COMPARISON", text)
        self.assertIn("Lighter Chicken Burger", text)
        self.assertEqual(rows, [
            {"area": "Ingredients", "original": "Fried chicken, mayo", "modified": "Grilled chicken, yogurt", "change": "Less fat"},
            {"area": "Cooking Method", "original": "Fried", "modified": "Grilled", "change": "Less oil"},
        ])

    def _modify(self, ai_text):
        recipe = Recipe(title="Grilled Chicken Burger", ingredients_text="chicken", instructions_text="Cook",
                        cooking_time_minutes=25, difficulty="easy")
        with patch("recipes.ai_service.settings") as settings, patch("recipes.ai_service.OpenAI") as client:
            settings.OPENAI_API_KEY = "test"
            client.return_value.responses.create.return_value.output_text = ai_text
            return modify_ai_recipe(recipe, "healthier")

    def test_the_ai_is_asked_for_a_table_and_it_is_returned(self):
        result = self._modify(AI_CHANGED_RECIPE)
        self.assertIn("COMPARISON TABLE:", result["prompt"])
        self.assertEqual(len(result["comparison_rows"]), 2)
        self.assertNotIn("Change Area", result["modified_recipe_text"])

    def test_a_missing_table_still_gives_a_basic_comparison(self):
        result = self._modify(AI_CHANGED_RECIPE.split("**COMPARISON")[0])
        areas = [row["area"] for row in result["comparison_rows"]]
        self.assertEqual(areas, ["Recipe", "Time", "Difficulty", "Summary"])
        self.assertEqual(result["comparison_rows"][1]["modified"], "20 minutes")


class ChangePreferencesTests(SimpleTestCase):
    BASE = {
        "ingredients": "chicken, rice", "diet_preferences": [], "cooking_time_minutes": 40,
        "spice_level": "Medium", "budget_level": "Moderate Budget", "difficulty": "medium",
        "meal_style": "No preference", "additional_notes": "None provided",
        "recipe_version": "Cheapest", "expected": {"cost": 1},
    }

    def test_settings_follow_the_change(self):
        self.assertEqual(build_change_preferences(self.BASE, "vegetarian", "", "T", "")["diet_preferences"], ["Vegetarian"])
        self.assertEqual(build_change_preferences(self.BASE, "quicker", "", "T", "")["cooking_time_minutes"], 25)
        self.assertEqual(build_change_preferences(self.BASE, "healthier", "", "T", "")["meal_style"], "Everyday healthy")
        self.assertEqual(build_change_preferences(self.BASE, "cheaper", "", "T", "")["budget_level"], "Low Budget")
        self.assertEqual(build_change_preferences(self.BASE, "spicier", "", "T", "")["spice_level"], "Spicy")
        self.assertEqual(build_change_preferences(self.BASE, "simpler", "", "T", "")["difficulty"], "easy")

    def test_the_ai_is_told_the_change_and_the_last_recipe(self):
        changed = build_change_preferences(self.BASE, "custom", "use tofu", "Chicken rice", "CHICKEN RICE\nStep 1")
        self.assertIn("Change request: use tofu", changed["additional_notes"])
        self.assertIn('"Chicken rice"', changed["additional_notes"])
        self.assertIn("CHICKEN RICE Step 1", changed["additional_notes"])
        self.assertNotIn("recipe_version", changed)  # an earlier "Cook this version" is not carried over
        self.assertEqual(self.BASE["diet_preferences"], [])  # the original settings are untouched


class RecipePageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with open("/dev/null", "w") as quiet:
            call_command("load_food_data", stdout=quiet)
        cls.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")

    def setUp(self):
        self.client.force_login(self.user)
        self.recipe = Recipe.objects.create(
            user=self.user, title="Grilled Chicken Burger", ingredients_text="chicken breast, burger bun",
            instructions_text=RECIPE_TEXT, cooking_time_minutes=25, difficulty="easy",
        )
        for target in ("recipes.swap_suggestion_service.ask_ai_for_swaps",):
            patcher = patch(target, return_value=None)
            patcher.start()
            self.addCleanup(patcher.stop)

    def detail(self):
        return self.client.get(reverse("saved_recipe_detail", args=[self.recipe.id])).content.decode()

    def test_page_without_a_change_shows_the_recipe(self):
        html = self.detail()
        self.assertIn('id="rp-original" class="rp-original" >', html.replace("\n", " ").replace("  ", " "))
        self.assertNotIn("Here's your changed recipe", html)
        self.assertIn("Change this recipe", html)
        self.assertIn('placeholder="Send this recipe to an email address"', html)

    @patch("recipes.views.generate_recipe_image_base64", side_effect=RuntimeError("images off in tests"))
    @patch("recipes.views.extract_recipe_structure", side_effect=structure_result)
    @patch("recipes.views.modify_ai_recipe")
    def test_change_preview_save_and_link_back(self, modify, extract, image):
        modify.return_value = {
            "modified_recipe_text": RECIPE_TEXT.replace("Grilled Chicken Burger", "Lighter Chicken Burger"),
            "comparison_rows": COMPARISON,
            "prompt": "p",
        }
        url = reverse("modify_saved_recipe", args=[self.recipe.id])

        # Typing a change without picking one of the buttons counts as a custom change.
        self.client.post(url, {"custom_instruction": "make it lighter"})
        self.assertEqual(modify.call_args.kwargs["modification_type"], "custom")

        html = self.detail()
        self.assertIn("Here's your changed recipe", html)
        self.assertIn("What changed", html)
        self.assertIn("Grilled tofu", html)
        self.assertIn('You asked: "make it lighter"', html)
        self.assertIn("View original recipe", html)
        self.assertIn('id="rp-original" class="rp-original" hidden', html)  # the original is folded away
        self.assertIn("rp-checks", html)  # one-line check summary, not the old report

        self.client.post(reverse("save_modified_recipe", args=[self.recipe.id]))
        changed = Recipe.objects.exclude(id=self.recipe.id).get()
        self.assertEqual(changed.original_recipe, self.recipe)
        changed_html = self.client.get(reverse("saved_recipe_detail", args=[changed.id])).content.decode()
        self.assertIn("Grilled Chicken Burger", changed_html)  # small box linking to the original
        self.assertIn(reverse("saved_recipe_detail", args=[self.recipe.id]), changed_html)
        self.assertIn("What changed from the original", changed_html)

    def test_email_a_saved_recipe(self):
        response = self.client.post(
            reverse("send_recipe_email", args=[self.recipe.id]), {"recipient_email": "friend@example.com"}, follow=True,
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["friend@example.com"])
        self.assertIn("Grilled Chicken Burger", mail.outbox[0].body)
        self.assertIn("Recipe sent to friend@example.com.", response.content.decode())

    @patch("recipes.views.send_mail", side_effect=OSError("smtp down"))
    def test_email_failure_is_explained_not_a_crash(self, send):
        response = self.client.post(
            reverse("send_recipe_email", args=[self.recipe.id]), {"recipient_email": "friend@example.com"}, follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("The email couldn&#x27;t be sent just now.", response.content.decode())


class GeneratePageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with open("/dev/null", "w") as quiet:
            call_command("load_food_data", stdout=quiet)
        cls.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")

    def setUp(self):
        self.client.force_login(self.user)
        patcher = patch("recipes.swap_suggestion_service.ask_ai_for_swaps", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch("recipes.views.generate_recipe_image_base64", side_effect=RuntimeError("images off in tests"))
    @patch("recipes.views.extract_recipe_structure", side_effect=structure_result)
    @patch("recipes.views.generate_ai_recipe", return_value={"prompt": "p", "recipe_text": RECIPE_TEXT})
    def test_generate_then_change_then_email(self, generate, extract, image):
        html = self.client.post(reverse("generate_recipe"), FORM, follow=True).content.decode()
        self.assertIn("Your recipe is ready", html)
        self.assertIn("rp-checks", html)
        self.assertIn("Change this recipe", html)
        self.assertIn(reverse("change_generated_recipe"), html)
        self.assertIn(reverse("email_generated_recipe"), html)

        calls = generate.call_count
        self.client.post(reverse("change_generated_recipe"), {"modification_type": "vegetarian"}, follow=True)
        self.assertGreater(generate.call_count, calls)
        changed = generate.call_args.args[0]
        self.assertIn("Vegetarian", changed["diet_preferences"])
        self.assertIn("Change request: Make it vegetarian", changed["additional_notes"])

        # The latest recipe is emailed (here the safe fallback, as the burger has chicken in it).
        self.client.post(reverse("email_generated_recipe"), {"recipient_email": "me@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.client.session["latest_ai_recipe_text"].strip()[:60], mail.outbox[0].body)

    def test_change_needs_a_recipe_and_a_choice(self):
        response = self.client.post(reverse("change_generated_recipe"), {"modification_type": "quicker"}, follow=True)
        self.assertIn("That recipe is no longer available.", response.content.decode())

        session = self.client.session
        session["latest_recipe_preferences"] = {"ingredients": "rice"}
        session["latest_ai_recipe_text"] = RECIPE_TEXT
        session.save()
        response = self.client.post(reverse("change_generated_recipe"), {}, follow=True)
        self.assertIn("Choose a change, or describe the change you want.", response.content.decode())


class RecipeListAndSharedPageTests(TestCase):
    """Saved list, favourites, the shared page and the print page after the redesign."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        cls.other = User.objects.create_user("friend", "friend@example.com", "pass-12345")
        cls.recipe = Recipe.objects.create(
            user=cls.user, title="Grilled Chicken Burger", ingredients_text="chicken breast, burger bun",
            instructions_text=RECIPE_TEXT, cooking_time_minutes=25, difficulty="easy",
            allergy_notes="peanuts", is_public=True,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_saved_list_is_simple_cards(self):
        html = self.client.get(reverse("saved_recipes")).content.decode()
        self.assertIn("Saved recipes", html)
        self.assertIn(reverse("saved_recipe_detail", args=[self.recipe.id]), html)
        self.assertIn("Shared", html)
        for old in ("Older Recipe", "Validation not stored", "Private Recipe", "CulinaAI Verified"):
            self.assertNotIn(old, html)

    def test_empty_search_says_so(self):
        html = self.client.get(reverse("saved_recipes"), {"q": "no such dish"}).content.decode()
        self.assertIn("No recipes match", html)

    def test_saved_recipe_shows_what_is_avoided_and_lays_out_the_recipe(self):
        html = self.client.get(reverse("saved_recipe_detail", args=[self.recipe.id])).content.decode()
        self.assertIn("You're avoiding:", html)
        self.assertIn("data-culina-recipe-output data-title-shown", html)
        self.assertIn("What you asked for", html)
        self.assertNotIn("Advanced AI Cooking Assistant", html)

    def test_shared_page(self):
        self.client.force_login(self.other)
        html = self.client.get(reverse("community_recipe_detail", args=[self.recipe.id])).content.decode()
        self.assertIn("Shared by cook", html)
        self.assertIn("Made without:", html)
        self.assertIn("Ratings and comments", html)
        self.assertNotIn("Quality Score", html)
        self.assertNotIn("Open in your recipes", html)  # only the owner sees this

    def test_print_page(self):
        html = self.client.get(reverse("print_saved_recipe", args=[self.recipe.id])).content.decode()
        self.assertIn("Print or save as PDF", html)
        self.assertIn("Made without:", html)
        self.assertNotIn("Final AI Recipe", html)
