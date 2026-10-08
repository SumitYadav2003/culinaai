"""
Phase 4: the dashboard's impact cards and weekly balance (impact_service.py), and
the SDG page. Uses stored insights only; no AI calls.
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from recipes.impact_service import build_impact_context, version_savings, weekly_balance
from recipes.models import RecipeHistory


def insights(tag="everyday", salt="green", fibre="Good", protein="High", cost=1.50, carbon=1.00,
             servings=2, complete=True, version=None, original=None):
    """A stored insights dict with just the parts the dashboard reads."""
    lights = {"fat_g": "green", "saturates_g": "green", "sugars_g": "green", "salt_g": salt}
    return {
        "version": 2,
        "available": True,
        "tag": tag if complete else None,
        "nutrition": {"servings": servings, "is_complete": complete, "traffic_lights": lights},
        "nutrition_rows": [
            {"label": "Protein", "light_label": protein if complete else ""},
            {"label": "Fibre", "light_label": fibre if complete else ""},
        ],
        "cost": {"per_serving": cost},
        "carbon": {"per_serving": carbon},
        "basis": {
            "version": version or "",
            "expected": {"original": original} if original else {},
        },
    }


class WeeklyBalanceTests(TestCase):
    def test_counts_and_a_red_nudge_for_salt(self):
        week = weekly_balance([
            insights(tag="treat", salt="red", fibre="Low"),
            insights(tag="treat", salt="red"),
            insights(),
        ])
        self.assertEqual((week["total"], week["everyday"], week["treat"]), (3, 1, 2))
        self.assertEqual(week["high"], [{"nutrient": "salt", "count": 2}])
        self.assertEqual(week["protein"], {"High": 3, "Good": 0, "Low": 0})
        self.assertTrue(week["nudges"][0]["warning"])
        self.assertTrue(week["nudges"][0]["text"].startswith("2 of your 3 recipes this week were high in salt."))

    def test_low_fibre_nudge_and_good_week(self):
        low = weekly_balance([insights(fibre="Low"), insights(fibre="Low")])
        self.assertIn("low in fibre", low["nudges"][0]["text"])

        good = weekly_balance([insights(), insights()])
        self.assertEqual(good["nudges"], [{"warning": False, "text": "All 2 of your recipes this week were everyday healthy."}])

    def test_incomplete_recipes_and_a_single_recipe_give_no_nudge(self):
        week = weekly_balance([insights(tag="treat", salt="red"), insights(complete=False)])
        self.assertEqual(week["total"], 1)  # the incomplete one can't be judged
        self.assertEqual(week["nudges"], [])

    def test_old_source_label_counts_as_good(self):
        week = weekly_balance([insights(protein="Source")])
        self.assertEqual(week["protein"]["Good"], 1)


class VersionSavingsTests(TestCase):
    def test_savings_are_per_serving_times_servings_and_can_be_negative(self):
        savings = version_savings([
            # Cheaper by £0.50 and 1.0 kg a serving, 2 servings: £1.00 and 2.0 kg saved.
            insights(cost=1.00, carbon=0.50, version="Cheapest", original={"cost": 1.50, "carbon": 1.50}),
            # Dearer by £0.20 a serving, 2 servings: £0.40 more. Carbon unknown for the original.
            insights(cost=1.20, carbon=0.80, version="Healthiest", original={"cost": 1.00, "carbon": None}),
            # Not a version: ignored.
            insights(cost=0.10, carbon=0.10),
        ])
        self.assertEqual(savings, {"count": 2, "money": 0.60, "carbon": 2.0})

    def test_no_versions(self):
        self.assertEqual(version_savings([insights()]), {"count": 0, "money": None, "carbon": None})


class ImpactContextTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")

    def add(self, days_ago=0, **kwargs):
        entry = RecipeHistory.objects.create(user=self.user, title="Dish", recipe_text="text", insights=insights(**kwargs))
        RecipeHistory.objects.filter(id=entry.id).update(created_at=timezone.now() - timedelta(days=days_ago))

    def test_all_time_and_this_week(self):
        self.add(cost=1.00, carbon=1.00)
        self.add(tag="treat", salt="red", cost=2.00, carbon=3.00)
        self.add(days_ago=10, tag="treat", salt="red", cost=3.00, carbon=2.00)  # older than a week
        RecipeHistory.objects.create(user=self.user, title="Old", recipe_text="text", insights={})  # before insights

        context = build_impact_context(self.user)
        impact, week = context["impact"], context["week"]
        self.assertEqual((impact["recipes"], impact["judged"], impact["everyday"]), (3, 3, 1))
        self.assertEqual(impact["average_cost"], 2.0)
        self.assertEqual(impact["average_carbon"], 2.0)
        self.assertEqual(week["total"], 2)

    def test_other_users_recipes_are_not_counted(self):
        other = User.objects.create_user("other", "other@example.com", "pass-12345")
        RecipeHistory.objects.create(user=other, title="Dish", recipe_text="text", insights=insights())
        self.assertEqual(build_impact_context(self.user)["impact"]["recipes"], 0)


class PagesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")

    def test_dashboard_shows_impact_and_a_red_nudge(self):
        for _ in range(2):
            RecipeHistory.objects.create(user=self.user, title="Dish", recipe_text="text",
                                         insights=insights(tag="treat", salt="red"))
        self.client.force_login(self.user)
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("Health, cost and carbon across your recipes", html)
        self.assertIn("0 of 2", html)  # everyday healthy
        self.assertIn("culina-nudge-warning", html)
        self.assertIn("2 of your 2 recipes this week were high in salt.", html)
        self.assertIn(reverse("sdg_impact"), html)

    def test_dashboard_with_no_recipes(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("No recipes with complete nutrition in the last 7 days.", html)
        self.assertIn("None yet", html)

    def test_sdg_page_is_public_and_linked_from_the_footer(self):
        response = self.client.get(reverse("sdg_impact"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for goal in ("No Poverty", "Zero Hunger", "Good Health and Well-being", "Responsible Consumption"):
            self.assertIn(goal, html)
        self.assertIn("Supports food affordability", html)
        self.assertIn("The fine print", html)
        self.assertIn(f'href="{reverse("sdg_impact")}"', self.client.get(reverse("about_culinaai")).content.decode())

    def test_signed_in_users_see_their_own_figures(self):
        RecipeHistory.objects.create(user=self.user, title="Dish", recipe_text="text", insights=insights())
        self.client.force_login(self.user)
        html = self.client.get(reverse("sdg_impact")).content.decode()
        self.assertIn("Your kitchen so far", html)
        self.assertIn("1 of 1", html)


class SwapExampleTests(TestCase):
    """The SDG page's example is worked out live from the real data."""

    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command

        with open("/dev/null", "w") as quiet:
            call_command("load_food_data", stdout=quiet)

    def test_half_the_beef_for_lentils(self):
        from recipes.impact_service import swap_example

        example = swap_example()
        self.assertEqual(example["swap"], "Swap half the beef mince for red lentils")
        # Same figures as the bolognese's Cheapest card: 58p and about 6.2 kg CO2e less a serving.
        self.assertEqual(example["per_serving"]["money"], 0.58)
        self.assertAlmostEqual(example["per_serving"]["carbon"], 6.17, places=2)
        self.assertEqual(example["year"]["meals"], 208)
        self.assertEqual(example["year"]["money"], round(0.58 * 208))  # 121
        self.assertGreater(example["after"]["fibre"], example["before"]["fibre"])
        self.assertLess(example["after"]["saturates"], example["before"]["saturates"])

        html = self.client.get(reverse("sdg_impact")).content.decode()
        self.assertIn("£0.58 cheaper and 6.2 kg CO₂e lighter, per serving.", html)
        # The household sliders get the unrounded per-serving figures; without JavaScript
        # the page still shows a family of 4, once a week.
        self.assertIn(f'data-money="{example["per_serving_exact"]["money"]}"', html)
        self.assertIn('data-sdg-people', html)
        self.assertIn(f'£{example["year"]["money"]}', html)
