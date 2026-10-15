"""
Part C: "Use it before it goes off", the Sunday email (and the weekly job that
sends it), and "Try the demo". Also the diet check no longer treating plant
milks and nut butters as dairy.
"""

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from recipes.demo_service import create_demo_user, delete_old_demo_users
from recipes.meal_plan_service import week_start_for
from recipes.models import AIUsage, MealPlanEntry, PantryItem, Recipe
from recipes.recipe_quality_engine import check_diet_compliance
from recipes.tests.test_generation_flow import FORM
from recipes.use_soon_service import going_off, recipes_using, use_soon_context, when_label
from recipes.weekly_email_service import build_weekly_email, send_weekly_emails, unsubscribe_token


def recipe_with(user, title, *names):
    return Recipe.objects.create(
        user=user, title=title, ingredients_text=", ".join(names), instructions_text="SERVINGS:\n2\n",
        cooking_time_minutes=20, difficulty="easy",
        insights={"available": True, "nutrition": {"servings": 2},
                  "ingredients": [{"name": n, "grams": 100, "display": "100 g"} for n in names]},
    )


def pantry(user, name, days):
    return PantryItem.objects.create(
        user=user, ingredient_name=name, unit="g",
        expiry_date=timezone.localdate() + timedelta(days=days) if days is not None else None,
    )


class DietCheckTests(SimpleTestCase):
    def conflicts(self, text, diet="Vegan"):
        return check_diet_compliance({"diet_preferences": [diet]}, text)["details"].get("conflicting_terms")

    def test_plant_milks_and_nut_butters_are_not_dairy(self):
        self.assertIsNone(self.conflicts("- 400 ml coconut milk\n- 2 tbsp peanut butter\n- 1 tin butter beans"))
        self.assertIsNone(self.conflicts("- 200 ml oat milk\n- 100 g soya yoghurt"))

    def test_real_dairy_still_fails(self):
        self.assertEqual(self.conflicts("- 200 ml milk"), ["milk"])
        self.assertEqual(self.conflicts("- 20 g butter\n- coconut milk"), ["butter"])
        self.assertEqual(self.conflicts("- oat milk and a splash of milk"), ["milk"])


class UseSoonTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")

    def setUp(self):
        self.client.force_login(self.user)

    def test_labels(self):
        self.assertEqual(when_label(0), "use today")
        self.assertEqual(when_label(1), "use by tomorrow")
        self.assertEqual(when_label(3), "use within 3 days")
        self.assertEqual(when_label(-1), "past its date")

    def test_what_is_going_off_and_which_recipes_use_it(self):
        pantry(self.user, "Spinach", 1)
        pantry(self.user, "Yoghurt", 0)
        pantry(self.user, "Rice", 10)       # not soon
        pantry(self.user, "Flour", None)    # no date
        pantry(self.user, "Milk", -2)       # past its date
        curry = recipe_with(self.user, "Spinach Curry", "spinach", "chickpeas", "natural yoghurt")
        recipe_with(self.user, "Spinach Salad", "baby spinach", "lemon")
        recipe_with(self.user, "Rice Pudding", "rice", "milk")

        soon = going_off(self.user)
        self.assertEqual([entry["name"] for entry in soon], ["Yoghurt", "Spinach"])

        ideas = recipes_using(self.user, soon)
        self.assertEqual(ideas[0]["recipe"], curry)
        self.assertEqual(ideas[0]["uses"], ["Yoghurt", "Spinach"])
        self.assertEqual([idea["recipe"].title for idea in ideas], ["Spinach Curry", "Spinach Salad"])

        context = use_soon_context(self.user)
        self.assertEqual([item.ingredient_name for item in context["out_of_date"]], ["Milk"])
        self.assertIn("use_up=Yoghurt%2C+Spinach", context["new_recipe_url"])

    def test_dashboard_card(self):
        pantry(self.user, "Spinach", 1)
        pantry(self.user, "Milk", -1)
        recipe_with(self.user, "Spinach Curry", "spinach")
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("Use it before it goes off", html)
        self.assertIn("use by tomorrow", html)
        self.assertIn("Spinach Curry", html)
        self.assertIn("Past its date: Milk", html)
        self.assertIn("Make a new recipe with it", html)
        self.assertIn("Get a Sunday email", html)

    def test_dashboard_without_pantry_or_dates(self):
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertNotIn('id="us-title"', html)
        pantry(self.user, "Flour", None)
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("Add use-by dates to your pantry items", html)

    def test_new_recipe_form_is_filled_in(self):
        response = self.client.get(reverse("generate_recipe"), {"use_up": "Spinach, Yoghurt"})
        html = response.content.decode()
        self.assertIn("Spinach, Yoghurt", html)
        self.assertIn("Added what needs using up from your pantry.", html)


class WeeklyEmailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("cook", "cook@example.com", "pass-12345", first_name="Sam")
        UserProfile.objects.filter(user=cls.user).update(weekly_email=True)
        cls.today = timezone.localdate()

    def plan_next_week(self):
        recipe = recipe_with(self.user, "Spinach Curry", "spinach")
        monday = week_start_for(self.today) + timedelta(days=7)
        MealPlanEntry.objects.create(user=self.user, recipe=recipe, date=monday + timedelta(days=2), servings=2)

    def test_nothing_to_say_means_no_email(self):
        self.assertIsNone(build_weekly_email(self.user, "https://example.com", self.today))
        counts = send_weekly_emails("https://example.com", self.today)
        self.assertEqual(counts, {"sent": 0, "nothing_to_say": 1, "failed": 0})
        self.assertEqual(len(mail.outbox), 0)

    def test_email_has_what_goes_off_and_next_weeks_plan(self):
        pantry(self.user, "Spinach", 2)
        pantry(self.user, "Milk", -1)
        self.plan_next_week()
        send_weekly_emails("https://example.com", self.today)
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ["cook@example.com"])
        self.assertIn("Hi Sam", email.body)
        self.assertIn("Spinach: use within 2 days", email.body)
        self.assertIn("Already past their date: Milk", email.body)
        self.assertIn("Spinach Curry", email.body)
        self.assertIn("https://example.com/recipes/shopping/?week=", email.body)
        self.assertIn("https://example.com/weekly-email/off/", email.body)
        self.assertIn("List-Unsubscribe", email.extra_headers)
        self.assertIn("Turn it off", email.alternatives[0][0])

    def test_only_for_people_who_turned_it_on_and_not_twice_a_week(self):
        other = User.objects.create_user("other", "other@example.com", "pass-12345")  # didn't turn it on
        pantry(other, "Spinach", 1)
        pantry(self.user, "Spinach", 1)
        self.assertEqual(send_weekly_emails("https://example.com", self.today)["sent"], 1)
        self.assertEqual(send_weekly_emails("https://example.com", self.today)["sent"], 0)
        self.assertEqual(send_weekly_emails("https://example.com", self.today + timedelta(days=7))["sent"], 1)
        self.assertEqual({m.to[0] for m in mail.outbox}, {"cook@example.com"})

    def test_unconfirmed_and_demo_accounts_get_nothing(self):
        pantry(self.user, "Spinach", 1)
        UserProfile.objects.filter(user=self.user).update(email_confirmed=False)
        self.assertEqual(send_weekly_emails("https://example.com", self.today)["sent"], 0)
        UserProfile.objects.filter(user=self.user).update(email_confirmed=True, is_demo=True)
        self.assertEqual(send_weekly_emails("https://example.com", self.today)["sent"], 0)

    def test_turn_off_link_works_without_logging_in(self):
        url = reverse("weekly_email_off", args=[unsubscribe_token(self.user)])
        html = self.client.get(url).content.decode()
        self.assertIn("Turn off the Sunday email?", html)
        self.assertTrue(UserProfile.objects.get(user=self.user).weekly_email)  # opening the link alone changes nothing
        html = self.client.post(url).content.decode()
        self.assertIn("The Sunday email is off", html)
        self.assertFalse(UserProfile.objects.get(user=self.user).weekly_email)

        response = self.client.get(reverse("weekly_email_off", args=["not-a-real-token"]))
        self.assertEqual(response.status_code, 400)

    def test_turn_on_and_off_from_the_site(self):
        self.client.force_login(self.user)
        self.client.post(reverse("weekly_email_toggle"), {"on": "0"})
        self.assertFalse(UserProfile.objects.get(user=self.user).weekly_email)
        response = self.client.post(reverse("weekly_email_toggle"), {"on": "1", "next": "/dashboard/"}, follow=True)
        self.assertTrue(UserProfile.objects.get(user=self.user).weekly_email)
        self.assertIn("on Sunday evenings", response.content.decode())
        self.assertIn("Turn off", self.client.get(reverse("profile_summary")).content.decode())

    @override_settings(CRON_SECRET="")
    def test_job_address_is_off_without_a_secret(self):
        self.assertEqual(self.client.post(reverse("weekly_tasks")).status_code, 404)

    @override_settings(CRON_SECRET="s3cret-value")
    def test_job_address_needs_the_secret(self):
        url = reverse("weekly_tasks")
        self.assertEqual(self.client.post(url, HTTP_AUTHORIZATION="Bearer wrong").status_code, 403)
        self.assertEqual(self.client.get(url, HTTP_AUTHORIZATION="Bearer s3cret-value").status_code, 405)

        pantry(self.user, "Spinach", 1)
        old_demo = create_demo_user()
        User.objects.filter(id=old_demo.id).update(date_joined=timezone.now() - timedelta(days=2))
        response = self.client.post(url, HTTP_AUTHORIZATION="Bearer s3cret-value")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["emails"]["sent"], 1)
        self.assertEqual(response.json()["demo_accounts_deleted"], 1)
        self.assertIn("http://testserver/recipes/", mail.outbox[0].body)

    def test_management_command(self):
        pantry(self.user, "Spinach", 1)
        out = StringIO()
        call_command("send_weekly_emails", stdout=out)
        self.assertIn("Sunday emails: 1 sent", out.getvalue())


class DemoAccountTests(TestCase):
    def setUp(self):
        cache.clear()

    def start(self, **extra):
        return self.client.post(reverse("start_demo"), follow=True, **extra)

    def demo_user(self):
        return User.objects.get(profile__is_demo=True)

    def test_start_logs_into_a_full_account(self):
        response = self.start()
        html = response.content.decode()
        self.assertEqual(response.redirect_chain[-1][0], reverse("dashboard"))
        self.assertIn("Welcome to the demo.", html)
        self.assertIn("You&#x27;re trying the demo.", html.replace("'", "&#x27;"))
        self.assertIn("Use it before it goes off", html)
        user = self.demo_user()
        self.assertFalse(user.has_usable_password())
        self.assertTrue(user.email.endswith("@demo.invalid"))
        self.assertEqual(user.recipes.filter(is_saved=True).count(), 4)
        self.assertEqual(user.favourite_recipes.count(), 2)
        self.assertEqual(user.meal_plan_entries.count(), 7)
        self.assertGreater(user.pantry_items.filter(expiry_date__isnull=False).count(), 0)
        # Every page works for a demo account.
        recipe = user.recipes.first()
        for url in (reverse("saved_recipes"), reverse("meal_plan"), reverse("shopping_list"), reverse("pantry_list"),
                    reverse("recipe_history"), reverse("saved_recipe_detail", args=[recipe.id]), reverse("profile_summary")):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_each_visitor_gets_their_own(self):
        self.start()
        other = self.client_class()
        other.post(reverse("start_demo"))
        self.assertEqual(UserProfile.objects.filter(is_demo=True).count(), 2)

    @patch("recipes.generate_views.run_recipe_generation")
    def test_no_ai_in_the_demo(self, run):
        self.start()
        response = self.client.post(reverse("generate_recipe"), FORM)
        run.assert_not_called()
        self.assertIn("The demo shows recipes that are already made", response.content.decode())
        self.assertFalse(AIUsage.objects.exists())
        self.assertIn("The demo doesn't make new AI recipes.", self.client.get(reverse("generate_recipe")).content.decode())

    @override_settings(DEMO_DAILY_RECIPE_LIMIT=1)
    @patch("recipes.generate_views.run_recipe_generation")
    def test_ai_can_be_allowed_a_little(self, run):
        self.start()
        self.client.post(reverse("generate_recipe"), FORM)
        self.client.post(reverse("generate_recipe"), FORM)
        self.assertEqual(run.call_count, 1)

    def test_no_emails_sharing_or_account_changes(self):
        self.start()
        user = self.demo_user()
        recipe = user.recipes.first()
        response = self.client.post(
            reverse("send_recipe_email", args=[recipe.id]), {"recipient_email": "someone@example.com"},
            HTTP_REFERER=reverse("saved_recipe_detail", args=[recipe.id]), follow=True,
        )
        self.assertIn("That isn&#x27;t available in the demo.", response.content.decode())
        self.client.post(reverse("toggle_community_recipe", args=[recipe.id]))
        self.client.post(reverse("shopping_email"), {"week": timezone.localdate().isoformat()})
        self.assertEqual(len(mail.outbox), 0)
        recipe.refresh_from_db()
        self.assertFalse(recipe.is_public)

        self.client.post(reverse("profile_summary"), {"form_type": "profile_update", "email": "me@example.com",
                                                      "username": "hacker", "first_name": "x", "last_name": ""})
        user.refresh_from_db()
        self.assertTrue(user.email.endswith("@demo.invalid"))

        self.client.post(reverse("weekly_email_toggle"), {"on": "1"})
        self.assertFalse(UserProfile.objects.get(user=user).weekly_email)

    def test_logging_out_deletes_it(self):
        self.start()
        response = self.client.get(reverse("logout"), follow=True)
        self.assertIn("You&#x27;ve left the demo", response.content.decode())
        self.assertFalse(User.objects.filter(profile__is_demo=True).exists())
        self.assertFalse(Recipe.objects.exists())

    def test_create_a_free_account_button(self):
        self.start()
        response = self.client.post(reverse("end_demo"))
        self.assertRedirects(response, reverse("signup"), fetch_redirect_response=False)
        self.assertFalse(User.objects.filter(profile__is_demo=True).exists())

    @override_settings(DEMO_STARTS_PER_HOUR=2)
    def test_starts_are_limited_per_address(self):
        for _ in range(2):
            self.client_class().post(reverse("start_demo"), REMOTE_ADDR="10.0.0.5")
        response = self.client.post(reverse("start_demo"), REMOTE_ADDR="10.0.0.5", follow=True)
        self.assertIn("You&#x27;ve started a lot of demos", response.content.decode())
        self.assertEqual(UserProfile.objects.filter(is_demo=True).count(), 2)

    @override_settings(DEMO_MAX_ACCOUNTS=1)
    def test_busy_when_full(self):
        create_demo_user()
        response = self.start()
        self.assertIn("The demo is busy right now.", response.content.decode())

    def test_old_demos_are_deleted_and_real_accounts_never(self):
        real = User.objects.create_user("real", "real@example.com", "pass-12345")
        User.objects.filter(id=real.id).update(date_joined=timezone.now() - timedelta(days=30))
        old = create_demo_user()
        User.objects.filter(id=old.id).update(date_joined=timezone.now() - timedelta(hours=25))
        create_demo_user()  # new one stays
        self.assertEqual(delete_old_demo_users(), 1)
        self.assertTrue(User.objects.filter(username="real").exists())
        self.assertEqual(UserProfile.objects.filter(is_demo=True).count(), 1)

    def test_buttons_on_home_and_login(self):
        self.assertIn(reverse("start_demo"), self.client.get(reverse("home")).content.decode())
        self.assertIn("Try the demo", self.client.get(reverse("login")).content.decode())


class DemoRecipesWithFoodDataTests(TestCase):
    """With the real food data loaded, the demo recipes get nutrition and pass the checks."""

    @classmethod
    def setUpTestData(cls):
        with open("/dev/null", "w") as quiet:
            call_command("load_food_data", stdout=quiet)

    def test_demo_recipes_are_worked_out_and_verified(self):
        user = create_demo_user()
        for recipe in user.recipes.all():
            self.assertTrue(recipe.insights.get("available"), recipe.title)
            self.assertGreater(recipe.insights["nutrition"]["per_serving"]["energy_kcal"], 100, recipe.title)
            self.assertGreaterEqual(recipe.quality_score, 90, recipe.title)
            failed = [c["name"] for c in recipe.validation_report["checks"] if not c["passed"]]
            self.assertEqual(failed, [], recipe.title)
