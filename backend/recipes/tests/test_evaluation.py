"""
Phase 5 evaluation: the numbers (evaluation_service.py), the benchmark command
(AI calls mocked) and the report written by `manage.py evaluate`.
"""

import csv
import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from recipes import evaluation_service as ev
from recipes.management.commands.run_benchmark import CASES_FILE, load_cases, preview_data_for
from recipes.models import CookingSession, CookingStepRecord, RecipeHistory
from recipes.risk_service import allergens_for_user_allergies, hidden_products_for_allergies
from recipes.tests.test_cuisine_check import THAI, structure
from recipes.tests.test_generation_flow import FORM
from recipes.tests.test_insights_and_gates import RECIPE_TEXT


def row(insights=None, allergies="", diets=None, history=None, attempts=1, score=90):
    return {
        "id": 1, "insights": insights or {}, "attempts": attempts, "attempt_history": history or [],
        "quality_score": score, "allergies": allergies, "diets": diets or [], "cuisine": "",
    }


def ingredients(*names):
    return {"available": True, "ingredients": [{"name": name} for name in names]}


class SusTests(SimpleTestCase):
    def test_standard_scoring(self):
        best = {f"sus{n}": 5 if n % 2 else 1 for n in range(1, 11)}
        worst = {f"sus{n}": 1 if n % 2 else 5 for n in range(1, 11)}
        neutral = {f"sus{n}": 3 for n in range(1, 11)}
        mostly_agree = {f"sus{n}": 4 if n % 2 else 2 for n in range(1, 11)}
        self.assertEqual(ev.sus_score(best), 100)
        self.assertEqual(ev.sus_score(worst), 0)
        self.assertEqual(ev.sus_score(neutral), 50)
        self.assertEqual(ev.sus_score(mostly_agree), 75)

    def test_incomplete_or_invalid_answers_are_not_scored(self):
        answers = {f"sus{n}": 3 for n in range(1, 11)}
        self.assertIsNone(ev.sus_score(dict(answers, sus4="")))
        self.assertIsNone(ev.sus_score(dict(answers, sus7="6")))
        self.assertIsNone(ev.sus_score(dict(answers, sus1="agree")))

    def test_grades(self):
        self.assertEqual(ev.sus_grade(90), "excellent")
        self.assertEqual(ev.sus_grade(75), "good")
        self.assertEqual(ev.sus_grade(68), "OK")
        self.assertEqual(ev.sus_grade(20), "awful")
        self.assertEqual(ev.sus_grade(None), "")
        self.assertEqual(ev.sus_against_average(75), "above the usual average of 68")
        self.assertEqual(ev.sus_against_average(50), "below the usual average of 68")

    def test_study_summary(self):
        rows = [
            dict({f"sus{n}": 4 if n % 2 else 2 for n in range(1, 11)}, f_voice="4",
                 voice_commands_tried="10", voice_commands_understood="8"),
            dict({f"sus{n}": 5 if n % 2 else 1 for n in range(1, 11)}, f_voice="5",
                 voice_commands_tried="10", voice_commands_understood="10"),
            {"participant": "P3", "f_voice": ""},  # didn't finish
        ]
        study = ev.study_summary(rows)
        self.assertEqual((study["participants"], study["sus_scores"], study["sus_mean"]), (3, 2, 87.5))
        self.assertEqual(study["features"]["f_voice"], {"answers": 2, "mean": 4.5})
        self.assertEqual(study["voice_pct"], 90.0)


class SafetyCrossCheckTests(SimpleTestCase):
    def test_allergen_found_in_ingredients(self):
        insights = dict(ingredients("peanut butter", "rice"), allergens={"Peanuts": ["peanut butter"]})
        self.assertEqual(ev.allergy_check(row(insights, allergies="peanuts")), {"found": ["Peanuts"], "label": []})

    def test_check_the_label_is_kept_apart(self):
        insights = dict(ingredients("soy sauce"), allergens={},
                        hidden_allergens=[{"product": "soy sauce", "allergen": "Cereals containing gluten"}])
        result = ev.allergy_check(row(insights, allergies="gluten"))
        self.assertEqual(result, {"found": [], "label": ["Cereals containing gluten"]})

    def test_only_declared_allergies_count(self):
        insights = dict(ingredients("milk"), allergens={"Milk": ["milk"]})
        self.assertEqual(ev.allergy_check(row(insights, allergies="peanuts")), {"found": [], "label": []})
        self.assertIsNone(ev.allergy_check(row(insights, allergies="None provided")))
        self.assertIsNone(ev.allergy_check(row({"available": False}, allergies="peanuts")))

    def test_every_common_allergy_maps_to_an_allergen(self):
        # Found by this cross-check: these used to map to nothing, so Quorn wasn't avoided for an egg allergy.
        self.assertEqual(
            allergens_for_user_allergies("eggs, sesame, peanuts, soya, mustard, walnuts"),
            {"Eggs", "Sesame", "Peanuts", "Soya", "Mustard", "Tree nuts"},
        )
        self.assertNotIn("Tree nuts", allergens_for_user_allergies("peanuts"))
        self.assertIn("quorn", hidden_products_for_allergies("egg"))

    def test_vegetarian_and_vegan(self):
        veg = ingredients("chicken thigh", "plant-based mince", "aubergine", "fish sauce", "paneer")
        self.assertEqual(ev.diet_violations(row(veg, diets=["Vegetarian"])), ["chicken thigh", "fish sauce"])
        vegan = ingredients("coconut milk", "peanut butter", "butter", "eggs", "honey", "tofu")
        self.assertEqual(ev.diet_violations(row(vegan, diets=["Vegan"])), ["butter", "eggs", "honey"])
        self.assertIsNone(ev.diet_violations(row(veg, diets=[])))


class QualityTests(SimpleTestCase):
    def test_first_try_retries_and_fallback(self):
        rows = [
            row(history=[{"score": 92, "passed": True, "failed_checks": []}]),
            row(attempts=2, history=[
                {"score": 90, "passed": True, "failed_checks": [], "retry_for": ["Cuisine"]},
                {"score": 91, "passed": True, "failed_checks": []},
            ]),
            # An older record without "passed": worked out from the score.
            row(attempts=2, history=[
                {"score": 60, "hard_fail": True, "failed_checks": ["Allergy Safety"]},
                {"score": 88, "hard_fail": False, "failed_checks": []},
            ]),
            row(attempts=1, history=[{"score": 85, "status": "Verified", "fallback": True, "error": True}]),
        ]
        quality = ev.quality_summary(rows)
        self.assertEqual((quality["first_try"], quality["gates_first"]), (2, 3))
        self.assertEqual((quality["fallback"], quality["errors"]), (1, 1))
        self.assertEqual(quality["failed_checks"], [("Allergy Safety", 1)])
        self.assertEqual(quality["retry_for"], [("Cuisine", 1)])
        self.assertEqual(quality["average_attempts"], 1.5)

    def test_ai_calories_compared_with_the_calculation(self):
        def recipe(ai, code):
            return row({"available": True, "ai_kcal_per_serving": ai,
                        "nutrition": {"is_complete": True, "per_serving": {"energy_kcal": code},
                                      "matched": [{"name": "x"}], "unmatched": []}})
        nutrition = ev.nutrition_summary([recipe(550, 500), recipe(400, 500), recipe(None, 500)])
        self.assertEqual(nutrition["ai_kcal_compared"], 2)
        self.assertEqual(nutrition["ai_kcal_median_diff_pct"], 15.0)
        self.assertEqual(nutrition["ai_kcal_within_10_pct"], 50.0)

    def test_cuisine_data_matches_the_tests(self):
        data = ev.cuisine_data_summary()
        self.assertEqual(len(data["regions"]), 11)
        self.assertEqual(data["dishes_as_expected"], len(data["dishes"]))
        self.assertEqual(data["regions"][0]["region"], "Southeast Asian")  # biggest gap first


class BenchmarkCasesTests(SimpleTestCase):
    def test_thirty_cases_with_known_values(self):
        cases = load_cases()
        self.assertEqual(len(cases), 30)
        self.assertEqual(len({case["id"] for case in cases}), 30)
        styles = {case["meal_style"] for case in cases}
        self.assertEqual(styles, {"No preference", "Everyday healthy", "Treat"})
        for case in cases:
            data = preview_data_for(case)
            self.assertNotIn("id", data)
            self.assertIn("other_utensils", data)
            self.assertEqual(data["cooking_equipment"], ["Stove / Hob", "Oven"])


@override_settings(OPENAI_API_KEY="test-key")
class BenchmarkAndReportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with open("/dev/null", "w") as quiet:
            call_command("load_food_data", stdout=quiet)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for target in ("recipes.management.commands.run_benchmark.RESULTS_DIR",
                       "recipes.management.commands.evaluate.RESULTS_DIR"):
            patcher = patch(target, self.tmp)
            patcher.start()
            self.addCleanup(patcher.stop)
        ai_swaps = patch("recipes.swap_suggestion_service.ask_ai_for_swaps", return_value=None)
        ai_swaps.start()
        self.addCleanup(ai_swaps.stop)

    def test_refuses_without_yes(self):
        with self.assertRaisesMessage(CommandError, "Run it again with --yes"):
            call_command("run_benchmark", stdout=StringIO())
        with self.assertRaisesMessage(CommandError, "Unknown case id"):
            call_command("run_benchmark", "--yes", "--only", "nope", stdout=StringIO())
        self.assertFalse(RecipeHistory.objects.exists())

    @override_settings(OPENAI_API_KEY="")
    def test_refuses_without_a_key(self):
        with self.assertRaisesMessage(CommandError, "OPENAI_API_KEY is not set"):
            call_command("run_benchmark", "--yes", stdout=StringIO())

    @patch("recipes.views.generate_recipe_image_base64")
    @patch("recipes.views.extract_recipe_structure")
    @patch("recipes.views.generate_ai_recipe", return_value={"prompt": "p", "recipe_text": RECIPE_TEXT})
    def test_run_then_report(self, generate, extract, image):
        # The first recipe is only loosely Thai, so the cuisine check asks for one more try.
        loose = structure(["chicken breast", "burger bun", "tomato"])
        extract.side_effect = lambda *args, **kwargs: loose if extract.call_count == 1 else structure(THAI)

        # Cases that fit the mocked recipe text (a chicken burger), so the quality gates pass.
        cases = self.tmp / "cases.json"
        base = {"ingredients": FORM["ingredients"], "cuisine": "Thai", "cooking_equipment": ["Stove / Hob"]}
        cases.write_text(json.dumps({"cases": [
            dict(base, id="thai-plain"),
            dict(base, id="thai-allergy", allergies="peanuts"),
            dict(base, id="not-run"),
        ]}))
        out = StringIO()
        call_command("run_benchmark", "--yes", "--cases", str(cases), "--limit", "2", stdout=out)

        image.assert_not_called()  # images are off for the benchmark
        self.assertEqual(generate.call_count, 3)  # thai-plain was retried once for cuisine

        results = list(self.tmp.glob("benchmark_*.jsonl"))
        self.assertEqual(len(results), 1)
        lines = [json.loads(line) for line in results[0].read_text().splitlines()]
        self.assertEqual([line["case"] for line in lines], ["thai-plain", "thai-allergy"])
        self.assertEqual(lines[0]["attempts"], 2)

        plain = RecipeHistory.objects.get(id=lines[0]["history_id"])
        self.assertEqual(plain.user.username, "culinaai-benchmark")
        self.assertEqual(plain.validation_attempt_history[0]["retry_for"], ["Cuisine"])
        self.assertIn("passed", plain.validation_attempt_history[0])

        call_command("evaluate", "--benchmark", str(results[0]), stdout=StringIO())
        report = next(self.tmp.glob("benchmark_report_*.md")).read_text()
        self.assertIn("# CulinaAI benchmark evaluation", report)
        self.assertIn("| thai-plain | 2 |", report)
        self.assertIn("Based on 2 recipes.", report)
        self.assertIn("Retries asked for by code after the gates passed: Cuisine (1)", report)
        self.assertIn("Recipes made for someone with allergies: 1", report)
        self.assertIn("| Southeast Asian | 457 | 88.1% |", report)
        self.assertNotIn("## 7. Cooking mode", report)  # benchmark reports are about recipes only

    def test_report_from_real_use_with_cooking_and_study(self):
        cook = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        benchmark = User.objects.create_user("culinaai-benchmark")
        RecipeHistory.objects.create(user=cook, title="Cook's", recipe_text="x", validation_attempts=1,
                                     validation_attempt_history=[{"score": 90, "passed": True}], quality_score=90)
        RecipeHistory.objects.create(user=benchmark, title="Benchmark", recipe_text="x")
        adjusted = CookingSession.objects.create(user=cook, recipe_title="A", finished=True, outcome="great",
                                                 timers_adjusted=True, voice_used=True)
        plain = CookingSession.objects.create(user=cook, recipe_title="B", outcome="ok")
        CookingSession.objects.create(user=cook, recipe_title="C", timers_adjusted=True)  # nothing recorded
        CookingStepRecord.objects.create(session=adjusted, number=1, completed=True, went_fine=True)
        CookingStepRecord.objects.create(session=plain, number=1, completed=True, trouble="longer", note="slow hob")

        study = self.tmp / "responses.csv"
        with open(study, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["participant"] + ev.SUS_QUESTIONS)
            writer.writeheader()
            writer.writerow(dict({key: 3 for key in ev.SUS_QUESTIONS}, participant="P1"))

        out_file = self.tmp / "report.md"
        call_command("evaluate", "--study", str(study), "--out", str(out_file), stdout=StringIO())
        report = out_file.read_text()
        self.assertIn("Based on 1 recipes.", report)  # the benchmark recipe is left out
        self.assertIn("| Adjusted to the cook | 1 | 100% | 1 | 1 | 0% |", report)
        self.assertIn("| Not adjusted | 1 | 0% | 1 | 1 | 100% |", report)
        self.assertIn("Trouble reported: took longer (1)", report)
        self.assertIn("Times cooking mode was used: 3; with at least one step recorded: 2; with voice: 1", report)
        self.assertIn("How dishes turned out: it was OK (1), turned out great (1)", report)
        self.assertIn("first attempt: 1 of 1 with an attempt record (100%)", report)
        self.assertIn('System Usability Scale: mean 50: "poor" on the Bangor et al. (2009) scale, '
                      "below the usual average of 68", report)

        call_command("evaluate", "--exclude-user", "cook", "--out", str(out_file), stdout=StringIO())
        self.assertIn("Based on 0 recipes.", out_file.read_text())

    def test_cases_file_is_the_documented_one(self):
        self.assertTrue(CASES_FILE.exists())
        self.assertEqual(CASES_FILE.parent.name, "evaluation")
