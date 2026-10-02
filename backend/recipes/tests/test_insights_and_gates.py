"""
"Compared with the classic", quality gates 9 and 10, the allergy-gate
exception and the full insights dict. Uses the real food data; no AI calls.
"""

from django.core.management import call_command
from django.test import TestCase

from recipes.classic_service import compare_with_classic
from recipes.insight_service import build_insights
from recipes.recipe_quality_engine import GATE_WEIGHTS, check_health_claims, validate_recipe_output

RECIPE_TEXT = """
RECIPE TITLE:
Grilled Chicken Burger with Garlic Yogurt

SHORT DESCRIPTION:
A quick chicken burger with a light garlic yogurt sauce.

INGREDIENTS WITH QUANTITIES:
- 2 chicken breasts (300 g)
- 2 burger buns
- 1 tomato, sliced
- 100 g Greek yogurt

COOKING TIME:
25 minutes

SERVINGS:
2

DIFFICULTY:
Easy

STEPS:
1. Season the chicken and cook in a pan for 12 minutes until cooked through.
2. Mix the yogurt with a little garlic.
3. Toast the buns, add the chicken, tomato and sauce.

ALLERGY AND DIET NOTES:
The user-provided restricted ingredients have been excluded from this recipe.
"""

PREFERENCES = {
    "ingredients": "chicken breast, burger bun, tomato, greek yogurt",
    "cuisine": "American",
    "meal_type": "Dinner",
    "diet_preferences": [],
    "allergies": "None provided",
    "cooking_time_minutes": 30,
    "servings": 2,
    "difficulty": "easy",
    "budget_level": "Moderate Budget",
    "nutrition_goal": "Balanced",
    "cooking_equipment": ["Stove"],
}


def burger_structure(missing, core=None):
    # Unless a test says otherwise, mayonnaise has a valid reason (a real healthier swap),
    # so each test only exercises the item it is about.
    if not core and not any(m["ingredient"] == "mayonnaise" for m in missing):
        missing = missing + [suggestion("mayonnaise", "healthier_swap", "greek yogurt")]
    return {
        "ingredients": [
            {"name": "chicken breast", "display": "2", "grams": 300},
            {"name": "burger bun", "display": "2", "grams": 120},
            {"name": "tomato", "display": "1", "grams": 80},
            {"name": "greek yogurt", "display": "100 g", "grams": 100},
        ],
        "ai_kcal_per_serving": 450,
        "classic": {
            "is_classic": True,
            "classic_name": "Chicken burger",
            "core_ingredients": core or ["chicken breast", "burger bun", "lettuce", "mayonnaise"],
            "usual_minutes": 30,
            "missing": missing,
        },
    }


def suggestion(ingredient, reason, replaced_with="", equipment="", note=""):
    return {"ingredient": ingredient, "reason": reason, "replaced_with": replaced_with,
            "equipment": equipment, "note": note}


class FoodDataTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        with open("/dev/null", "w") as quiet:
            call_command("load_food_data", stdout=quiet)


class CompareWithClassicTests(FoodDataTestCase):
    def items(self, structure, preferences=PREFERENCES):
        result = compare_with_classic(structure, preferences)
        return {item["ingredient"]: item for item in result["items"]}, result["issues"]

    def test_missing_items_are_found_by_code(self):
        items, _ = self.items(burger_structure([suggestion("lettuce", "not_in_your_ingredients")]))
        self.assertEqual(set(items), {"lettuce", "mayonnaise"})  # chicken and bun are present

    def test_lettuce_removed_for_health_fails_because_nothing_got_healthier(self):
        items, issues = self.items(burger_structure([suggestion("lettuce", "healthier_swap")]))
        self.assertEqual([issue["ingredient"] for issue in issues], ["lettuce"])
        self.assertEqual(items["lettuce"]["reason"], "not_in_your_ingredients")  # what code can prove

    def test_lettuce_not_in_your_ingredients_passes(self):
        items, issues = self.items(burger_structure([suggestion("lettuce", "not_in_your_ingredients")]))
        self.assertEqual(issues, [])
        self.assertEqual(items["lettuce"]["label"], "Not in your ingredients")

    def test_not_in_your_ingredients_fails_if_the_user_had_it(self):
        preferences = dict(PREFERENCES, ingredients="chicken breast, burger bun, lettuce")
        items, issues = self.items(burger_structure([suggestion("lettuce", "not_in_your_ingredients")]), preferences)
        self.assertEqual(len(issues), 1)
        self.assertEqual(items["lettuce"]["reason"], "none_given")

    def test_mayonnaise_to_greek_yogurt_is_a_real_healthier_swap(self):
        items, issues = self.items(burger_structure([suggestion("mayonnaise", "healthier_swap", "greek yogurt")]))
        self.assertNotIn("mayonnaise", [issue["ingredient"] for issue in issues])
        self.assertIn("lower in", items["mayonnaise"]["detail"])
        self.assertIn("fat", items["mayonnaise"]["detail"])

    def test_equipment_time_and_budget_rules(self):
        cases = [
            (suggestion("mayonnaise", "equipment", equipment="deep fryer"), PREFERENCES, True),
            (suggestion("mayonnaise", "equipment", equipment="stove"), PREFERENCES, False),
            (suggestion("mayonnaise", "time_limit"), dict(PREFERENCES, cooking_time_minutes=20), True),
            (suggestion("mayonnaise", "time_limit"), dict(PREFERENCES, cooking_time_minutes=45), False),
            (suggestion("mayonnaise", "budget"), dict(PREFERENCES, budget_level="Low Budget"), True),
            (suggestion("mayonnaise", "budget"), PREFERENCES, False),
        ]
        for case, preferences, should_pass in cases:
            with self.subTest(reason=case["reason"], should_pass=should_pass):
                _, issues = self.items(burger_structure([case]), preferences)
                failed = "mayonnaise" in [issue["ingredient"] for issue in issues]
                self.assertEqual(not failed, should_pass)

    def test_not_a_classic_shows_nothing(self):
        structure = burger_structure([])
        structure["classic"]["is_classic"] = False
        self.assertEqual(compare_with_classic(structure, PREFERENCES)["items"], [])


class AllergyExceptionTests(FoodDataTestCase):
    """The classic section may name an allergen only to say it was left out for the allergy."""

    preferences = dict(PREFERENCES, allergies="peanut")

    def satay(self, ai_reason):
        structure = burger_structure(
            [
                suggestion("peanut butter", ai_reason),
                suggestion("soy sauce", "not_in_your_ingredients"),
                suggestion("coconut milk", "not_in_your_ingredients"),
            ],
            core=["chicken breast", "peanut butter", "soy sauce", "coconut milk"],
        )
        structure["classic"]["classic_name"] = "Chicken satay"
        return structure

    def test_peanut_named_in_the_classic_section_with_the_allergy_reason_passes(self):
        insights = build_insights({"structure": self.satay("allergy_diet")}, self.preferences, RECIPE_TEXT)
        item = next(i for i in insights["classic"]["items"] if i["ingredient"] == "peanut butter")
        self.assertEqual(item["reason"], "allergy_diet")
        self.assertFalse(item["can_add_back"])
        report = validate_recipe_output(self.preferences, RECIPE_TEXT, insights=insights)
        checks = {check["name"]: check for check in report["checks"]}
        self.assertTrue(checks["Allergy Safety"]["passed"])
        self.assertTrue(checks["Explanation Consistency"]["passed"])

    def test_peanut_in_the_ingredients_still_fails(self):
        text = RECIPE_TEXT.replace("- 1 tomato, sliced", "- 2 tbsp peanut butter")
        report = validate_recipe_output(self.preferences, text)
        checks = {check["name"]: check for check in report["checks"]}
        self.assertFalse(checks["Allergy Safety"]["passed"])
        self.assertTrue(report["hard_fail"])

    def test_peanut_with_any_other_reason_is_still_shown_as_the_allergy(self):
        insights = build_insights({"structure": self.satay("style_choice")}, self.preferences, RECIPE_TEXT)
        item = next(i for i in insights["classic"]["items"] if i["ingredient"] == "peanut butter")
        self.assertEqual(item["reason"], "allergy_diet")


class GateTests(FoodDataTestCase):
    def test_weights_add_up_to_100(self):
        self.assertEqual(sum(GATE_WEIGHTS.values()), 100)
        report = validate_recipe_output(PREFERENCES, RECIPE_TEXT)
        self.assertEqual(len(report["checks"]), 10)
        self.assertEqual(sum(check["max_score"] for check in report["checks"]), 100)
        self.assertLessEqual(report["score"], 100)

    def test_gate_9_rejects_medical_claims(self):
        for phrase in ["Garlic boosts immunity.", "A detox bowl.", "This superfood salad.", "Helps prevent heart disease."]:
            with self.subTest(phrase=phrase):
                check = check_health_claims(RECIPE_TEXT + phrase)
                self.assertFalse(check["passed"])
                self.assertEqual(check["severity"], "critical")

    def test_gate_9_allows_ordinary_cooking_words(self):
        check = check_health_claims(RECIPE_TEXT + "Stir to prevent sticking. A sweet treat for the weekend.")
        self.assertTrue(check["passed"])

    def test_gate_9_also_reads_the_classic_reasons(self):
        structure = burger_structure([suggestion("mayonnaise", "style_choice", note="Left out because it cures colds")])
        insights = build_insights({"structure": structure}, PREFERENCES, RECIPE_TEXT)
        self.assertFalse(check_health_claims(RECIPE_TEXT, insights)["passed"])

    def test_gate_10_lowers_the_score_for_an_unconfirmed_reason(self):
        good = build_insights({"structure": burger_structure([
            suggestion("lettuce", "not_in_your_ingredients"),
            suggestion("mayonnaise", "healthier_swap", "greek yogurt"),
        ])}, PREFERENCES, RECIPE_TEXT)
        bad = build_insights({"structure": burger_structure([
            suggestion("lettuce", "healthier_swap"),
            suggestion("mayonnaise", "healthier_swap", "greek yogurt"),
        ])}, PREFERENCES, RECIPE_TEXT)
        good_report = validate_recipe_output(PREFERENCES, RECIPE_TEXT, insights=good)
        bad_report = validate_recipe_output(PREFERENCES, RECIPE_TEXT, insights=bad)
        gate = {c["name"]: c for c in bad_report["checks"]}["Explanation Consistency"]
        self.assertFalse(gate["passed"])
        self.assertEqual(gate["severity"], "major")
        self.assertEqual(good_report["score"] - bad_report["score"], 5)
        self.assertIn("classic ingredient", bad_report["correction_prompt"])

    def test_gate_10_is_not_applied_without_structured_data(self):
        report = validate_recipe_output(PREFERENCES, RECIPE_TEXT)
        gate = {c["name"]: c for c in report["checks"]}["Explanation Consistency"]
        self.assertTrue(gate["passed"])
        self.assertIn("not applied", gate["message"])


class BuildInsightsTests(FoodDataTestCase):
    def dal(self):
        return {"structure": {
            "ingredients": [
                {"name": "red lentils", "display": "250 g", "grams": 250},
                {"name": "onion", "display": "1", "grams": 150},
                {"name": "chopped tomatoes", "display": "200 g", "grams": 200},
                {"name": "garlic", "display": "2 cloves", "grams": 10},
                {"name": "ginger", "display": "1 tbsp", "grams": 10},
                {"name": "turmeric", "display": "1 tsp", "grams": 5},
                {"name": "cumin", "display": "1 tsp", "grams": 5},
                {"name": "ghee", "display": "1 tbsp", "grams": 20},
                {"name": "water", "display": "900 ml", "grams": 900},
            ],
            "ai_kcal_per_serving": 300,
            "classic": {"is_classic": False, "classic_name": "", "core_ingredients": [], "usual_minutes": None,
                        "missing": []},
        }}

    def test_dal_end_to_end(self):
        insights = build_insights(self.dal(), dict(PREFERENCES, servings=4), "Simmer the lentils.")
        self.assertTrue(insights["available"])
        self.assertAlmostEqual(insights["nutrition"]["per_serving"]["energy_kcal"], 264.45, places=1)
        self.assertEqual(insights["tag"], "everyday")
        self.assertIn("Low sugars", [b["claim"] for b in insights["benefits"]])
        self.assertAlmostEqual(insights["cost"]["per_serving"], 0.56)
        self.assertAlmostEqual(insights["carbon"]["per_serving"], 0.236, places=3)
        self.assertEqual(insights["ai_kcal_per_serving"], 300)
        self.assertIn("Milk", insights["allergens"])  # ghee
        self.assertFalse(insights["classic"]["is_classic"])

    def test_a_rich_dish_is_a_treat(self):
        structure = self.dal()
        structure["structure"]["ingredients"] = [
            {"name": "butter", "display": "", "grams": 200},
            {"name": "sugar", "display": "", "grams": 200},
            {"name": "plain flour", "display": "", "grams": 200},
        ]
        insights = build_insights(structure, PREFERENCES, "")
        self.assertEqual(insights["tag"], "treat")
        self.assertIn("high_fat_g", [flag["code"] for flag in insights["flags"]])
        self.assertEqual(insights["benefits"], [])

    def test_incomplete_nutrition_gives_no_tag_and_no_benefits(self):
        structure = self.dal()
        structure["structure"]["ingredients"].append({"name": "dragon fruit", "display": "", "grams": 2000})
        insights = build_insights(structure, PREFERENCES, "")
        self.assertIsNone(insights["tag"])
        self.assertEqual(insights["benefits"], [])
        self.assertIn("nutrition_incomplete", [flag["code"] for flag in insights["flags"]])

    def test_no_structure_means_not_available(self):
        insights = build_insights(None, PREFERENCES, RECIPE_TEXT)
        self.assertFalse(insights["available"])
        self.assertTrue(insights["disclaimer"])
