"""
Part B: the weekly meal plan, "Add to plan" and the combined shopping list.
"""

import json
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from recipes.meal_plan_service import (
    build_shopping_list,
    copy_week,
    format_grams,
    line_display_name,
    long_day,
    recipe_base_servings,
    shopping_list_text,
    strip_quantity,
    week_label,
    week_start_for,
)
from recipes.models import MealPlanEntry, PantryItem, Recipe, ShoppingListCheck, ShoppingListExtra


def insights(servings, *ingredients):
    return {
        "available": True,
        "nutrition": {"servings": servings},
        "ingredients": [{"name": name, "grams": grams, "display": f"{grams} g"} for name, grams in ingredients],
    }


def make_recipe(user, title, ingredients_text="rice", recipe_insights=None, **extra):
    return Recipe.objects.create(
        user=user, title=title, ingredients_text=ingredients_text, instructions_text="SERVINGS:\n4\n",
        cooking_time_minutes=30, difficulty="easy", insights=recipe_insights or {}, **extra,
    )


class HelperTests(SimpleTestCase):
    def test_weeks_start_on_monday(self):
        self.assertEqual(week_start_for(date(2026, 10, 15)), date(2026, 10, 12))
        self.assertEqual(week_start_for(date(2026, 10, 12)), date(2026, 10, 12))
        self.assertEqual(week_start_for(date(2026, 10, 18)), date(2026, 10, 12))

    def test_week_labels(self):
        self.assertEqual(week_label(date(2026, 10, 12)), "12 – 18 Oct 2026")
        self.assertEqual(week_label(date(2026, 10, 26)), "26 Oct – 1 Nov 2026")
        self.assertEqual(week_label(date(2026, 12, 28)), "28 Dec 2026 – 3 Jan 2027")

    def test_day_names_for_messages(self):
        today = date(2026, 10, 15)
        self.assertEqual(long_day(today, today), "today (Thu 15 Oct)")
        self.assertEqual(long_day(date(2026, 10, 16), today), "tomorrow (Fri 16 Oct)")
        self.assertEqual(long_day(date(2026, 10, 20), today), "Tuesday 20 Oct")

    def test_amounts_are_rounded_the_way_you_shop(self):
        self.assertEqual(format_grams(3.2), "about 3 g")
        self.assertEqual(format_grams(87), "about 85 g")
        self.assertEqual(format_grams(452), "about 450 g")
        self.assertEqual(format_grams(999), "about 1 kg")
        self.assertEqual(format_grams(1240), "about 1.2 kg")

    def test_written_lines_are_named_and_grouped(self):
        self.assertEqual(line_display_name("3 garlic cloves, crushed"), "Garlic cloves")
        self.assertEqual(line_display_name("4 chicken thighs, skinless (about 500 g)"), "Chicken thighs")
        self.assertEqual(line_display_name("200 ml coconut milk"), "Coconut milk")
        self.assertEqual(strip_quantity("4 chicken thighs, skinless (about 500 g)"), strip_quantity("chicken thighs"))


class ShoppingListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        cls.week = week_start_for(timezone.localdate())
        cls.curry = make_recipe(cls.user, "Chickpea Curry", recipe_insights=insights(
            2, ("chickpeas", 400), ("red onion", 150), ("basmati rice", 200), ("water", 300), ("red pepper", 100),
        ))
        cls.salad = make_recipe(cls.user, "Rice Salad", recipe_insights=insights(
            4, ("basmati rice", 300), ("red onion", 100), ("olive oil", 20),
        ))
        cls.old = make_recipe(cls.user, "Old Soup", ingredients_text="- 2 carrots, diced\n- 1 litre stock")

    def plan(self, recipe, day_offset, servings, meal="dinner"):
        return MealPlanEntry.objects.create(
            user=self.user, recipe=recipe, date=self.week + timedelta(days=day_offset), meal=meal, servings=servings,
        )

    def items(self, shopping):
        return {item["key"]: item for group in shopping["groups"] for item in group["items"]}

    def test_same_ingredient_is_added_up_and_scaled_to_the_servings(self):
        self.plan(self.curry, 0, 4)   # double the recipe
        self.plan(self.salad, 2, 2)   # half the recipe
        shopping = build_shopping_list(self.user, self.week)
        items = self.items(shopping)

        # Rice: 200 g x 2 + 300 g x 0.5 = 550 g
        self.assertEqual(items["basmati rice"]["amount"], "about 550 g")
        # Onion: 150 x 2 + 100 x 0.5 = 350 g
        self.assertEqual(items["red onion"]["amount"], "about 350 g")
        self.assertEqual(items["chickpea"]["amount"], "about 800 g")
        self.assertEqual(items["red onion"]["uses"], ["Chickpea Curry (Mon)", "Rice Salad (Wed)"])
        self.assertNotIn("water", items)
        self.assertEqual(shopping["recipe_count"], 2)

    def test_same_recipe_on_two_days_lists_the_days_once(self):
        self.plan(self.curry, 0, 2)
        self.plan(self.curry, 3, 2, meal="lunch")
        items = self.items(build_shopping_list(self.user, self.week))
        self.assertEqual(items["chickpea"]["uses"], ["Chickpea Curry (Mon, Thu)"])
        self.assertEqual(items["chickpea"]["amount"], "about 800 g")

    def test_pantry_items_move_to_you_may_already_have(self):
        PantryItem.objects.create(user=self.user, ingredient_name="Rice", unit="g")
        PantryItem.objects.create(user=self.user, ingredient_name="Black pepper", unit="g")
        PantryItem.objects.create(
            user=self.user, ingredient_name="Chickpeas", unit="g", expiry_date=timezone.localdate() - timedelta(days=1),
        )
        self.plan(self.curry, 0, 2)
        shopping = build_shopping_list(self.user, self.week)
        have = {item["key"]: item for item in shopping["have"]}
        self.assertEqual(have["basmati rice"]["pantry_name"], "Rice")
        # "Black pepper" doesn't count as "red pepper", and out-of-date chickpeas don't count.
        self.assertIn("red pepper", self.items(shopping))
        self.assertIn("chickpea", self.items(shopping))

    def test_older_recipes_list_their_lines_as_written(self):
        self.plan(self.old, 1, 2)
        shopping = build_shopping_list(self.user, self.week)
        items = self.items(shopping)
        self.assertTrue(shopping["has_unscaled"])
        self.assertEqual(items["carrot"]["name"], "Carrots")
        self.assertEqual(items["carrot"]["amount"], "")
        self.assertEqual(items["carrot"]["lines"], ["2 carrots, diced (recipe serves 4, planned for 2) – Old Soup"])

    def test_other_weeks_other_users_and_unsaved_recipes_are_left_out(self):
        other = User.objects.create_user("friend", "friend@example.com", "pass-12345")
        MealPlanEntry.objects.create(user=other, recipe=make_recipe(other, "Theirs"), date=self.week, servings=2)
        self.plan(self.curry, 7, 2)  # next week
        unsaved = make_recipe(self.user, "Not saved", is_saved=False, recipe_insights=insights(2, ("tofu", 200)))
        self.plan(unsaved, 0, 2)
        shopping = build_shopping_list(self.user, self.week)
        self.assertEqual(shopping["recipe_count"], 0)
        self.assertEqual(shopping["groups"], [])

    def test_ticks_and_text(self):
        self.plan(self.salad, 0, 4)
        ShoppingListCheck.objects.create(user=self.user, week_start=self.week, item_key="olive oil")
        ShoppingListExtra.objects.create(user=self.user, week_start=self.week, name="Bin bags")
        shopping = build_shopping_list(self.user, self.week)
        self.assertTrue(self.items(shopping)["olive oil"]["done"])
        self.assertEqual(shopping["done_count"], 1)
        self.assertEqual(shopping["to_buy_count"], 4)  # rice, onion, oil + bin bags
        text = shopping_list_text(shopping, self.week)
        self.assertIn("[x] Olive oil, about 20 g", text)
        self.assertIn("[ ] Bin bags", text)

    def test_base_servings(self):
        self.assertEqual(recipe_base_servings(self.curry), 2)  # from the worked-out nutrition
        self.assertEqual(recipe_base_servings(self.old), 4)  # from the SERVINGS: line
        self.old.instructions_text = ""
        self.assertEqual(recipe_base_servings(self.old), 2)  # default

    def test_copy_last_week_skips_meals_already_there(self):
        self.plan(self.curry, 0, 2)
        self.plan(self.salad, 2, 3, meal="lunch")
        self.assertEqual(copy_week(self.user, self.week, self.week + timedelta(days=7)), 2)
        self.assertEqual(copy_week(self.user, self.week, self.week + timedelta(days=7)), 0)
        copied = MealPlanEntry.objects.get(date=self.week + timedelta(days=9))
        self.assertEqual((copied.recipe, copied.meal, copied.servings), (self.salad, "lunch", 3))


class MealPlanPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        cls.other = User.objects.create_user("friend", "friend@example.com", "pass-12345")
        cls.recipe = make_recipe(cls.user, "Chickpea Curry", recipe_insights=insights(2, ("chickpeas", 400)))
        cls.theirs = make_recipe(cls.other, "Their Pie")
        cls.today = timezone.localdate()
        cls.week = week_start_for(cls.today)

    def setUp(self):
        self.client.force_login(self.user)

    def test_needs_login(self):
        self.client.logout()
        for name in ("meal_plan", "meal_plan_add", "shopping_list"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 302)

    def test_plan_page_shows_the_week(self):
        MealPlanEntry.objects.create(user=self.user, recipe=self.recipe, date=self.today, meal="lunch", servings=3)
        MealPlanEntry.objects.create(user=self.other, recipe=self.theirs, date=self.today, servings=2)
        html = self.client.get(reverse("meal_plan")).content.decode()
        self.assertIn("Chickpea Curry", html)
        self.assertNotIn("Their Pie", html)
        self.assertIn("This week", html)
        self.assertIn("Today", html)
        self.assertEqual(html.count('<li class="mp-day'), 7)
        self.assertIn("Shopping list (1 meal)", html)

    def test_other_weeks(self):
        next_week = self.week + timedelta(days=7)
        html = self.client.get(reverse("meal_plan"), {"week": next_week.isoformat()}).content.decode()
        self.assertIn("Back to this week", html)
        self.assertIn(f"?week={(next_week + timedelta(days=7)).isoformat()}", html)
        # Any day of a week opens that week; nonsense opens this week.
        html = self.client.get(reverse("meal_plan"), {"week": "rubbish"}).content.decode()
        self.assertIn("This week", html)

    def test_add_from_a_recipe_goes_back_to_it(self):
        back = reverse("saved_recipe_detail", args=[self.recipe.id])
        page = self.client.get(reverse("meal_plan_add"), {"recipe": self.recipe.id, "next": back}).content.decode()
        self.assertIn("Chickpea Curry", page)
        self.assertIn("The recipe is written for 2.", page)

        day = self.today + timedelta(days=2)
        response = self.client.post(reverse("meal_plan_add"), {
            "recipe": self.recipe.id, "date": day.isoformat(), "meal": "lunch", "servings": "5", "next": back,
        })
        self.assertRedirects(response, back, fetch_redirect_response=False)
        entry = MealPlanEntry.objects.get(user=self.user)
        self.assertEqual((entry.date, entry.meal, entry.servings), (day, "lunch", 5))

    def test_add_from_a_day_picks_the_recipe_there(self):
        day = self.today + timedelta(days=1)
        page = self.client.get(reverse("meal_plan_add"), {"date": day.isoformat()}).content.decode()
        self.assertIn("Choose a saved recipe", page)
        self.assertIn(f'value="{day.isoformat()}" selected', page)
        self.assertNotIn("Their Pie", page)

        response = self.client.post(reverse("meal_plan_add"), {"date": day.isoformat(), "meal": "dinner"}, follow=True)
        self.assertIn("Choose a recipe.", response.content.decode())

        response = self.client.post(
            reverse("meal_plan_add"), {"recipe": self.recipe.id, "date": day.isoformat(), "meal": "dinner"}, follow=True,
        )
        self.assertIn("tomorrow", response.content.decode())
        self.assertEqual(MealPlanEntry.objects.get().servings, 2)  # the recipe's own servings

    def test_cannot_plan_someone_elses_recipe_or_a_silly_date(self):
        self.client.post(reverse("meal_plan_add"), {"recipe": self.theirs.id, "date": self.today.isoformat()})
        self.client.post(reverse("meal_plan_add"), {"recipe": self.recipe.id, "date": "2099-01-01"})
        self.assertFalse(MealPlanEntry.objects.exists())

    def test_change_servings_move_and_remove(self):
        entry = MealPlanEntry.objects.create(user=self.user, recipe=self.recipe, date=self.today, servings=2)
        url = reverse("meal_plan_update", args=[entry.id])
        self.client.post(url, {"servings": "50"})
        entry.refresh_from_db()
        self.assertEqual(entry.servings, MealPlanEntry.MAX_SERVINGS)
        self.client.post(url, {"servings": "0"})
        entry.refresh_from_db()
        self.assertEqual(entry.servings, 1)

        new_day = self.today + timedelta(days=3)
        self.client.post(url, {"servings": "2", "date": new_day.isoformat(), "meal": "breakfast"})
        entry.refresh_from_db()
        self.assertEqual((entry.date, entry.meal), (new_day, "breakfast"))

        self.client.post(reverse("meal_plan_remove", args=[entry.id]))
        self.assertFalse(MealPlanEntry.objects.exists())

    def test_cannot_touch_someone_elses_plan(self):
        entry = MealPlanEntry.objects.create(user=self.other, recipe=self.theirs, date=self.today, servings=2)
        self.assertEqual(self.client.post(reverse("meal_plan_update", args=[entry.id]), {"servings": 9}).status_code, 404)
        self.assertEqual(self.client.post(reverse("meal_plan_remove", args=[entry.id])).status_code, 404)

    def test_copy_last_week_button(self):
        MealPlanEntry.objects.create(user=self.user, recipe=self.recipe, date=self.week - timedelta(days=5), servings=2)
        html = self.client.get(reverse("meal_plan")).content.decode()
        self.assertIn("Copy last week", html)
        response = self.client.post(reverse("meal_plan_copy"), {"week": self.week.isoformat()}, follow=True)
        self.assertIn("Copied 1 meal from last week.", response.content.decode())

    def test_links_from_the_rest_of_the_site(self):
        MealPlanEntry.objects.create(user=self.user, recipe=self.recipe, date=self.today, meal="dinner", servings=2)
        nav = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn(f'href="{reverse("meal_plan")}">Plan</a>', nav)
        self.assertIn("Coming up", nav)
        self.assertIn("Chickpea Curry", nav)
        detail = self.client.get(reverse("saved_recipe_detail", args=[self.recipe.id])).content.decode()
        self.assertIn(f'{reverse("meal_plan_add")}?recipe={self.recipe.id}', detail)
        saved = self.client.get(reverse("saved_recipes")).content.decode()
        self.assertIn('class="rl-plan"', saved)

    def test_data_download_includes_the_plan(self):
        MealPlanEntry.objects.create(user=self.user, recipe=self.recipe, date=self.today, servings=2)
        data = json.loads(self.client.get(reverse("download_my_data")).content)
        self.assertEqual(data["meal_plan"][0]["recipe"], str(self.recipe))


class ShoppingListPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        cls.recipe = make_recipe(cls.user, "Chickpea Curry", recipe_insights=insights(2, ("chickpeas", 400), ("lime", 50)))
        cls.week = week_start_for(timezone.localdate())
        MealPlanEntry.objects.create(user=cls.user, recipe=cls.recipe, date=timezone.localdate(), servings=2)

    def setUp(self):
        self.client.force_login(self.user)

    def test_page(self):
        html = self.client.get(reverse("shopping_list")).content.decode()
        self.assertIn("Chickpeas", html)
        self.assertIn("about 400 g", html)
        self.assertIn("For Chickpea Curry", html)
        self.assertIn("0</strong> of <span data-total-count>2</span> ticked", html)

    def test_empty_week(self):
        html = self.client.get(reverse("shopping_list"), {"week": "2026-01-05"}).content.decode()
        self.assertIn("Nothing planned this week", html)

    def test_ticking_with_and_without_javascript(self):
        url = reverse("shopping_toggle")
        data = {"week": self.week.isoformat(), "key": "chickpea"}
        response = self.client.post(url, data, HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(response.json(), {"ok": True, "done": True})
        response = self.client.post(url, data)  # no JavaScript: back to the list
        self.assertRedirects(response, f"{reverse('shopping_list')}?week={self.week.isoformat()}", fetch_redirect_response=False)
        self.assertFalse(ShoppingListCheck.objects.exists())

    def test_extras(self):
        self.client.post(reverse("shopping_extra_add"), {"week": self.week.isoformat(), "name": "  Bin   bags "})
        extra = ShoppingListExtra.objects.get()
        self.assertEqual(extra.name, "Bin bags")
        self.client.post(reverse("shopping_extra_toggle", args=[extra.id]), HTTP_X_REQUESTED_WITH="fetch")
        extra.refresh_from_db()
        self.assertTrue(extra.done)
        html = self.client.get(reverse("shopping_list")).content.decode()
        self.assertIn("Bin bags", html)
        self.client.post(reverse("shopping_clear_ticks"), {"week": self.week.isoformat()})
        extra.refresh_from_db()
        self.assertFalse(extra.done)
        self.client.post(reverse("shopping_extra_remove", args=[extra.id]))
        self.assertFalse(ShoppingListExtra.objects.exists())

        other = User.objects.create_user("friend", "friend@example.com", "pass-12345")
        theirs = ShoppingListExtra.objects.create(user=other, week_start=self.week, name="Theirs")
        self.assertEqual(self.client.post(reverse("shopping_extra_remove", args=[theirs.id])).status_code, 404)

    def test_email_the_list_once_a_minute(self):
        url = reverse("shopping_email")
        response = self.client.post(url, {"week": self.week.isoformat()}, follow=True)
        self.assertIn("Sent the list to cook@example.com.", response.content.decode())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["cook@example.com"])
        self.assertIn("Chickpeas, about 400 g", mail.outbox[0].body)

        response = self.client.post(url, {"week": self.week.isoformat()}, follow=True)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("We&#x27;ve just sent it.", response.content.decode())
