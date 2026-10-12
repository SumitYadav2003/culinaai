"""
Favourites (the nav link, the hearts on the saved list, the tabs and the button
on the recipe page) and the "changing your recipe" loading box on the saved
recipe page.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from recipes.models import FavouriteRecipe, Recipe
from recipes.tests.test_insights_and_gates import RECIPE_TEXT


class FavouriteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        cls.other = User.objects.create_user("friend", "friend@example.com", "pass-12345")
        cls.recipe = Recipe.objects.create(
            user=cls.user, title="Grilled Chicken Burger", ingredients_text="chicken breast, burger bun",
            instructions_text=RECIPE_TEXT, cooking_time_minutes=25, difficulty="easy",
        )
        cls.second = Recipe.objects.create(
            user=cls.user, title="Lemon Rice", ingredients_text="rice, lemon",
            instructions_text=RECIPE_TEXT, cooking_time_minutes=20, difficulty="easy",
        )

    def setUp(self):
        self.client.force_login(self.user)

    def toggle(self, recipe, **extra):
        return self.client.post(reverse("toggle_favourite_recipe", args=[recipe.id]), extra)

    def test_favourites_link_is_in_the_main_nav(self):
        html = self.client.get(reverse("dashboard")).content.decode()
        nav = html.split('class="navbar-nav')[1].split("</ul>")[0]
        self.assertIn(reverse("favourite_recipes"), nav)
        self.assertIn(">Favourites<", nav.replace("\n", "").replace("  ", ""))

    def test_saved_list_has_a_heart_on_every_card_and_tabs(self):
        FavouriteRecipe.objects.create(user=self.user, recipe=self.recipe)
        html = self.client.get(reverse("saved_recipes")).content.decode()
        self.assertEqual(html.count('class="rl-fav-form"'), 2)
        self.assertEqual(html.count('class="rl-fav is-on"'), 1)
        self.assertIn("Favourites (1)", html)
        self.assertIn('aria-pressed="true"', html)
        self.assertIn('aria-pressed="false"', html)

    def test_heart_adds_then_removes_and_goes_back_to_the_list(self):
        back = reverse("saved_recipes") + "?q=rice"
        response = self.toggle(self.second, next=back)
        self.assertRedirects(response, back, fetch_redirect_response=False)
        self.assertTrue(FavouriteRecipe.objects.filter(user=self.user, recipe=self.second).exists())

        response = self.client.post(
            reverse("toggle_favourite_recipe", args=[self.second.id]), {"next": back}, follow=True,
        )
        self.assertFalse(FavouriteRecipe.objects.filter(user=self.user, recipe=self.second).exists())
        self.assertIn("Removed &quot;Lemon Rice&quot; from favourites.", response.content.decode())

    def test_outside_next_url_is_ignored(self):
        response = self.toggle(self.recipe, next="https://evil.example.com/")
        self.assertRedirects(
            response, reverse("saved_recipe_detail", args=[self.recipe.id]), fetch_redirect_response=False,
        )

    def test_no_next_goes_to_the_recipe(self):
        response = self.toggle(self.recipe)
        self.assertRedirects(
            response, reverse("saved_recipe_detail", args=[self.recipe.id]), fetch_redirect_response=False,
        )

    def test_cannot_favourite_someone_elses_recipe(self):
        self.client.force_login(self.other)
        self.assertEqual(self.toggle(self.recipe).status_code, 404)
        self.assertFalse(FavouriteRecipe.objects.exists())

    def test_favourites_page_has_tabs_and_hearts(self):
        FavouriteRecipe.objects.create(user=self.user, recipe=self.recipe)
        html = self.client.get(reverse("favourite_recipes")).content.decode()
        self.assertIn("All saved", html)
        self.assertEqual(html.count('class="rl-fav is-on"'), 1)
        self.assertNotIn("Lemon Rice", html)

    def test_recipe_page_button_says_what_it_does(self):
        url = reverse("saved_recipe_detail", args=[self.recipe.id])
        html = self.client.get(url).content.decode()
        self.assertIn("rp-fav-btn", html)
        self.assertIn('aria-pressed="false"', html)
        self.assertNotIn("In favourites", html)

        FavouriteRecipe.objects.create(user=self.user, recipe=self.recipe)
        html = self.client.get(url).content.decode()
        self.assertIn("In favourites", html)
        self.assertIn("rp-fav-btn is-on", html)


class ChangeLoadingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("cook", "cook@example.com", "pass-12345")
        cls.recipe = Recipe.objects.create(
            user=cls.user, title="Grilled Chicken Burger", ingredients_text="chicken breast, burger bun",
            instructions_text=RECIPE_TEXT, cooking_time_minutes=25, difficulty="easy",
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_saved_page_has_the_loading_box_for_changes(self):
        html = self.client.get(reverse("saved_recipe_detail", args=[self.recipe.id])).content.decode()
        self.assertIn("data-culina-loading-overlay", html)
        self.assertIn('data-loading-title="Changing your recipe"', html)
        self.assertIn("Making the change…", html)
        self.assertIn("js/recipe_loading.js", html)

    def test_generate_page_still_has_its_loading_box(self):
        html = self.client.get(reverse("generate_recipe")).content.decode()
        self.assertIn("data-culina-loading-overlay", html)
        self.assertIn("Making your recipe", html)
