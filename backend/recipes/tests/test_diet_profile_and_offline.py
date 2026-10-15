"""
Part E: diet and allergies saved on the profile and filled in on the New recipe form.
Part F: installing the site as an app and using it offline (the service worker,
the manifest, the offline page and ticks that can be sent late).

The offline behaviour itself was also checked in a real browser with the server
switched off; these tests cover the server side of it.
"""

import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from recipes.diet_profile import missing_saved_allergies, saved_diet
from recipes.meal_plan_service import week_start_for
from recipes.models import DietPreference, ShoppingListCheck, ShoppingListExtra
from recipes.tests.test_generation_flow import FORM


class DietProfileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        cls.vegan = DietPreference.objects.get_or_create(name="Vegan")[0]
        cls.halal = DietPreference.objects.get_or_create(name="Halal")[0]

    def setUp(self):
        self.client.force_login(self.user)

    def save_diet(self, **data):
        payload = {"form_type": "diet", "other_diet": "", "allergies": ""}
        payload.update(data)
        return self.client.post(reverse("profile_summary"), payload, follow=True)

    def test_save_on_the_profile(self):
        response = self.save_diet(
            diet_preferences=[self.vegan.id], other_diet="  no   onion ", allergies="Peanuts;\nshellfish, peanuts ,  sesame",
        )
        self.assertIn("Your diet and allergies will be filled in on every new recipe.", response.content.decode())
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.allergies, "Peanuts, shellfish, sesame")  # tidied, no repeats
        self.assertEqual(profile.other_diet, "no onion")
        self.assertEqual(list(profile.diet_preferences.all()), [self.vegan])
        html = self.client.get(reverse("profile_summary")).content.decode()
        self.assertIn("Peanuts, shellfish, sesame", html)
        self.assertRegex(html, rf'name="diet_preferences" value="{self.vegan.id}"[^>]*checked')

    def test_new_recipe_form_is_filled_in(self):
        self.save_diet(diet_preferences=[self.vegan.id, self.halal.id], other_diet="Jain", allergies="peanuts")
        html = self.client.get(reverse("generate_recipe")).content.decode()
        self.assertIn("Filled in from", html)
        self.assertIn(">\npeanuts</textarea>", html)
        self.assertIn('value="Jain"', html)
        for diet in (self.vegan, self.halal):
            self.assertRegex(html, rf'value="{diet.id}"[^>]*checked')

    def test_filled_in_for_pantry_fridge_and_use_up_too(self):
        self.save_diet(allergies="peanuts")
        for params in ({"use_up": "spinach"}, {"recommendation": "rice"}):
            html = self.client.get(reverse("generate_recipe"), params).content.decode()
            self.assertIn(">\npeanuts</textarea>", html)

    def test_without_saved_settings_the_form_suggests_saving_them(self):
        html = self.client.get(reverse("generate_recipe")).content.decode()
        self.assertIn("Save your diet and allergies on your profile", html)
        dashboard = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("Tell us your allergies once", dashboard)
        self.save_diet(allergies="milk")
        self.assertNotIn("Tell us your allergies once", self.client.get(reverse("dashboard")).content.decode())

    @patch("recipes.generate_views.run_recipe_generation")
    def test_taking_a_saved_allergy_out_for_one_recipe_is_allowed_but_said(self, run):
        self.save_diet(allergies="peanuts, milk")
        response = self.client.post(reverse("generate_recipe"), dict(FORM, allergies="milk"), follow=True)
        run.assert_called_once()
        self.assertIn("This recipe wasn&#x27;t checked for peanuts", response.content.decode())

        run.reset_mock()
        response = self.client.post(reverse("generate_recipe"), dict(FORM, allergies="Peanuts and milk"), follow=True)
        self.assertNotIn("wasn&#x27;t checked for", response.content.decode())

    def test_helpers(self):
        self.assertFalse(saved_diet(self.user)["has_any"])
        self.save_diet(allergies="peanuts, sesame")
        self.assertTrue(saved_diet(self.user)["has_any"])
        self.assertEqual(missing_saved_allergies(self.user, "sesame seeds"), ["peanuts"])
        self.assertEqual(missing_saved_allergies(self.user, "PEANUTS, sesame"), [])

    def test_in_the_data_download(self):
        self.save_diet(diet_preferences=[self.vegan.id], allergies="peanuts")
        data = json.loads(self.client.get(reverse("download_my_data")).content)
        self.assertEqual(data["account"]["allergies"], "peanuts")
        self.assertEqual(data["account"]["diet"], ["Vegan"])

    def test_demo_accounts_cannot_change_it(self):
        UserProfile.objects.filter(user=self.user).update(is_demo=True)
        self.save_diet(allergies="peanuts")
        self.assertEqual(UserProfile.objects.get(user=self.user).allergies, "")


class InstallAndOfflineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")

    def test_service_worker_is_served_from_the_root(self):
        response = self.client.get("/sw.js")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/javascript")
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertIn("no-cache", response["Cache-Control"])
        body = response.content.decode()
        self.assertIn('const OFFLINE_URL = "/offline/"', body)
        self.assertIn("culina-pages-", body)
        self.assertNotIn("{%", body)

    def test_manifest(self):
        response = self.client.get(reverse("web_manifest"))
        self.assertEqual(response["Content-Type"], "application/manifest+json")
        data = json.loads(response.content)
        self.assertEqual(data["name"], "CulinaAI")
        self.assertEqual(data["display"], "standalone")
        self.assertTrue(any(icon["purpose"] == "maskable" for icon in data["icons"] if "purpose" in icon))
        self.assertEqual({icon["sizes"] for icon in data["icons"]}, {"192x192", "512x512"})

    def test_offline_page_has_no_personal_data(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse("offline_page")).content.decode()
        self.assertIn("You're offline", html)
        self.assertNotIn("cook@example.com", html)
        self.assertNotIn("cook</span>", html)

    def test_pages_link_the_manifest_and_say_who_is_logged_in(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn(reverse("web_manifest"), html)
        self.assertIn("js/pwa.js", html)
        self.assertNotIn("data-user-id", html)  # logged out: pwa.js clears saved pages
        self.client.force_login(self.user)
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn(f'data-user-id="{self.user.pk}"', html)
        self.assertIn("data-offline-bar", html)

    def test_ticks_sent_late_land_the_same_however_often_they_are_sent(self):
        self.client.force_login(self.user)
        week = week_start_for(timezone.localdate()).isoformat()
        url = reverse("shopping_toggle")
        for _ in range(2):
            response = self.client.post(url, {"week": week, "key": "rice", "done": "1"}, HTTP_X_REQUESTED_WITH="fetch")
            self.assertEqual(response.json(), {"ok": True, "done": True})
        self.assertEqual(ShoppingListCheck.objects.count(), 1)
        for _ in range(2):
            self.client.post(url, {"week": week, "key": "rice", "done": "0"}, HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(ShoppingListCheck.objects.count(), 0)

        extra = ShoppingListExtra.objects.create(user=self.user, week_start=week_start_for(timezone.localdate()), name="Foil")
        extra_url = reverse("shopping_extra_toggle", args=[extra.id])
        for _ in range(2):
            self.client.post(extra_url, {"done": "1"}, HTTP_X_REQUESTED_WITH="fetch")
        extra.refresh_from_db()
        self.assertTrue(extra.done)

    def test_the_list_has_a_place_to_say_ticks_are_waiting(self):
        self.client.force_login(self.user)
        from recipes.models import MealPlanEntry, Recipe

        recipe = Recipe.objects.create(user=self.user, title="Rice", ingredients_text="rice", instructions_text="x",
                                       cooking_time_minutes=10, difficulty="easy")
        MealPlanEntry.objects.create(user=self.user, recipe=recipe, date=timezone.localdate(), servings=2)
        html = self.client.get(reverse("shopping_list")).content.decode()
        self.assertIn("data-queue-note", html)
        self.assertIn("shopping_list.js", html)
