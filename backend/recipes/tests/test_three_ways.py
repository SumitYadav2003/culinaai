"""
"One dish, three ways" (swap_service.py) and the meal style picker
(insight_service.py and the generate view). Uses the real food data; the AI is mocked.
"""

import csv
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from nutrition.models import CofidFood
from nutrition.services import IngredientInput, calculate_for_foods, resolve_ingredients
from nutrition.tests.test_real_data import HAND_CHECKED_RECIPES
from recipes.insight_service import build_insights, meal_style_correction
from recipes.models import Recipe, RecipeHistory
from recipes.swap_service import SWAPS_CSV, apply_swap, load_swaps, three_ways
from recipes.tests.test_generation_flow import FORM
from recipes.tests.test_insights_and_gates import RECIPE_TEXT

NO_SETTINGS = {"allergies": "None provided", "diet_preferences": []}


def recipe(number):
    """(resolved ingredients, servings) for one of the hand-checked recipes."""
    _, servings, items, _ = HAND_CHECKED_RECIPES[number]
    return resolve_ingredients([IngredientInput(name, grams) for name, grams, _ in items]), servings


def version(versions, goal):
    return next(v for v in versions if v["goal"] == goal)


def swap_texts(v):
    return [swap["text"] for swap in v["swaps"]]


class SwapListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with open("/dev/null", "w") as quiet:
            call_command("load_food_data", stdout=quiet)

    def test_every_swap_points_at_real_priced_foods(self):
        with SWAPS_CSV.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), len(load_swaps()))
        for row in rows:
            with self.subTest(swap=row["text"]):
                self.assertIn("{from}", row["text"])
                self.assertTrue(0 < float(row["share"]) <= 1)
                codes = [row["from_code"]] + ([row["to_code"]] if row["to_code"] else [])
                for code in codes:
                    food = CofidFood.objects.get(food_code=code)
                    self.assertIsNotNone(food.price_per_kg_gbp, code)
                if row["to_code"]:
                    self.assertTrue(row["to_name"])
                    self.assertGreater(float(row["ratio"]), 0)

    def test_half_swap_keeps_half_and_adds_the_new_food(self):
        resolved, _ = recipe(1)  # spaghetti bolognese, 500 g beef mince
        swap = next(s for s in load_swaps() if s.from_code == "18-469" and s.to_code == "13-657")
        lentils = CofidFood.objects.get(food_code="13-657")
        swapped = apply_swap(resolved, swap, lentils)
        self.assertIn(("beef mince", 250.0), [(i.name, i.grams) for i in swapped])
        self.assertIn(("red lentils", 100.0), [(i.name, i.grams) for i in swapped])  # 250 g x 0.4


class ThreeWaysTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with open("/dev/null", "w") as quiet:
            call_command("load_food_data", stdout=quiet)

    def test_bolognese(self):
        resolved, servings = recipe(1)
        original = calculate_for_foods(resolved, servings)
        versions = three_ways(resolved, servings, NO_SETTINGS)
        self.assertEqual([v["goal"] for v in versions], ["cheapest", "healthiest", "greenest"])

        cheapest = version(versions, "cheapest")
        self.assertIn("Swap half the beef mince for red lentils", swap_texts(cheapest))
        self.assertLess(cheapest["cost"], original.cost_gbp_per_serving)
        self.assertLessEqual(len(cheapest["swaps"]), 3)

        greenest = version(versions, "greenest")
        self.assertIn("Use turkey mince instead of beef mince", swap_texts(greenest))
        # Beef 99.48 kg CO2e/kg -> poultry 9.87: 0.5 kg x 89.61 / 4 servings = 11.20 kg less
        self.assertEqual(greenest["swaps"][0]["impact"], "11.20 kg CO₂e less per serving")

        healthiest = version(versions, "healthiest")
        self.assertEqual(healthiest["tag"], "everyday")
        self.assertEqual(original.traffic_lights["saturates_g"], "red")

    def test_cheapest_and_greenest_never_make_a_traffic_light_worse(self):
        order = {"green": 0, "amber": 1, "red": 2}
        for number in range(len(HAND_CHECKED_RECIPES)):
            resolved, servings = recipe(number)
            original = calculate_for_foods(resolved, servings)
            for v in three_ways(resolved, servings, NO_SETTINGS):
                if v["goal"] == "healthiest" or not v["swaps"]:
                    continue
                with self.subTest(recipe=HAND_CHECKED_RECIPES[number][0], goal=v["goal"]):
                    # Recalculate the version from its swaps, independently of the summary.
                    swapped = resolved
                    for chosen in v["swaps"]:
                        swap = next(s for s in load_swaps()
                                    if (s.from_code, s.to_code) == (chosen["from_code"], chosen["to_code"]))
                        new_food = CofidFood.objects.filter(food_code=swap.to_code).first()
                        swapped = apply_swap(swapped, swap, new_food)
                    result = calculate_for_foods(swapped, servings)
                    for nutrient, light in result.traffic_lights.items():
                        self.assertLessEqual(order[light], order[original.traffic_lights[nutrient]])

    def test_red_lentil_dal_by_hand(self):
        # Ghee 20 g at £15.00/kg -> rapeseed oil 20 g at £1.58/kg: (0.300 - 0.032) / 4 = £0.07 less.
        # Ghee has no carbon figure, so the carbon change is not claimed.
        resolved, servings = recipe(4)
        cheapest = version(three_ways(resolved, servings, NO_SETTINGS), "cheapest")
        self.assertEqual(swap_texts(cheapest), ["Cook with rapeseed oil instead of ghee"])
        self.assertEqual(cheapest["swaps"][0]["impact"], "£0.07 less per serving")
        self.assertEqual(cheapest["cost_change"], -0.07)
        self.assertEqual(cheapest["cost"], 0.50)  # £0.57 - £0.07
        self.assertIsNone(cheapest["carbon_change"])
        self.assertEqual(cheapest["stats"][0], {"label": "Cost", "value": "£0.50", "change": "£0.07 less"})
        self.assertEqual(cheapest["stats"][1]["change"], "")

    def test_swaps_respect_allergies_and_diet(self):
        resolved, servings = recipe(7)  # paneer tikka wraps
        anyone = three_ways(resolved, servings, NO_SETTINGS)
        self.assertIn("Use firm tofu instead of paneer", swap_texts(version(anyone, "greenest")))

        soya_allergy = three_ways(resolved, servings, {"allergies": "soya", "diet_preferences": []})
        for v in soya_allergy:
            self.assertNotIn("Use firm tofu instead of paneer", swap_texts(v))

        resolved, servings = recipe(2)  # chickpea and coconut curry
        dairy_free = three_ways(resolved, servings, {"allergies": "None provided", "diet_preferences": ["Dairy Free"]})
        for v in dairy_free:
            self.assertFalse(any("yogurt" in text for text in swap_texts(v)), v)

    def test_not_enough_data_says_so(self):
        resolved = resolve_ingredients([IngredientInput("dragon fruit", 300), IngredientInput("salt", 2)])
        healthiest = version(three_ways(resolved, 1, NO_SETTINGS), "healthiest")
        self.assertEqual(healthiest["swaps"], [])
        self.assertIn("weren't found", healthiest["message"])


def structure(salt_grams):
    """A small chicken and rice dish; lots of salt makes it 'high in salt'."""
    return {
        "structure": {
            "ingredients": [
                {"name": "chicken breast", "display": "300 g", "grams": 300},
                {"name": "basmati rice", "display": "200 g", "grams": 200},
                {"name": "spinach", "display": "100 g", "grams": 100},
                {"name": "salt", "display": "", "grams": salt_grams},
            ],
            "servings": 2,
        },
        "warnings": [],
    }


class MealStyleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with open("/dev/null", "w") as quiet:
            call_command("load_food_data", stdout=quiet)

    def insights(self, salt_grams, meal_style):
        return build_insights(structure(salt_grams), dict(NO_SETTINGS, servings=2, meal_style=meal_style), "")

    def test_everyday_met_and_missed(self):
        met = self.insights(2, "Everyday healthy")
        self.assertEqual(met["tag"], "everyday")
        self.assertTrue(met["meal_style"]["met"])
        self.assertEqual(meal_style_correction(met), "")

        missed = self.insights(15, "Everyday healthy")
        self.assertEqual(missed["tag"], "treat")
        self.assertFalse(missed["meal_style"]["met"])
        self.assertIn("high in salt", missed["meal_style"]["text"])
        self.assertIn("high in salt", meal_style_correction(missed))

    def test_treat_and_no_preference_never_ask_for_a_retry(self):
        treat = self.insights(15, "Treat")
        self.assertTrue(treat["meal_style"]["met"])
        self.assertEqual(meal_style_correction(treat), "")
        self.assertIsNone(self.insights(15, "No preference")["meal_style"])
        self.assertIsNone(self.insights(15, None)["meal_style"])

    def test_three_ways_are_part_of_the_insights(self):
        insights = self.insights(15, "Everyday healthy")
        self.assertEqual(insights["version"], 2)
        healthiest = version(insights["three_ways"], "healthiest")
        self.assertIn("Use half the salt", swap_texts(healthiest))


class MealStyleFlowTests(TestCase):
    """Through the real generate view, with the AI calls mocked."""

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
    @patch("recipes.views.extract_recipe_structure", side_effect=[structure(15), structure(2)])
    @patch("recipes.views.generate_ai_recipe")
    def test_everyday_healthy_retries_when_the_dish_is_high_in_salt(self, generate, extract, image):
        generate.side_effect = [
            {"prompt": "p1", "recipe_text": RECIPE_TEXT},
            {"prompt": "p2", "recipe_text": RECIPE_TEXT},
        ]
        response = self.client.post(reverse("generate_recipe"), dict(FORM, meal_style="everyday"), follow=True)

        self.assertEqual(generate.call_count, 2)
        retry_notes = generate.call_args_list[1].args[0]["additional_notes"]
        self.assertIn("Meal Style: The user asked for an everyday healthy dish", retry_notes)

        history = RecipeHistory.objects.get(user=self.user)
        self.assertEqual(history.insights["meal_style"]["chosen"], "everyday")
        self.assertTrue(history.insights["meal_style"]["met"])
        html = response.content.decode()
        self.assertIn("One dish, three ways", html)
        self.assertIn("this dish has no high levels", html)
        self.assertIn(reverse("generate_recipe_version"), html)  # "Cook this version" on the generate page
        self.assertIn("The recipe above is your recipe", html)

        # Once saved, each version can be cooked through the existing "modify" flow.
        self.client.post(reverse("save_generated_recipe"))
        saved = Recipe.objects.get(user=self.user)
        detail = self.client.get(reverse("saved_recipe_detail", args=[saved.id])).content.decode()
        self.assertIn("Cook this version", detail)
        self.assertIn("Make the healthiest version of this recipe with these swaps:", detail)

    @patch("recipes.views.generate_recipe_image_base64", side_effect=RuntimeError("images off in tests"))
    @patch("recipes.views.extract_recipe_structure", side_effect=[structure(15), structure(2)])
    @patch("recipes.views.generate_ai_recipe")
    def test_a_validated_recipe_is_never_swapped_for_one_that_failed(self, generate, extract, image):
        # The first try passes validation but is high in salt. The second and third meet the
        # meal style but make a health claim (gate 9, a hard fail), so the first is kept.
        generate.side_effect = [
            {"prompt": "p1", "recipe_text": RECIPE_TEXT},
            {"prompt": "p2", "recipe_text": RECIPE_TEXT + "\nCHEF TIPS:\nThis will cure a cold."},
            {"prompt": "p3", "recipe_text": RECIPE_TEXT + "\nCHEF TIPS:\nThis will cure a cold."},
        ]
        extract.side_effect = [structure(15), structure(2), structure(2)]
        response = self.client.post(reverse("generate_recipe"), dict(FORM, meal_style="everyday"), follow=True)

        history = RecipeHistory.objects.get(user=self.user)
        self.assertNotIn("cure", history.recipe_text)
        self.assertFalse(history.insights["meal_style"]["met"])
        self.assertIn("Not everyday healthy:", response.content.decode())

    @patch("recipes.views.generate_recipe_image_base64", side_effect=RuntimeError("images off in tests"))
    @patch("recipes.views.extract_recipe_structure", side_effect=[structure(15)])
    @patch("recipes.views.generate_ai_recipe", return_value={"prompt": "p", "recipe_text": RECIPE_TEXT})
    def test_no_preference_never_retries(self, generate, extract, image):
        # FORM picks "No preference" explicitly; the field is required.
        self.client.post(reverse("generate_recipe"), FORM, follow=True)
        self.assertEqual(generate.call_count, 1)
        self.assertIsNone(RecipeHistory.objects.get(user=self.user).insights["meal_style"])


class FormRulesTests(TestCase):
    """Meal style is required; cooking time and servings may be left blank."""

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

    @patch("recipes.views.generate_ai_recipe")
    def test_meal_style_is_required(self, generate):
        form = {key: value for key, value in FORM.items() if key != "meal_style"}
        response = self.client.post(reverse("generate_recipe"), form)
        self.assertEqual(generate.call_count, 0)
        self.assertIn("Choose a meal style: Everyday healthy, Treat or No preference.", response.content.decode())

    def test_labels_say_required_and_optional(self):
        html = self.client.get(reverse("generate_recipe")).content.decode()
        self.assertEqual(html.count("(required)"), 2)  # ingredients and meal style
        self.assertIn('<option value="" selected>Choose one</option>', html)
        self.assertGreaterEqual(html.count("(optional)"), 13)

    @patch("recipes.views.generate_recipe_image_base64", side_effect=RuntimeError("images off in tests"))
    @patch("recipes.views.extract_recipe_structure", return_value=structure(2))
    @patch("recipes.views.generate_ai_recipe", return_value={"prompt": "p", "recipe_text": RECIPE_TEXT})
    def test_blank_cooking_time_and_servings_use_the_defaults(self, generate, extract, image):
        self.client.post(reverse("generate_recipe"), dict(FORM, cooking_time_minutes="", servings=""))
        preferences = generate.call_args.args[0]
        self.assertEqual((preferences["cooking_time_minutes"], preferences["servings"]), (30, 2))


def paneer_structure(*args, **kwargs):
    return {
        "structure": {
            "ingredients": [
                {"name": "paneer", "display": "200 g", "grams": 200},
                {"name": "tortilla", "display": "2", "grams": 120},
                {"name": "red onion", "display": "1", "grams": 80},
                {"name": "vegetable oil", "display": "1 tbsp", "grams": 10},
            ],
            "servings": 2,
        },
        "warnings": [],
    }


class CookThisVersionTests(TestCase):
    """'Cook this version' on the generate page, through the real views with the AI mocked."""

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
    @patch("recipes.views.extract_recipe_structure", side_effect=paneer_structure)
    @patch("recipes.views.generate_ai_recipe", return_value={"prompt": "p", "recipe_text": RECIPE_TEXT})
    def test_cook_the_greenest_version(self, generate, extract, image):
        form = dict(FORM, ingredients="paneer, tortilla, red onion")
        self.client.post(reverse("generate_recipe"), form, follow=True)
        first = RecipeHistory.objects.get(user=self.user)
        greenest = version(first.insights["three_ways"], "greenest")
        self.assertEqual(swap_texts(greenest), ["Use firm tofu instead of paneer"])

        response = self.client.post(reverse("generate_recipe_version"), {"goal": "greenest"}, follow=True)

        # The same pipeline ran again with the swap made in the ingredient list.
        preferences = generate.call_args.args[0]
        self.assertEqual(preferences["ingredients"], "tortilla, red onion, firm tofu")
        self.assertIn("Recipe version: cook the greenest version of the user's last recipe", preferences["additional_notes"])
        self.assertIn("Make these swaps: Use firm tofu instead of paneer.", preferences["additional_notes"])
        self.assertIn("paneer (200 g)", preferences["additional_notes"])
        self.assertEqual(RecipeHistory.objects.filter(user=self.user).count(), 2)

        latest = RecipeHistory.objects.filter(user=self.user).latest("id")
        self.assertEqual(latest.insights["basis"]["version"], "Greenest")
        self.assertIn("The recipe above is the greenest version", response.content.decode())

    @patch("recipes.views.generate_recipe_image_base64", side_effect=RuntimeError("images off in tests"))
    @patch("recipes.views.extract_recipe_structure", side_effect=paneer_structure)
    @patch("recipes.views.generate_ai_recipe", return_value={"prompt": "p", "recipe_text": RECIPE_TEXT})
    def test_ai_swap_ideas_reach_the_page_once_per_recipe(self, generate, extract, image):
        # Chickpeas for paneer (£1.65/kg drained vs £9.00/kg) beats tofu on cost.
        self.ask_ai_for_swaps.return_value = ai_says(("paneer", "chickpeas", "all", 100, "Rinse the chickpeas."))
        response = self.client.post(reverse("generate_recipe"), FORM, follow=True)
        self.assertEqual(self.ask_ai_for_swaps.call_count, 1)  # final recipe only, not every attempt
        history = RecipeHistory.objects.get(user=self.user)
        self.assertEqual((history.insights["ai_swaps"]["suggested"], history.insights["ai_swaps"]["accepted"]), (1, 1))
        cheapest = version(history.insights["three_ways"], "cheapest")
        self.assertIn("Use chickpeas instead of paneer", swap_texts(cheapest))
        self.assertIn("AI idea, checked by code", response.content.decode())

    def test_without_a_recent_recipe_nothing_is_generated(self):
        response = self.client.post(reverse("generate_recipe_version"), {"goal": "cheapest"}, follow=True)
        self.assertIn("That recipe is no longer available.", response.content.decode())
        self.assertFalse(RecipeHistory.objects.filter(user=self.user).exists())

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(reverse("generate_recipe_version")).status_code, 405)

    def test_half_swaps_and_use_less_keep_the_original(self):
        from recipes.views import build_version_preferences

        version_data = {"title": "Cheapest", "swaps": [
            {"from_name": "beef mince", "to_name": "red lentils", "to_code": "13-657", "share": 0.5,
             "text": "Swap half the beef mince for red lentils"},
            {"from_name": "salt", "to_name": "", "to_code": "", "share": 0.5, "text": "Use half the salt"},
        ]}
        preferences = {"ingredients": "beef mince, spaghetti, salt", "additional_notes": "None provided"}
        result = build_version_preferences(preferences, version_data, {"ingredients": []}, "Bolognese")
        self.assertEqual(result["ingredients"], "beef mince, spaghetti, salt, red lentils")
        self.assertTrue(result["additional_notes"].startswith("Recipe version: cook the cheapest version"))
        self.assertEqual(preferences["ingredients"], "beef mince, spaghetti, salt")  # original untouched


class SwapNamesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with open("/dev/null", "w") as quiet:
            call_command("load_food_data", stdout=quiet)

    def test_every_new_ingredient_name_matches_its_food(self):
        # When a version is cooked, the AI writes these names into the recipe. If one didn't
        # match ("firm tofu" once didn't), the new recipe's nutrition would be incomplete.
        for swap in load_swaps():
            if swap.to_code:
                with self.subTest(name=swap.to_name):
                    food = resolve_ingredients([IngredientInput(swap.to_name, 100)])[0].food
                    self.assertIsNotNone(food)
                    self.assertEqual(food.food_code, swap.to_code)

    def test_a_version_still_high_in_something_says_so(self):
        resolved, servings = recipe(1)  # bolognese: cheapest keeps it a treat
        cheapest = version(three_ways(resolved, servings, NO_SETTINGS), "cheapest")
        self.assertEqual(cheapest["tag"], "treat")
        self.assertTrue(cheapest["still_high"])


CHICKEN_BOWL = [
    {"name": "chicken breast", "display": "300 g", "grams": 300},
    {"name": "basmati rice", "display": "200 g", "grams": 200},
    {"name": "spinach", "display": "100 g", "grams": 100},
    {"name": "salt", "display": "", "grams": 2},
]


def ai_says(*suggestions):
    return [
        {"from": f, "to": t, "amount": a, "grams_per_100g": g, "note": n}
        for f, t, a, g, n in suggestions
    ]


class AiSwapTests(TestCase):
    """The AI proposes swaps; only those that pass code's checks are used."""

    @classmethod
    def setUpTestData(cls):
        with open("/dev/null", "w") as quiet:
            call_command("load_food_data", stdout=quiet)

    def check(self, raw, preferences=NO_SETTINGS):
        from recipes.swap_suggestion_service import check_suggestions

        resolved = resolve_ingredients([IngredientInput(i["name"], i["grams"]) for i in CHICKEN_BOWL])
        return check_suggestions(raw, resolved, preferences)

    def test_good_suggestions_pass(self):
        swaps, rejected = self.check(ai_says(
            ("chicken breast", "mushrooms", "half", 100, "Brown the mushrooms well."),
            ("salt", "", "less", 0, ""),
        ))
        self.assertEqual(rejected, [])
        self.assertEqual([s.text for s in swaps], ["Swap half the {from} for mushrooms", "Use half the {from}"])
        self.assertEqual({s.source for s in swaps}, {"ai"})
        self.assertEqual(swaps[0].to_code, "13-505")

    def test_each_check_rejects(self):
        swaps, rejected = self.check(ai_says(
            ("lobster", "tofu", "all", 100, ""),                 # not in the recipe
            ("chicken breast", "dragon fruit", "all", 100, ""),  # not in the food data
            ("chicken breast", "chicken breast", "all", 100, ""),  # same food
            ("chicken breast", "tofu", "all", 400, ""),          # silly amount
            ("basmati rice", "brown rice", "most", 100, ""),     # not an allowed amount
        ))
        self.assertEqual(swaps, [])
        self.assertEqual(len(rejected), 5)

    def test_allergies_and_health_claims(self):
        swaps, rejected = self.check(
            ai_says(
                ("chicken breast", "tofu", "half", 100, ""),
                ("basmati rice", "brown rice", "all", 100, "Brown rice will boost your immune system."),
            ),
            {"allergies": "soya", "diet_preferences": []},
        )
        self.assertEqual(rejected[0]["reason"], "Clashes with the user's allergies or diet")
        self.assertEqual(len(swaps), 1)
        self.assertEqual(swaps[0].note, "")  # the claim is dropped, the swap is kept

    @patch("recipes.swap_suggestion_service.ask_ai_for_swaps")
    def test_ai_swaps_join_the_three_versions(self, ask):
        from recipes.insight_service import add_ai_swaps

        ask.return_value = ai_says(("chicken breast", "mushrooms", "half", 100, "Brown the mushrooms well."))
        preferences = dict(NO_SETTINGS, servings=2)
        insights = build_insights({"structure": {"ingredients": CHICKEN_BOWL, "servings": 2}, "warnings": []}, preferences, "")
        before = version(insights["three_ways"], "greenest")["carbon"]

        # Chickpeas (on the list) stay the cheapest swap for the chicken, but the AI's
        # mushrooms are lower in carbon, so they win the greenest version.
        insights = add_ai_swaps(insights, preferences)
        greenest = version(insights["three_ways"], "greenest")
        self.assertEqual(insights["ai_swaps"]["accepted"], 1)
        self.assertIn("Swap half the chicken breast for mushrooms", swap_texts(greenest))
        self.assertEqual(next(s for s in greenest["swaps"] if "mushrooms" in s["text"])["source"], "ai")
        self.assertLess(greenest["carbon"], before)
        self.assertIn("Swap half the chicken breast for tinned chickpeas", swap_texts(version(insights["three_ways"], "cheapest")))

    @patch("recipes.swap_suggestion_service.ask_ai_for_swaps", return_value=None)
    def test_when_the_ai_fails_the_list_versions_stay(self, ask):
        from recipes.insight_service import add_ai_swaps

        preferences = dict(NO_SETTINGS, servings=2)
        insights = build_insights({"structure": {"ingredients": CHICKEN_BOWL, "servings": 2}, "warnings": []}, preferences, "")
        list_only = insights["three_ways"]
        insights = add_ai_swaps(insights, preferences)
        self.assertEqual(insights["three_ways"], list_only)
        self.assertFalse(insights["ai_swaps"]["available"])


CHICKEN_RICE = [("chicken breast", 300), ("basmati rice", 200), ("tomato", 150), ("onion", 100),
                ("green chilli", 10), ("vegetable oil", 15), ("salt", 3), ("water", 400)]


def chicken_rice_insights(**preferences):
    structure = {"ingredients": [{"name": n, "display": "", "grams": g} for n, g in CHICKEN_RICE], "servings": 2}
    return build_insights({"structure": structure, "warnings": []}, dict(NO_SETTINGS, servings=2, **preferences), "")


class ProteinTradeoffTests(TestCase):
    """A swap that lowers protein or fibre says so; High Protein users never lose protein."""

    @classmethod
    def setUpTestData(cls):
        with open("/dev/null", "w") as quiet:
            call_command("load_food_data", stdout=quiet)

    def test_levels_are_recorded_and_words_are_plain(self):
        insights = chicken_rice_insights()
        self.assertEqual(version(insights["three_ways"], "cheapest")["levels"]["protein"], "High")
        self.assertIn("High protein", [b["name"] for b in insights["benefits"]])

    def test_a_drop_in_protein_is_shown_and_blocked_for_high_protein(self):
        from recipes.swap_service import level_drops

        # All the chicken -> chickpeas (an AI-style full swap) takes chicken and rice from High to Good protein.
        resolved = resolve_ingredients([IngredientInput(n, g) for n, g in CHICKEN_RICE])
        before = calculate_for_foods(resolved, 2)
        chickpeas = CofidFood.objects.get(food_code="13-670")
        from recipes.swap_service import Swap
        swap = Swap("18-290", "13-670", 1.0, 1.0, "chickpeas", "Use chickpeas instead of {from}", "", "ai")
        after = calculate_for_foods(apply_swap(resolved, swap, chickpeas), 2)
        drops = level_drops(before, after)
        self.assertTrue(drops and drops[0].startswith("Protein: "), drops)

        full_swap = "Use chickpeas instead of chicken breast"
        everyone = three_ways(resolved, 2, NO_SETTINGS, [swap])
        chosen = next(s for s in version(everyone, "cheapest")["swaps"] if s["text"] == full_swap)
        self.assertEqual(chosen["tradeoffs"], drops)  # shown in red on the card
        self.assertNotIn(full_swap, swap_texts(version(everyone, "healthiest")))  # healthiest never lowers protein

        # With High Protein, the full swap is never used. (Half the chicken for chickpeas
        # keeps protein High, so that one is still allowed.)
        high_protein = three_ways(resolved, 2, dict(NO_SETTINGS, nutrition_goal="High Protein"), [swap])
        for v in high_protein:
            self.assertNotIn(full_swap, swap_texts(v), v["title"])
            self.assertTrue(all(not s["tradeoffs"] or not s["tradeoffs"][0].startswith("Protein") for s in v["swaps"]))

    def test_cooked_version_is_told_exact_amounts_and_checked(self):
        from recipes.views import build_version_preferences

        insights = chicken_rice_insights()
        cheapest = version(insights["three_ways"], "cheapest")
        preferences = build_version_preferences(
            dict(NO_SETTINGS, ingredients="chicken, rice, tomato, onion, chillies", additional_notes="None provided"),
            cheapest, insights, "Chicken rice",
        )
        notes = preferences["additional_notes"]
        self.assertIn("chicken breast (300 g)", notes)
        self.assertIn("Use exactly these amounts for the swapped ingredients: chicken breast 150 g, chickpeas 150 g", notes)
        self.assertNotIn("adjust quantities", notes)
        self.assertEqual(preferences["expected"]["levels"]["protein"], "High")

        # If the AI then writes less chicken, the page says protein came out lower than the card.
        lighter = [{"name": "chicken breast", "display": "", "grams": 80}, {"name": "chickpeas", "display": "", "grams": 80},
                   {"name": "basmati rice", "display": "", "grams": 300}, {"name": "vegetable oil", "display": "", "grams": 40}]
        cooked = build_insights({"structure": {"ingredients": lighter, "servings": 2}, "warnings": []}, preferences, "")
        self.assertEqual(cooked["basis"]["version"], "Cheapest")
        self.assertTrue(cooked["basis"]["problems"])
        self.assertIn("Protein came out", cooked["basis"]["problems"][0])
