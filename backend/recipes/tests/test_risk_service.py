"""Rule-based allergen and safety flags (risk_service.py). No AI involved."""

from django.test import SimpleTestCase

from recipes.ai_service import build_avoidance_terms
from recipes.risk_service import (
    ALLERGEN_KEYWORDS,
    allergens_in,
    hidden_allergen_alerts,
    hidden_products_for_allergies,
    nutrition_flags,
    safety_flags,
)

# One everyday ingredient for each of the UK's 14 allergens.
ONE_PER_ALLERGEN = {
    "Celery": "celery",
    "Cereals containing gluten": "plain flour",
    "Crustaceans": "king prawn",
    "Eggs": "eggs",
    "Fish": "salmon fillet",
    "Lupin": "lupin flour",
    "Milk": "cheddar cheese",
    "Molluscs": "mussels",
    "Mustard": "dijon mustard",
    "Peanuts": "peanuts",
    "Sesame": "sesame oil",
    "Soya": "tofu",
    "Sulphur dioxide and sulphites": "red wine",
    "Tree nuts": "cashew nuts",
}


class AllergenTests(SimpleTestCase):
    def test_all_fourteen_allergens_are_covered(self):
        self.assertEqual(len(ALLERGEN_KEYWORDS), 14)
        self.assertEqual(set(ONE_PER_ALLERGEN), set(ALLERGEN_KEYWORDS))

    def test_each_allergen_is_found_from_a_common_ingredient(self):
        for allergen, ingredient in ONE_PER_ALLERGEN.items():
            with self.subTest(allergen=allergen):
                self.assertIn(allergen, allergens_in([ingredient]))

    def test_oats_count_as_a_cereal_containing_gluten(self):
        self.assertIn("Cereals containing gluten", allergens_in(["oat drink"]))

    def test_names_that_only_look_like_an_allergen(self):
        found = allergens_in(["coconut milk", "peanut butter", "butter beans", "rice noodles",
                              "aubergine", "eggplant", "butternut squash", "coconut", "chickpeas"])
        self.assertNotIn("Milk", found)
        self.assertNotIn("Eggs", found)
        self.assertNotIn("Tree nuts", found)
        self.assertEqual(found.get("Peanuts"), ["peanut butter"])
        self.assertEqual(found.get("Cereals containing gluten"), None)

    def test_the_matched_food_name_is_checked_too(self):
        found = allergens_in(["burger bun"], {"burger bun": "Bread rolls, white, crusty"})
        self.assertEqual(found, {"Cereals containing gluten": ["burger bun"]})

    def test_soya_milk_from_cofid_is_not_cows_milk(self):
        found = allergens_in(["soya milk"], {"soya milk": "Milk, soya, non-dairy alternative to milk, unsweetened, fortified"})
        self.assertNotIn("Milk", found)
        self.assertIn("Soya", found)

    def test_quorn_and_naan_have_hidden_allergen_alerts(self):
        allergens = [alert["allergen"] for alert in hidden_allergen_alerts(["quorn pieces", "naan bread"])]
        self.assertEqual(allergens, ["Eggs", "Milk"])

    def test_almond_milk_is_a_tree_nut_but_not_milk(self):
        found = allergens_in(["almond milk"])
        self.assertIn("Tree nuts", found)
        self.assertNotIn("Milk", found)


class HiddenAllergenTests(SimpleTestCase):
    def test_hidden_allergen_products(self):
        cases = {
            "worcestershire sauce": "Fish",
            "green pesto": "Milk",
            "chicken stock cube": "Celery",
            "gravy granules": "Cereals containing gluten",
            "soy sauce": "Cereals containing gluten",
            "oyster sauce": "Molluscs",
            "thai red curry paste": "Crustaceans",
            "marzipan": "Tree nuts",
            "pork sausages": "Cereals containing gluten",
            "malt vinegar": "Cereals containing gluten",
        }
        for product, allergen in cases.items():
            with self.subTest(product=product):
                alerts = hidden_allergen_alerts([product])
                self.assertIn(allergen, [alert["allergen"] for alert in alerts])
                self.assertTrue(all(alert["text"].endswith("Check the label.") for alert in alerts))

    def test_stock_cube_alerts_are_not_doubled(self):
        alerts = hidden_allergen_alerts(["vegetable stock cube"])
        self.assertEqual(len(alerts), 2)  # celery and gluten, once each

    def test_wording_says_usually_or_often(self):
        for alert in hidden_allergen_alerts(["worcestershire sauce", "pesto", "stock cube"]):
            with self.subTest(text=alert["text"]):
                self.assertTrue(any(word in alert["text"] for word in ["usually", "often", "Many"]))

    def test_a_fish_allergy_avoids_worcestershire_sauce_in_the_prompt(self):
        self.assertIn("worcestershire sauce", build_avoidance_terms("fish"))
        self.assertIn("worcestershire sauce", hidden_products_for_allergies("Fish allergy"))

    def test_a_peanut_allergy_is_not_read_as_a_tree_nut_allergy(self):
        self.assertNotIn("pesto", hidden_products_for_allergies("peanut"))
        self.assertIn("pesto", hidden_products_for_allergies("tree nuts"))

    def test_plain_stock_and_sausages_are_not_banned_for_gluten_free_users(self):
        products = hidden_products_for_allergies("gluten")
        self.assertIn("stock cube", products)
        self.assertIn("malt vinegar", products)
        self.assertNotIn("stock", products)
        self.assertNotIn("sausage", products)


class SafetyFlagTests(SimpleTestCase):
    def codes(self, names, text=""):
        return [flag["code"] for flag in safety_flags(names, text)]

    def test_chicken_and_mince_need_thorough_cooking(self):
        self.assertIn("cook_thoroughly", self.codes(["chicken breast"]))
        self.assertIn("cook_thoroughly", self.codes(["beef mince"]))
        self.assertIn("cook_thoroughly", self.codes(["pork sausages"]))

    def test_tofu_and_steak_do_not(self):
        self.assertNotIn("cook_thoroughly", self.codes(["tofu"]))
        self.assertNotIn("cook_thoroughly", self.codes(["sirloin steak"]))

    def test_lightly_cooked_egg(self):
        self.assertIn("lightly_cooked_egg", self.codes(["eggs", "spaghetti"], "Carbonara: toss with the eggs off the heat"))
        self.assertNotIn("lightly_cooked_egg", self.codes(["eggs"], "Bake the cake for 30 minutes"))

    def test_high_in_and_incomplete_flags(self):
        nutrition = {
            "traffic_lights": {"fat_g": "green", "saturates_g": "amber", "sugars_g": "green", "salt_g": "red"},
            "per_serving": {"salt_g": 2.4},
            "percent_reference_intake": {"salt_g": 40},
            "coverage_pct": 70.0,
            "unmatched": ["dragon fruit"],
        }
        flags = {flag["code"]: flag for flag in nutrition_flags(nutrition)}
        self.assertEqual(set(flags), {"high_salt_g", "nutrition_incomplete"})
        self.assertEqual(flags["high_salt_g"]["text"], "2.4 g per serving, 40% of an adult's reference intake.")
        self.assertIn("dragon fruit", flags["nutrition_incomplete"]["text"])
