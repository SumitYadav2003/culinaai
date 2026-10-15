"""
Part A: the daily AI limits, confirming your email, downloading your data,
deleting your account, page numbers on long lists and the closable messages.
No real AI calls are made: the code that would call the AI is patched out.
"""

import json
import re
import shutil
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from recipes.ai_limits import allowance, start_of_today
from recipes.models import AIUsage, FavouriteRecipe, PantryItem, Recipe, RecipeHistory
from recipes.tests.test_generation_flow import FORM
from recipes.tests.test_insights_and_gates import RECIPE_TEXT


def make_recipe(user, title="Lemon Rice", **extra):
    return Recipe.objects.create(
        user=user, title=title, ingredients_text="rice, lemon", instructions_text=RECIPE_TEXT,
        cooking_time_minutes=20, difficulty="easy", **extra,
    )


def use_up(user, kind="recipe", count=None, when=None):
    from django.conf import settings

    count = count if count is not None else (
        settings.AI_DAILY_QUESTION_LIMIT if kind == "question" else settings.AI_DAILY_RECIPE_LIMIT
    )
    rows = AIUsage.objects.bulk_create([AIUsage(user=user, kind=kind, action="test") for _ in range(count)])
    if when:
        AIUsage.objects.filter(id__in=[row.id for row in rows]).update(created_at=when)


@override_settings(AI_DAILY_RECIPE_LIMIT=3, AI_DAILY_QUESTION_LIMIT=2)
class DailyLimitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        cls.recipe = make_recipe(cls.user)

    def setUp(self):
        self.client.force_login(self.user)

    @patch("recipes.generate_views.run_recipe_generation")
    def test_each_new_recipe_is_counted_until_the_limit(self, run):
        for _ in range(3):
            self.client.post(reverse("generate_recipe"), FORM)
        self.assertEqual(run.call_count, 3)
        self.assertEqual(AIUsage.objects.filter(user=self.user, action="generate").count(), 3)

        response = self.client.post(reverse("generate_recipe"), FORM)
        self.assertEqual(run.call_count, 3)  # the AI was not called a fourth time
        html = response.content.decode()
        self.assertIn("You&#x27;ve used all 3 of today&#x27;s AI recipes and changes.", html)
        # The form comes back with what they typed.
        self.assertIn("chicken breast, burger bun", html)

    @patch("recipes.generate_views.run_recipe_generation")
    def test_a_form_with_mistakes_is_not_counted(self, run):
        self.client.post(reverse("generate_recipe"), {"ingredients": ""})
        self.assertFalse(AIUsage.objects.exists())
        run.assert_not_called()

    def test_yesterdays_use_does_not_count(self):
        use_up(self.user, when=start_of_today() - timedelta(minutes=1))
        self.assertEqual(allowance(self.user, "recipe")["left"], 3)
        use_up(self.user, count=1)
        self.assertEqual(allowance(self.user, "recipe")["left"], 2)

    def test_page_shows_how_many_are_left(self):
        use_up(self.user, count=1)
        html = self.client.get(reverse("generate_recipe")).content.decode()
        self.assertIn("2 of 3 AI recipes and changes left today.", html)
        use_up(self.user, count=2)
        html = self.client.get(reverse("saved_recipe_detail", args=[self.recipe.id])).content.decode()
        self.assertIn("You've used all 3 of today's AI recipes and changes.", html)

    @patch("recipes.saved_views.modify_ai_recipe")
    def test_changing_a_saved_recipe_is_limited(self, modify):
        use_up(self.user)
        response = self.client.post(
            reverse("modify_saved_recipe", args=[self.recipe.id]), {"modification_type": "healthier"}, follow=True,
        )
        modify.assert_not_called()
        self.assertIn("You&#x27;ve used all 3", response.content.decode())

    @patch("recipes.generate_views.run_recipe_generation")
    def test_change_and_version_on_the_generate_page_are_limited(self, run):
        session = self.client.session
        session["latest_recipe_preferences"] = {"ingredients": "rice"}
        session["latest_ai_recipe_text"] = RECIPE_TEXT
        session["latest_recipe_insights"] = {"three_ways": [{"goal": "cheaper", "swaps": [{"from": "a"}]}]}
        session.save()
        use_up(self.user)

        self.client.post(reverse("change_generated_recipe"), {"modification_type": "quicker"})
        self.client.post(reverse("generate_recipe_version"), {"goal": "cheaper"})
        run.assert_not_called()

    @patch("recipes.fridge_scanner_views.scan_fridge_image")
    def test_fridge_scan_is_limited(self, scan):
        use_up(self.user)
        from io import BytesIO

        from PIL import Image

        buffer = BytesIO()
        Image.new("RGB", (20, 20), "white").save(buffer, "PNG")
        photo = SimpleUploadedFile("fridge.png", buffer.getvalue(), content_type="image/png")
        response = self.client.post(reverse("fridge_scan_upload"), {"image": photo}, follow=True)
        scan.assert_not_called()
        self.assertIn("You&#x27;ve used all 3", response.content.decode())

    @patch("recipes.saved_views.ask_cooking_assistant")
    def test_cooking_questions_have_their_own_limit(self, ask):
        use_up(self.user)  # recipe allowance used up; questions still work
        url = reverse("ask_cooking_assistant", args=[self.recipe.id])
        ask.return_value.success = True
        ask.return_value.reply = "Yes."
        ask.return_value.session.id = 1
        ask.return_value.error = ""
        ask.return_value.user_message = None
        ask.return_value.assistant_message = None
        response = self.client.post(url, json.dumps({"question": "Can I use brown rice?"}), content_type="application/json")
        self.assertTrue(response.json()["success"])
        self.assertEqual(AIUsage.objects.filter(kind="question").count(), 1)

        use_up(self.user, kind="question")
        ask.reset_mock()
        response = self.client.post(url, json.dumps({"question": "And basmati?"}), content_type="application/json")
        ask.assert_not_called()
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("questions today, which is the daily limit", data["error"])

    @patch("recipes.generate_views.run_recipe_generation")
    def test_staff_have_no_limit(self, run):
        staff = User.objects.create_user("owner", "owner@example.com", "pass-12345", is_staff=True)
        self.client.force_login(staff)
        use_up(staff, count=10)
        self.client.post(reverse("generate_recipe"), FORM)
        run.assert_called_once()
        self.assertNotIn("AI recipes and changes left today", self.client.get(reverse("generate_recipe")).content.decode())


class EmailConfirmationTests(TestCase):
    def sign_up(self):
        return self.client.post(reverse("signup"), {
            "full_name": "Alex Morgan", "email": "alex@example.com",
            "password1": "Tomato-soup-42", "password2": "Tomato-soup-42",
        }, follow=True)

    def link_from(self, message):
        return re.search(r"https?://testserver(/confirm-email/[^\s\"<]+)", message.body).group(1)

    @patch("recipes.generate_views.run_recipe_generation")
    def test_new_account_must_confirm_before_using_the_ai(self, run):
        self.sign_up()
        user = User.objects.get(email="alex@example.com")
        self.assertFalse(user.profile.email_confirmed)

        response = self.client.post(reverse("generate_recipe"), FORM)
        run.assert_not_called()
        self.assertIn("Confirm your email first.", response.content.decode())
        self.assertFalse(AIUsage.objects.exists())

        response = self.client.get(self.link_from(mail.outbox[0]), follow=True)
        self.assertIn("Thanks, your email is confirmed.", response.content.decode())
        self.assertNotIn("site-confirm-bar", response.content.decode())
        user.profile.refresh_from_db()
        self.assertTrue(user.profile.email_confirmed)

        self.client.post(reverse("generate_recipe"), FORM)
        run.assert_called_once()

    def test_link_only_works_once_and_bad_links_are_explained(self):
        self.sign_up()
        link = self.link_from(mail.outbox[0])
        self.client.get(link)
        response = self.client.get(link, follow=True)
        self.assertIn("Your email is already confirmed.", response.content.decode())

        response = self.client.get(reverse("confirm_email", args=["OTk5", "bad-token"]), follow=True)
        self.assertIn("That link has expired or was already used.", response.content.decode())

    def test_a_wrong_token_does_not_confirm(self):
        self.sign_up()
        user = User.objects.get(email="alex@example.com")
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        response = self.client.get(
            reverse("confirm_email", args=[urlsafe_base64_encode(force_bytes(user.pk)), "abc-123"]), follow=True,
        )
        self.assertIn("That link has expired or was already used.", response.content.decode())
        user.profile.refresh_from_db()
        self.assertFalse(user.profile.email_confirmed)

    def test_link_works_when_logged_out(self):
        self.sign_up()
        link = self.link_from(mail.outbox[0])
        self.client.logout()
        response = self.client.get(link, follow=True)
        self.assertEqual(response.redirect_chain[-1][0], reverse("login"))
        self.assertTrue(UserProfile.objects.get(user__email="alex@example.com").email_confirmed)

    def test_send_the_link_again_waits_a_minute(self):
        self.sign_up()
        self.assertEqual(len(mail.outbox), 1)
        response = self.client.post(reverse("resend_confirmation"), {"next": "/recipes/saved/"}, follow=True)
        self.assertEqual(len(mail.outbox), 1)  # just sent at signup
        self.assertIn("We&#x27;ve just sent one.", response.content.decode())
        self.assertEqual(response.redirect_chain[-1][0], "/recipes/saved/")

        session = self.client.session
        session["confirmation_sent_at"] = 0
        session.save()
        self.client.post(reverse("resend_confirmation"))
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[1].subject, "Confirm your email for CulinaAI")

        # The newest link works.
        self.client.get(self.link_from(mail.outbox[1]))
        self.assertTrue(UserProfile.objects.get(user__email="alex@example.com").email_confirmed)

    def test_send_again_ignores_outside_links(self):
        self.sign_up()
        response = self.client.post(reverse("resend_confirmation"), {"next": "https://evil.example.com/"})
        self.assertEqual(response["Location"], reverse("dashboard"))

    def test_existing_and_admin_made_accounts_are_already_confirmed(self):
        user = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        self.assertTrue(user.profile.email_confirmed)
        self.client.force_login(user)
        self.assertNotIn("site-confirm-bar", self.client.get(reverse("dashboard")).content.decode())

    def test_changing_your_email_needs_confirming_again(self):
        user = User.objects.create_user("cook", "cook@example.com", "pass-12345", first_name="Sam")
        self.client.force_login(user)
        response = self.client.post(reverse("profile_summary"), {
            "form_type": "profile_update", "first_name": "Sam", "last_name": "", "username": "cook",
            "email": "sam@example.com", "bio": "",
        }, follow=True)
        self.assertIn("We&#x27;ve sent a link to sam@example.com", response.content.decode())
        user.profile.refresh_from_db()
        self.assertFalse(user.profile.email_confirmed)
        self.assertEqual(mail.outbox[-1].to, ["sam@example.com"])
        self.assertIn("Not confirmed yet", response.content.decode())

    @override_settings(EMAIL_CONFIRMATION_REQUIRED=False)
    def test_can_be_turned_off(self):
        self.sign_up()
        self.assertTrue(UserProfile.objects.get(user__email="alex@example.com").email_confirmed)
        self.assertIn("Log in", mail.outbox[0].body)


class DownloadAndDeleteTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(
            MEDIA_ROOT=self.media,
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
            },
        )
        override.enable()
        self.addCleanup(override.disable)

        self.user = User.objects.create_user("cook", "cook@example.com", "pass-12345", first_name="Sam")
        self.other = User.objects.create_user("friend", "friend@example.com", "pass-12345")
        self.recipe = make_recipe(self.user, is_public=True)
        self.recipe.generated_image.save("mine.png", ContentFile(b"png"), save=True)
        FavouriteRecipe.objects.create(user=self.user, recipe=self.recipe)
        PantryItem.objects.create(user=self.user, ingredient_name="rice", unit="g")
        self.client.force_login(self.user)

    def test_download_has_everything_and_no_password(self):
        response = self.client.get(reverse("download_my_data"))
        self.assertEqual(response["Content-Type"], "application/json; charset=utf-8")
        self.assertIn('attachment; filename="culinaai-data-cook-', response["Content-Disposition"])
        data = json.loads(response.content)
        self.assertEqual(data["account"]["email"], "cook@example.com")
        self.assertEqual([r["title"] for r in data["recipes"]], ["Lemon Rice"])
        self.assertEqual(data["favourites"][0]["recipe"], str(self.recipe))
        self.assertEqual(data["pantry"][0]["ingredient_name"], "rice")
        self.assertIn("mine", data["recipes"][0]["generated_image"])
        self.assertNotIn("pbkdf2", response.content.decode())
        self.assertNotIn("password", data["account"])

    def test_wrong_password_deletes_nothing(self):
        response = self.client.post(reverse("delete_account"), {"password": "nope"})
        self.assertContains(response, "That password isn&#x27;t right.")
        self.assertTrue(User.objects.filter(username="cook").exists())

    def test_delete_page_says_what_goes(self):
        html = self.client.get(reverse("delete_account")).content.decode()
        self.assertIn("1 saved recipe, including 1 you shared with other cooks", html)
        self.assertIn("1 pantry item", html)

    def test_delete_removes_the_account_its_rows_and_its_own_images(self):
        image_name = self.recipe.generated_image.name
        # A file another account also uses must stay.
        shared = make_recipe(self.other, title="Copy")
        shared_history = RecipeHistory.objects.create(
            user=self.user, title="Shared", recipe_text=RECIPE_TEXT, ingredients_text="rice",
        )
        shared_history.generated_image.save("shared.png", ContentFile(b"png"), save=True)
        Recipe.objects.filter(id=shared.id).update(generated_image=shared_history.generated_image.name)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("delete_account"), {"password": "pass-12345"}, follow=True)

        self.assertIn("Your account and everything in it has been deleted.", response.content.decode())
        self.assertFalse(User.objects.filter(username="cook").exists())
        self.assertFalse(Recipe.objects.filter(user__username="cook").exists())
        self.assertFalse(PantryItem.objects.exists())
        self.assertFalse(default_storage.exists(image_name))
        self.assertTrue(default_storage.exists(shared_history.generated_image.name))
        self.assertTrue(User.objects.filter(username="friend").exists())
        # Logged out.
        self.assertNotIn("site-account-button", response.content.decode())

    def test_profile_links_to_both(self):
        html = self.client.get(reverse("profile_summary")).content.decode()
        self.assertIn(reverse("download_my_data"), html)
        self.assertIn(reverse("delete_account"), html)
        self.assertIn("Confirmed", html)


class PageNumberTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        for number in range(15):
            make_recipe(cls.user, title=f"Rice dish {number:02d}")
            RecipeHistory.objects.create(
                user=cls.user, title=f"History {number}", recipe_text=RECIPE_TEXT, ingredients_text="rice",
            )

    def setUp(self):
        self.client.force_login(self.user)

    def test_saved_list_is_split_into_pages_and_keeps_the_search(self):
        html = self.client.get(reverse("saved_recipes"), {"q": "rice"}).content.decode()
        self.assertEqual(html.count('class="rl-item"'), 12)
        self.assertIn("15 recipes match your filters.", html)
        self.assertIn("?q=rice&amp;page=2", html)
        self.assertIn("Showing 1–12 of 15", html)

        html = self.client.get(reverse("saved_recipes"), {"q": "rice", "page": 2}).content.decode()
        self.assertEqual(html.count('class="rl-item"'), 3)
        self.assertIn('aria-current="page">2<', html)

    def test_a_page_past_the_end_shows_the_last_page(self):
        html = self.client.get(reverse("saved_recipes"), {"page": 99}).content.decode()
        self.assertEqual(html.count('class="rl-item"'), 3)

    def test_history_and_favourites_have_pages(self):
        html = self.client.get(reverse("recipe_history")).content.decode()
        self.assertNotIn("site-pages", html)  # 15 fits on one page of 20
        for recipe in Recipe.objects.all():
            FavouriteRecipe.objects.create(user=self.user, recipe=recipe)
        html = self.client.get(reverse("favourite_recipes")).content.decode()
        self.assertIn("site-pages", html)
        self.assertIn("15 recipes.", html)


class MessageTests(TestCase):
    def test_messages_can_be_closed(self):
        user = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        self.client.force_login(user)
        response = self.client.post(reverse("toggle_favourite_recipe", args=[make_recipe(user).id]), follow=True)
        html = response.content.decode()
        self.assertIn("data-message-close", html)
        self.assertIn('role="status"', html)
