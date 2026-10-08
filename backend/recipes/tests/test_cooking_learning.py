"""
Learning from how the user cooks, part 1: recording sessions from cooking mode,
the on/off switch, deleting history, and the dashboard's cooking profile.
No AI calls. The voice commands are tested separately with Node:
    node scripts/test_voice_commands.js
"""

import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from recipes.cooking_learning_service import build_cooking_profile, pace_words, record_session
from recipes.cooking_mode_service import build_cooking_mode_context
from recipes.models import CookingSession, CookingSettings, CookingStepRecord, Recipe

INSTRUCTIONS = """1. Chop the onion and garlic.
2. Fry the onion in olive oil for 5 minutes.
3. Add the tomatoes and simmer for 10 minutes.
4. Stir in the coriander and serve."""


def make_recipe(user, title="Tomato curry"):
    return Recipe.objects.create(
        user=user,
        title=title,
        ingredients_text="- 1 onion\n- 2 garlic cloves\n- 400 g chopped tomatoes\n- 2 tbsp fresh coriander\n- 1 tbsp olive oil",
        instructions_text=INSTRUCTIONS,
        cooking_time_minutes=30,
        is_saved=True,
    )


def step(number, seconds=0, completed=False, **extra):
    return dict({"number": number, "seconds": seconds, "completed": completed}, **extra)


class CookingStepsTests(TestCase):
    def test_steps_say_whether_the_time_came_from_the_text(self):
        user = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        steps = build_cooking_mode_context(make_recipe(user))["cooking_steps"]
        self.assertEqual([s["timer_from_text"] for s in steps], [False, True, True, False])
        self.assertEqual([s["timer_minutes"] for s in steps[1:3]], [5, 10])


class RecordSessionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        self.recipe = make_recipe(self.user)

    def test_saves_steps_with_text_from_the_server_and_clamps_numbers(self):
        session = record_session(self.user, self.recipe, {
            "voice_used": True,
            "steps": [
                step(1, 90, True, text="something the browser made up"),
                step(2, 10**9, True, repeats=999, trouble="longer", timer_used=True),
                step(3, 30, trouble="not-a-reason"),
                step(99, 60, True),  # not in this recipe
                "nonsense",
            ],
        })
        self.assertEqual((session.steps_total, session.steps_completed, session.finished), (4, 2, False))
        self.assertTrue(session.voice_used)

        records = {r.number: r for r in session.steps.all()}
        self.assertEqual(set(records), {1, 2, 3})
        self.assertEqual(records[1].text, "Chop the onion and garlic.")
        self.assertEqual(records[2].seconds_open, 6 * 60 * 60)
        self.assertEqual(records[2].repeats, 50)
        self.assertEqual((records[2].trouble, records[2].planned_minutes, records[2].timer_from_text), ("longer", 5, True))
        self.assertEqual(records[3].trouble, "")
        self.assertEqual(session.active_seconds, 90 + 6 * 60 * 60 + 30)

    def test_step_feedback_note_and_went_fine(self):
        session = record_session(self.user, self.recipe, {"steps": [
            step(1, 60, True, went_fine=True, note="  Easy,\n quick  "),
            step(2, 60, True, went_fine=True, trouble="longer", note="x" * 500),
            step(3, 60, True, note=["not", "text"]),
        ]})
        records = {r.number: r for r in session.steps.all()}
        self.assertEqual((records[1].went_fine, records[1].note), (True, "Easy, quick"))
        self.assertEqual((records[2].went_fine, records[2].trouble, len(records[2].note)), (False, "longer", 300))
        self.assertEqual(records[3].note, "")

        profile = build_cooking_profile(self.user)
        self.assertEqual((profile["went_fine"], profile["notes"]), (1, 2))
        self.assertEqual(profile["recent_trouble"][0]["reason"], "Went fine")
        self.assertEqual(profile["recent_trouble"][0]["note"], "Easy, quick")

    def test_same_session_is_updated_not_duplicated(self):
        first = record_session(self.user, self.recipe, {"steps": [step(1, 60, True)]})
        again = record_session(self.user, self.recipe, {
            "session_id": first.id,
            "outcome": "great",
            "steps": [step(n, 60, True) for n in range(1, 5)],
        })
        self.assertEqual(first.id, again.id)
        self.assertEqual(CookingSession.objects.count(), 1)
        self.assertTrue(again.finished)
        self.assertEqual(again.outcome, "great")
        self.assertEqual(CookingStepRecord.objects.count(), 4)

    def test_another_users_session_id_starts_a_new_session(self):
        other = User.objects.create_user("other", "other@example.com", "pass-12345")
        theirs = record_session(other, make_recipe(other), {"steps": [step(1, 60, True)]})
        mine = record_session(self.user, self.recipe, {"session_id": theirs.id, "steps": [step(1, 60, True)]})
        self.assertNotEqual(mine.id, theirs.id)
        self.assertEqual(CookingSession.objects.get(id=theirs.id).user, other)

    def test_nothing_is_saved_when_learning_is_off(self):
        CookingSettings.objects.create(user=self.user, learn_from_cooking=False)
        self.assertIsNone(record_session(self.user, self.recipe, {"steps": [step(1, 60, True)]}))
        self.assertFalse(CookingSession.objects.exists())

    def test_bad_payloads(self):
        with self.assertRaises(ValueError):
            record_session(self.user, self.recipe, ["not", "a", "dict"])
        with self.assertRaises(ValueError):
            record_session(self.user, self.recipe, {"steps": "nope"})


class RecordViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        self.recipe = make_recipe(self.user)
        self.url = reverse("cooking_record", args=[self.recipe.id])
        self.client.force_login(self.user)

    def test_json_and_page_closing_form(self):
        response = self.client.post(self.url, json.dumps({"steps": [step(1, 60, True)]}), content_type="application/json")
        session_id = response.json()["session_id"]

        # sendBeacon posts a form with the same JSON in "payload".
        response = self.client.post(self.url, {"payload": json.dumps({"session_id": session_id, "steps": [step(2, 60, True)]})})
        self.assertEqual(response.json(), {"saved": True, "session_id": session_id})
        session = CookingSession.objects.get()
        self.assertEqual(session.steps.count(), 2)  # step 1 from the first save is kept
        self.assertEqual((session.steps_completed, session.active_seconds), (2, 120))

    def test_rejections(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(self.client.post(self.url, "{not json", content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post(self.url, "", content_type="application/json").status_code, 400)

        other = User.objects.create_user("other", "other@example.com", "pass-12345")
        their_url = reverse("cooking_record", args=[make_recipe(other).id])
        self.assertEqual(self.client.post(their_url, "{}", content_type="application/json").status_code, 404)

        self.client.logout()
        self.assertEqual(self.client.post(self.url, "{}", content_type="application/json").status_code, 302)

    def test_learning_off_reply(self):
        CookingSettings.objects.create(user=self.user, learn_from_cooking=False)
        response = self.client.post(self.url, json.dumps({"steps": [step(1, 60, True)]}), content_type="application/json")
        self.assertEqual(response.json(), {"saved": False, "learning": False})


class SettingsAndForgetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        self.client.force_login(self.user)

    def test_switch_learning_and_english(self):
        url = reverse("cooking_settings")
        response = self.client.post(url, {"learn": "off", "english": "en-IN"}, HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(response.json(), {"learning": False, "english": "en-IN"})

        response = self.client.post(url, {"english": "klingon"}, HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(response.json()["english"], "en-IN")

        response = self.client.post(url, {"learn": "on", "next": "/dashboard/#cooking-profile"})
        self.assertRedirects(response, "/dashboard/#cooking-profile", fetch_redirect_response=False)
        self.assertTrue(CookingSettings.objects.get(user=self.user).learn_from_cooking)

        response = self.client.post(url, {"learn": "on", "next": "https://evil.example.com/"})
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)

    def test_forget_deletes_only_my_history(self):
        other = User.objects.create_user("other", "other@example.com", "pass-12345")
        record_session(other, make_recipe(other), {"steps": [step(1, 60, True)]})
        recipe = make_recipe(self.user)
        record_session(self.user, recipe, {"steps": [step(1, 60, True)]})
        record_session(self.user, recipe, {"steps": [step(2, 60, True)]})

        response = self.client.post(reverse("cooking_forget"), HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(response.json(), {"deleted": 2})
        self.assertEqual(CookingSession.objects.filter(user=other).count(), 1)
        self.assertEqual(CookingStepRecord.objects.filter(session__user=self.user).count(), 0)


class CookingProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        self.recipe = make_recipe(self.user)

    def test_pace_needs_three_timed_steps_and_ignores_outliers(self):
        # Steps 2 (5 min) and 3 (10 min) give their own times.
        record_session(self.user, self.recipe, {"steps": [step(2, 390, True), step(3, 780, True), step(1, 999, True)]})
        profile = build_cooking_profile(self.user)
        self.assertIsNone(profile["pace"]["ratio"])
        self.assertEqual(profile["pace"]["steps"], 2)

        record_session(self.user, self.recipe, {
            "outcome": "great",
            "steps": [step(2, 390, True), step(3, 5, True), step(1, 60, True, trouble="unclear")],
        })
        record_session(self.user, self.recipe, {"steps": [step(3, 99999, True)]})  # left open for hours: ignored
        profile = build_cooking_profile(self.user)
        # Ratios 1.3, 1.3, 1.3 (the 5-second and 27-hour steps are left out).
        self.assertEqual(profile["pace"]["ratio"], 1.3)
        self.assertEqual(profile["pace"]["words"], "About 30% longer than the recipe times")
        self.assertEqual(profile["cooked"], 3)
        self.assertEqual(profile["trouble_total"], 1)
        self.assertEqual(profile["top_trouble"], "Instructions unclear")
        self.assertEqual(profile["recent_trouble"][0]["number"], 1)
        self.assertEqual(profile["rated"], 1)

    def test_pace_words(self):
        self.assertEqual(pace_words(1.05), "About the same as the recipe times")
        self.assertEqual(pace_words(0.7), "About 30% quicker than the recipe times")
        self.assertEqual(pace_words(None), "")


class PagesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        self.recipe = make_recipe(self.user)
        self.client.force_login(self.user)

    def test_cooking_mode_has_voice_learning_on_and_trouble_button(self):
        html = self.client.get(reverse("cooking_mode", args=[self.recipe.id])).content.decode()
        for text in ("Hands-free voice", "My English", "English (India)", "Learning: <span id=\"learningState\">On</span>", "cooking-captions",
                     'id="learningSwitch" checked', "Having trouble with this step?", "Instructions unclear", 'id="stepFeedback" hidden', "Went fine",
                     "How did it turn out?", 'id="cookingConfig"', "cooking_voice_commands.js", "csrfmiddlewaretoken"):
            self.assertIn(text, html)
        config = json.loads(html.split('id="cookingConfig" type="application/json">')[1].split("</script>")[0])
        self.assertTrue(config["learning"])
        self.assertIn("2 tbsp fresh coriander", config["ingredients"])
        self.assertEqual(config["record_url"], reverse("cooking_record", args=[self.recipe.id]))

    def test_cooking_mode_with_learning_off(self):
        CookingSettings.objects.create(user=self.user, learn_from_cooking=False, english="en-US")
        html = self.client.get(reverse("cooking_mode", args=[self.recipe.id])).content.decode()
        self.assertIn('id="stepTrouble" data-learning-only hidden', html)
        self.assertNotIn('id="learningSwitch" checked', html)
        self.assertIn('"english": "en-US"', html)

    def test_dashboard_profile(self):
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("What CulinaAI has learned from your cooking", html)
        self.assertIn("Turn learning off", html)
        self.assertNotIn("Delete my cooking history", html)  # nothing to delete yet

        record_session(self.user, self.recipe, {"steps": [step(1, 60, True, trouble="technique")]})
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("Delete my cooking history", html)
        self.assertIn("Tricky technique: step 1, Tomato curry", html)

        record_session(self.user, self.recipe, {"steps": [step(2, 60, True, trouble="longer", note="My pan was too small")]})
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("“My pan was too small”", html)
