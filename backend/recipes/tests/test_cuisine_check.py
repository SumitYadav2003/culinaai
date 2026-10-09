"""
Cuisine check (cuisine_service.py): signature ingredients from Ahn et al. (2011),
how recipe ingredients are matched, diet-aware scoring, and the retry through
the real generate view (AI calls mocked).
"""

import csv
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from recipes.cuisine_service import (
    DATA_DIR,
    WORDS,
    cuisine_check,
    cuisine_correction,
    ingredients_section,
    load_regions,
    region_for,
    study_ingredient,
)
from recipes.models import Cuisine, RecipeHistory
from recipes.tests.test_generation_flow import FORM
from recipes.tests.test_insights_and_gates import RECIPE_TEXT, burger_structure

THAI = ["chicken thigh", "fish sauce", "lemongrass", "lime", "fresh coriander", "jasmine rice", "coconut milk",
        "garlic", "red chilli"]


class DataTests(SimpleTestCase):
    def test_eleven_regions_and_every_signature_has_words(self):
        regions = load_regions()
        self.assertEqual(len(regions), 11)
        self.assertEqual(sum(r["recipes"] for r in regions.values()), 56498)
        for region, info in regions.items():
            self.assertTrue(info["signature"], region)
            for name in info["signature"]:
                self.assertIn(name, WORDS, f"{name} ({region}) has no matching rule")

    def test_north_american_is_the_only_region_not_checked(self):
        unchecked = [region for region, info in load_regions().items() if not info["checked"]]
        self.assertEqual(unchecked, ["NorthAmerican"])

    def test_held_out_and_real_recipe_figures_are_stored(self):
        with open(DATA_DIR / "cuisine_regions.csv", newline="") as handle:
            rows = {row["region"]: row for row in csv.DictReader(handle)}
        self.assertEqual(rows["SoutheastAsian"]["heldout_own_2plus"], "0.881")
        self.assertGreater(float(rows["EastAsian"]["gap"]), 0.5)
        # Real Southeast Asian recipes mostly use 3 to 6 of its 12 signature ingredients, typically 4.
        southeast = load_regions()["SoutheastAsian"]
        self.assertEqual((southeast["real_low"], southeast["real_typical"], southeast["real_high"]), (3, 4, 6))


class MatchingTests(SimpleTestCase):
    def test_regions(self):
        cases = {"Thai": "SoutheastAsian", "Italian": "SouthernEuropean", "Indian": "SouthAsian",
                 "Mexican": "LatinAmerican", "Chinese": "EastAsian", "Latin American": "LatinAmerican",
                 "Moroccan": "African", "British": "WesternEuropean", "American": "NorthAmerican",
                 "Fusion": None, "Russian": "EasternEuropean"}
        for cuisine, region in cases.items():
            self.assertEqual(region_for(cuisine), region, cuisine)

    def test_ingredient_words(self):
        cases = {
            "coconut milk": "coconut", "almond milk": None, "peanut butter": None, "cornflour": None,
            "fresh coriander": "cilantro", "ground coriander": "coriander", "spring onions": "scallion",
            "red pepper, sliced": "bell_pepper", "red chilli flakes": "cayenne", "rice vinegar": None,
            "kaffir lime leaves": None, "juice of 1 lime": "lime_juice", "plain flour": "wheat",
            "gram flour": None, "spaghetti": "macaroni", "firm tofu": "soybean", "ghee": "butter",
            "sweet potato": None, "potatoes": "potato", "double cream": "cream", "greek yoghurt": "yogurt",
        }
        for name, expected in cases.items():
            self.assertEqual(study_ingredient(name), expected, name)

    def test_ingredients_from_recipe_text(self):
        self.assertEqual(ingredients_section(RECIPE_TEXT)[0], "2 chicken breasts (300 g)")


class CheckTests(SimpleTestCase):
    def test_levels_compare_with_real_recipes(self):
        # Real Southeast Asian recipes: most use 3 to 6 signature ingredients, typically 4.
        very = cuisine_check({"cuisine": "Thai"}, THAI)
        self.assertEqual((very["level"], very["usable"]), ("very", 12))
        self.assertIn("Very typical of Thai cooking: uses 8 of its signature ingredients", very["text"])
        self.assertIn("more than most Southeast Asian recipes in the study (most use 3 to 6).", very["text"])
        self.assertFalse(very["retry"])

        same = cuisine_check({"cuisine": "Thai"}, ["fish sauce", "jasmine rice", "lime", "garlic", "broccoli"])
        self.assertEqual(same["level"], "typical")
        self.assertIn("the same as a typical Southeast Asian recipe in the study", same["text"])

        fewer = cuisine_check({"cuisine": "Thai"}, ["chicken", "garlic", "ginger", "broccoli"])
        self.assertEqual((fewer["level"], fewer["retry"]), ("less", False))  # 2 is below 3, but not retried
        self.assertIn("fewer than most Southeast Asian recipes", fewer["text"])

        none = cuisine_check({"cuisine": "Italian"}, ["chicken breast", "soy sauce", "broccoli"])
        self.assertEqual((none["level"], none["retry"]), ("less", True))
        self.assertIn("Less typical of Italian cooking: uses none of its signature ingredients", none["text"])
        self.assertIn("Typical ones include olive oil, parmesan, basil.", none["text"])

    def test_curry_paste_counts_as_chilli(self):
        self.assertEqual(study_ingredient("Thai green curry paste"), "cayenne")

    def test_diet_and_allergies_are_respected(self):
        vegan = cuisine_check({"cuisine": "Thai", "diet_preferences": ["Vegan"], "allergies": "None provided"},
                              ["tofu", "soy sauce", "garlic", "lime"])
        self.assertEqual(vegan["excluded"], ["fish or fish sauce"])
        self.assertEqual(vegan["usable"], 11)
        self.assertEqual(vegan["level"], "typical")  # 3 found: within real recipes' 3 to 6

        avoid = cuisine_check({"cuisine": "Italian", "allergies": "tomato, mushrooms"}, ["olive oil"])
        self.assertIn("tomato", avoid["excluded"])

        eggs_ok = cuisine_check({"cuisine": "British", "diet_preferences": ["Eggetarian"]}, ["egg", "butter"])
        self.assertNotIn("eggs", eggs_ok["excluded"])

    def test_not_checked_and_no_cuisine(self):
        self.assertIsNone(cuisine_check({"cuisine": "Any cuisine"}, THAI))
        self.assertIsNone(cuisine_check({}, THAI))
        american = cuisine_check({"cuisine": "American"}, ["beef mince"])
        self.assertFalse(american["available"])
        self.assertIn("can't reliably tell the cuisine apart", american["text"])
        self.assertFalse(cuisine_check({"cuisine": "Fusion"}, THAI)["available"])

    def test_correction_only_when_retried(self):
        weak = cuisine_check({"cuisine": "Italian"}, ["chicken breast", "soy sauce"])
        note = cuisine_correction({"cuisine": weak})
        self.assertIn("The user asked for Italian food", note)
        self.assertIn("olive oil, parmesan, basil, pasta, tomato", note)
        self.assertEqual(cuisine_correction({"cuisine": cuisine_check({"cuisine": "Thai"}, THAI)}), "")
        self.assertEqual(cuisine_correction({}), "")


def structure(names):
    data = burger_structure([])
    data["ingredients"] = [{"name": name, "display": "100 g", "grams": 100} for name in names]
    return {"structure": data, "warnings": []}


class CuisineFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with open("/dev/null", "w") as quiet:
            call_command("load_food_data", stdout=quiet)
        cls.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        cls.thai = Cuisine.objects.create(name="Thai")

    def setUp(self):
        self.client.force_login(self.user)
        ai_swaps = patch("recipes.swap_suggestion_service.ask_ai_for_swaps", return_value=None)
        ai_swaps.start()
        self.addCleanup(ai_swaps.stop)

    @patch("recipes.views.generate_recipe_image_base64", side_effect=RuntimeError("images off in tests"))
    @patch("recipes.views.extract_recipe_structure",
           side_effect=[structure(["chicken breast", "burger bun", "tomato"]), structure(THAI)])
    @patch("recipes.views.generate_ai_recipe")
    def test_a_loosely_thai_recipe_is_retried_once(self, generate, extract, image):
        generate.side_effect = [
            {"prompt": "p1", "recipe_text": RECIPE_TEXT},
            {"prompt": "p2", "recipe_text": RECIPE_TEXT},
        ]
        html = self.client.post(reverse("generate_recipe"), dict(FORM, cuisine=self.thai.id), follow=True).content.decode()

        self.assertEqual(generate.call_count, 2)
        retry_notes = generate.call_args_list[1].args[0]["additional_notes"]
        self.assertIn("Cuisine: The user asked for Thai food", retry_notes)
        self.assertIn("fish or fish sauce", retry_notes)

        cuisine = RecipeHistory.objects.get(user=self.user).insights["cuisine"]
        self.assertEqual(cuisine["level"], "very")
        self.assertIn("Cuisine check:", html)
        self.assertIn("Very typical of Thai cooking", html)
        self.assertIn("457 real\n                        Southeast Asian recipes", html)

    @patch("recipes.views.generate_recipe_image_base64", side_effect=RuntimeError("images off in tests"))
    @patch("recipes.views.extract_recipe_structure", return_value=structure(THAI))
    @patch("recipes.views.generate_ai_recipe", return_value={"prompt": "p", "recipe_text": RECIPE_TEXT})
    def test_a_typical_recipe_is_not_retried(self, generate, extract, image):
        self.client.post(reverse("generate_recipe"), dict(FORM, cuisine=self.thai.id), follow=True)
        self.assertEqual(generate.call_count, 1)


# Well-known dishes, with ingredient names written the way a recipe would list them.
CLASSIC_DISHES = [
    ("Thai", "green curry", "typical", ["boneless chicken thighs", "Thai green curry paste", "coconut milk",
                                        "fish sauce", "palm sugar", "kaffir lime leaves", "Thai basil", "green beans",
                                        "vegetable oil", "jasmine rice"]),
    ("Thai", "pad thai", "typical", ["flat rice noodles", "prawns", "eggs", "tamarind paste", "fish sauce",
                                     "brown sugar", "garlic", "spring onions", "bean sprouts", "roasted peanuts",
                                     "lime wedges"]),
    ("Italian", "carbonara", "typical", ["spaghetti", "pancetta", "eggs", "pecorino romano", "black pepper", "salt"]),
    ("Italian", "mushroom risotto", "typical", ["arborio rice", "chicken stock", "onion", "white wine", "butter",
                                                "parmesan", "mushrooms", "olive oil"]),
    ("Indian", "chana masala", "typical", ["chickpeas", "onion", "tomatoes", "ginger garlic paste", "green chilli",
                                           "cumin seeds", "ground coriander", "turmeric powder", "garam masala",
                                           "fresh coriander", "vegetable oil"]),
    ("Indian", "butter chicken", "typical", ["chicken breast", "yoghurt", "ginger", "garlic",
                                             "kashmiri chilli powder", "garam masala", "butter", "double cream",
                                             "tomato puree", "kasuri methi"]),
    ("Mexican", "chicken tacos", "very", ["chicken breast", "corn tortillas", "red onion", "fresh coriander",
                                             "lime", "avocado", "jalapeño", "cumin", "smoked paprika",
                                             "sour cream"]),
    ("Chinese", "egg fried rice", "typical", ["cooked rice", "eggs", "spring onions", "soy sauce", "sesame oil",
                                              "frozen peas", "garlic", "vegetable oil"]),
    ("Japanese", "teriyaki salmon", "very", ["salmon fillets", "soy sauce", "mirin", "honey", "ginger", "garlic",
                                                "sesame seeds", "spring onions", "steamed rice"]),
    ("Moroccan", "chicken tagine", "very", ["chicken thighs", "onion", "garlic", "ground cumin",
                                               "ground cinnamon", "ground ginger", "preserved lemon", "green olives",
                                               "chicken stock", "fresh coriander", "olive oil"]),
    ("Greek", "greek salad", "typical", ["tomatoes", "cucumber", "red onion", "feta", "kalamata olives",
                                         "dried oregano", "olive oil", "red wine vinegar"]),
    ("British", "shepherd's pie", "typical", ["lamb mince", "onion", "carrot", "peas", "worcestershire sauce",
                                              "beef stock", "potatoes", "butter", "milk", "thyme"]),
    # A spaghetti bolognese labelled Thai should be caught and retried.
    ("Thai", "bolognese labelled Thai", "less", ["spaghetti", "beef mince", "chopped tomatoes", "onion", "garlic",
                                                  "oregano", "parmesan"]),
]


class ClassicDishesTests(SimpleTestCase):
    def test_well_known_dishes(self):
        for cuisine, dish, level, ingredients in CLASSIC_DISHES:
            with self.subTest(dish=dish):
                result = cuisine_check({"cuisine": cuisine}, ingredients)
                self.assertEqual(result["level"], level, f"{dish}: {result['found']}")
                self.assertEqual(result["retry"], dish == "bolognese labelled Thai")
