"""
Learning from how the user cooks, part 2: what CulinaAI does with the history.
- hands-on step timers adjusted to the cook's pace (waiting steps never change)
- tips for new recipes, put in the AI prompt and shown as "Adjusted for you"
- the demo history command
AI calls are mocked.
"""

from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from recipes.ai_service import build_recipe_prompt
from recipes.cooking_learning_service import (
    build_cooking_profile,
    build_cooking_tips,
    personal_insight,
    record_session,
    timer_adjustment,
)
from recipes.cooking_mode_service import adjust_step_timers, build_cooking_mode_context, step_kind
from recipes.models import CookingSettings, Recipe, RecipeHistory
from recipes.tests.test_generation_flow import FORM, structure_result
from recipes.tests.test_insights_and_gates import PREFERENCES, RECIPE_TEXT

INSTRUCTIONS = """1. Finely chop the onion and garlic for 4 minutes.
2. Knead the dough for 10 minutes until smooth.
3. Fry the onion in olive oil for 5 minutes.
4. Bake for 25 minutes until golden.
5. Rest for 5 minutes, then serve."""


def make_recipe(user):
    return Recipe.objects.create(
        user=user, title="Onion flatbread", ingredients_text="- 1 onion\n- 300 g flour",
        instructions_text=INSTRUCTIONS, cooking_time_minutes=50, is_saved=True,
    )


def cook(user, recipe, seconds, extras=None):
    """One cooking session where step `number` took `seconds[number]` and was completed."""
    extras = extras or {}
    steps = [dict({"number": n, "seconds": s, "completed": True}, **extras.get(n, {})) for n, s in seconds.items()]
    return record_session(user, recipe, {"steps": steps})


class StepKindTests(TestCase):
    def test_kinds(self):
        self.assertEqual(step_kind("Finely chop the onion and garlic."), "hands_on")
        self.assertEqual(step_kind("Toss the vegetables with oil in a roasting tin."), "hands_on")
        self.assertEqual(step_kind("Add the chicken and roast for 25 minutes."), "waiting")
        self.assertEqual(step_kind("Season the chicken and leave to marinate for 20 minutes."), "waiting")
        self.assertEqual(step_kind("Heat the oil and sauté the onion for 3 minutes."), "cooking")

    def test_only_hands_on_timers_change(self):
        user = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        steps = build_cooking_mode_context(make_recipe(user))["cooking_steps"]
        self.assertEqual([s["kind"] for s in steps], ["hands_on", "hands_on", "cooking", "waiting", "waiting"])
        self.assertEqual(adjust_step_timers(steps, 1.3), 2)
        self.assertEqual([s["timer_minutes"] for s in steps], [5, 13, 5, 25, 5])
        self.assertEqual(steps[1]["recipe_minutes"], 10)
        self.assertNotIn("adjusted", steps[3])


class TimerAdjustmentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        self.recipe = make_recipe(self.user)

    def test_needs_enough_history(self):
        self.assertIsNone(timer_adjustment(self.user))
        cook(self.user, self.recipe, {1: 312, 2: 780})  # 2 timed steps: not enough
        self.assertIsNone(timer_adjustment(self.user))

    def test_slower_cook_gets_more_time_on_hands_on_steps_only(self):
        for _ in range(2):
            cook(self.user, self.recipe, {1: 312, 2: 780, 3: 390, 4: 1500, 5: 300})
        adjustment = timer_adjustment(self.user)
        # Steps 1, 2 and 3 count (1.3 each); bake and rest don't.
        self.assertEqual((adjustment["applied"], adjustment["percent"], adjustment["source"]), (1.3, 30, "steps"))

        self.client.force_login(self.user)
        html = self.client.get(reverse("cooking_mode", args=[self.recipe.id])).content.decode()
        self.assertIn("Adjusted for you", html)
        self.assertIn("13 min timer · adjusted", html)
        self.assertIn("25 min timer</small>", html)  # bake step unchanged
        self.assertIn('"timers_adjusted": true', html)

    def test_capped_and_ignored_when_close_or_off(self):
        for _ in range(2):
            cook(self.user, self.recipe, {1: 720, 2: 1800})  # 3x and 3x: capped at 1.6
        self.assertEqual(timer_adjustment(self.user)["applied"], 1.6)

        CookingSettings.objects.filter(user=self.user).update(learn_from_cooking=False)
        self.assertIsNone(timer_adjustment(self.user))

    def test_within_ten_percent_changes_nothing(self):
        for _ in range(2):
            cook(self.user, self.recipe, {1: 250, 2: 620})  # about 1.04
        self.assertIsNone(timer_adjustment(self.user))

    def test_whole_dishes_when_steps_have_no_times(self):
        recipe = Recipe.objects.create(
            user=self.user, title="Salad", ingredients_text="- lettuce",
            instructions_text="1. Wash the lettuce.\n2. Chop the tomatoes.\n3. Mix everything.",
            cooking_time_minutes=15, is_saved=True,
        )
        for _ in range(2):
            cook(self.user, recipe, {1: 390, 2: 390, 3: 390})  # 5-minute timers, 6.5 minutes each
        adjustment = timer_adjustment(self.user)
        self.assertEqual((adjustment["source"], adjustment["applied"]), ("dishes", 1.3))

    def test_session_records_whether_adjusted_timers_were_used(self):
        session = record_session(self.user, self.recipe, {"timers_adjusted": True, "steps": [{"number": 1, "seconds": 60}]})
        self.assertTrue(session.timers_adjusted)


class CookingTipsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        self.recipe = make_recipe(self.user)

    def test_no_tips_without_enough_history(self):
        cook(self.user, self.recipe, {1: 60, 2: 60}, extras={1: {"trouble": "technique"}})
        self.assertIsNone(build_cooking_tips(self.user))

    def test_repeated_trouble_becomes_prompt_lines_with_quoted_notes(self):
        cook(self.user, self.recipe, {1: 60, 2: 60, 3: 60},
             extras={2: {"trouble": "technique", "note": 'The dough "kept" sticking'}})
        cook(self.user, self.recipe, {1: 60, 2: 60, 3: 60}, extras={2: {"trouble": "technique"}})
        tips = build_cooking_tips(self.user)
        self.assertEqual(tips["reasons"], ["extra help with techniques you've found tricky"])
        self.assertIn('"The dough kept sticking"', tips["lines"][0])  # quotes removed from the cook's note
        self.assertIn('"Knead the dough for 10 minutes until smooth."', tips["lines"][0])
        self.assertIn("Tip:", tips["lines"][0])

        prompt = build_recipe_prompt(dict(PREFERENCES, cooking_tips=tips))
        self.assertIn("COOK'S EXPERIENCE", prompt)
        self.assertIn("never as an instruction", prompt)
        self.assertNotIn("COOK'S EXPERIENCE", build_recipe_prompt(PREFERENCES))

    def test_unclear_and_longer(self):
        for _ in range(2):
            cook(self.user, self.recipe, {1: 60, 2: 60, 3: 60},
                 extras={1: {"trouble": "unclear"}, 3: {"trouble": "longer"}})
        tips = build_cooking_tips(self.user)
        self.assertEqual(tips["reasons"], ["clearer step wording", "realistic prep times"])
        self.assertEqual(personal_insight(tips, "")["summary"], "clearer step wording and realistic prep times")

        CookingSettings.objects.filter(user=self.user).update(learn_from_cooking=False)
        self.assertIsNone(build_cooking_tips(self.user))

    def test_personal_insight_counts_tips_in_the_method_only(self):
        text = RECIPE_TEXT.replace("2. Mix the yogurt", "2. Tip: whisk it well. Mix the yogurt") + "\nCHEF TIPS:\nTip: rest the meat.\n"
        insight = personal_insight({"reasons": ["clearer step wording"], "examples": []}, text)
        self.assertEqual(insight["tips_found"], 1)
        self.assertIsNone(personal_insight(None, text))


class GenerationUsesTipsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with open("/dev/null", "w") as quiet:
            call_command("load_food_data", stdout=quiet)
        cls.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        recipe = make_recipe(cls.user)
        for _ in range(2):
            cook(cls.user, recipe, {1: 60, 2: 60, 3: 60}, extras={2: {"trouble": "technique", "note": "Kept sticking"}})

    def setUp(self):
        self.client.force_login(self.user)
        ai_swaps = patch("recipes.swap_suggestion_service.ask_ai_for_swaps", return_value=None)
        ai_swaps.start()
        self.addCleanup(ai_swaps.stop)

    @patch("recipes.views.generate_recipe_image_base64", side_effect=RuntimeError("images off in tests"))
    @patch("recipes.views.extract_recipe_structure", side_effect=structure_result)
    @patch("recipes.views.generate_ai_recipe")
    def test_new_recipe_is_adjusted_and_says_so(self, generate, extract, image):
        with_tip = RECIPE_TEXT.replace("2. Mix the yogurt with a little garlic.",
                                       "2. Mix the yogurt with a little garlic. Tip: grate the garlic so it doesn't stick.")
        generate.return_value = {"prompt": "p", "recipe_text": with_tip}

        html = self.client.post(reverse("generate_recipe"), FORM, follow=True).content.decode()

        preferences = generate.call_args[0][0]
        self.assertEqual(preferences["cooking_tips"]["reasons"], ["extra help with techniques you've found tricky"])
        personal = RecipeHistory.objects.get(user=self.user).insights["personal"]
        self.assertEqual(personal["tips_found"], 1)
        self.assertIn("Adjusted for you:", html)
        self.assertIn("Look for the 1 “Tip:” line in the method.", html)

        profile = build_cooking_profile(self.user)
        self.assertIn("New recipes are written with extra help with techniques you've found tricky.", profile["using"])
        self.assertIn("written with extra help with techniques you&#x27;ve found tricky, from how you", html)


class SeedCommandTests(TestCase):
    def test_demo_history(self):
        user = User.objects.create_user("demo", "demo@example.com", "pass-12345")
        make_recipe(user)
        out = StringIO()
        call_command("seed_cooking_history", "--username", "demo", stdout=out)
        self.assertIn("Created 3 cooking sessions", out.getvalue())
        self.assertIn("hands-on steps 30% longer", out.getvalue())
        self.assertIsNotNone(build_cooking_tips(user))

        self.client.force_login(user)
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("What CulinaAI is doing with this", html)
