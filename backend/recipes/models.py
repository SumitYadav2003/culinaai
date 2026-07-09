from django.conf import settings
from django.db import models


class Cuisine(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class DietPreference(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class MealType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Ingredient(models.Model):
    name = models.CharField(max_length=120, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Recipe(models.Model):
    DIFFICULTY_CHOICES = [
        ("easy", "Easy"),
        ("medium", "Medium"),
        ("hard", "Hard"),
    ]

    MODIFICATION_TYPE_CHOICES = [
        ("healthier", "Healthier"),
        ("cheaper", "Cheaper"),
        ("quicker", "Quicker"),
        ("vegetarian", "Vegetarian"),
        ("spicier", "Spicier"),
        ("simpler", "Simpler"),
        ("custom", "Custom"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recipes",
    )

    original_recipe = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modified_versions",
    )

    modification_type = models.CharField(
        max_length=50,
        choices=MODIFICATION_TYPE_CHOICES,
        blank=True,
    )

    modification_instruction = models.TextField(blank=True)

    title = models.CharField(max_length=200)
    personal_notes = models.TextField(blank=True)
    description = models.TextField(blank=True)

    generated_image = models.ImageField(
        upload_to="recipe_images/",
        null=True,
        blank=True,
        help_text="AI-generated image for this recipe.",
    )

    cuisine = models.ForeignKey(
        Cuisine,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recipes",
    )

    meal_type = models.ForeignKey(
        MealType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recipes",
    )

    diet_preferences = models.ManyToManyField(
        DietPreference,
        blank=True,
        related_name="recipes",
    )

    ingredients = models.ManyToManyField(
        Ingredient,
        blank=True,
        related_name="recipes",
    )

    ingredients_text = models.TextField(help_text="Ingredients used for the recipe.")
    instructions_text = models.TextField(help_text="Step-by-step cooking instructions.")

    cooking_time_minutes = models.PositiveIntegerField(default=30)

    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        default="easy",
    )

    allergy_notes = models.TextField(blank=True)
    ai_prompt = models.TextField(blank=True)
    ai_response = models.TextField(blank=True)

    quality_score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Final CulinaAI validation score out of 100.",
    )

    validation_status = models.CharField(
        max_length=100,
        blank=True,
        help_text="Final validation status such as Verified or Excellent / Verified.",
    )

    validation_risk_level = models.CharField(
        max_length=50,
        blank=True,
        help_text="Risk level identified by the validation engine.",
    )

    validation_badge = models.CharField(
        max_length=50,
        blank=True,
        help_text="Short validation badge shown in the UI.",
    )

    validation_attempts = models.PositiveSmallIntegerField(
        default=0,
        help_text="Number of generation/correction attempts used.",
    )

    validation_report = models.JSONField(
        default=dict,
        blank=True,
        help_text="Full CulinaAI validation report stored as JSON.",
    )

    validation_attempt_history = models.JSONField(
        default=list,
        blank=True,
        help_text="History of AI generation, correction and fallback attempts.",
    )

    is_ai_generated = models.BooleanField(default=True)
    is_saved = models.BooleanField(default=True)

    is_public = models.BooleanField(
        default=False,
        help_text="Controls whether this recipe is visible in the community section.",
    )

    public_shared_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Stores when the recipe was shared with the community.",
    )

    community_views = models.PositiveIntegerField(
        default=0,
        help_text="Counts how many times this public recipe has been viewed.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_modified_version(self):
        return self.original_recipe_id is not None

    @property
    def average_rating(self):
        average = self.ratings.aggregate(
            models.Avg("rating")
        )["rating__avg"]

        if average:
            return round(average, 1)

        return 0

    @property
    def feedback_count(self):
        return self.feedback.count()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class FavouriteRecipe(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favourite_recipes",
    )

    recipe = models.ForeignKey(
        Recipe,
        on_delete=models.CASCADE,
        related_name="favourited_by",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "recipe")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} - {self.recipe.title}"



class RecipeRating(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recipe_ratings",
    )

    recipe = models.ForeignKey(
        Recipe,
        on_delete=models.CASCADE,
        related_name="ratings",
    )

    rating = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "recipe")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.recipe.title} - {self.rating}/5"


class RecipeFeedback(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recipe_feedback",
    )

    recipe = models.ForeignKey(
        Recipe,
        on_delete=models.CASCADE,
        related_name="feedback",
    )

    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Feedback from {self.user.username} on {self.recipe.title}"


class RecipeHistory(models.Model):
    """
    Stores every AI-generated recipe automatically.

    This is different from saved recipes:
    - History is created automatically after generation.
    - Saved recipes are created only when the user clicks Save.
    - History will later support analytics and ML recommendations.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recipe_history",
    )

    saved_recipe = models.ForeignKey(
        Recipe,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="history_entries",
        help_text="Links this history item to a saved recipe if the user saves it later.",
    )

    title = models.CharField(max_length=200)
    recipe_text = models.TextField()
    recipe_prompt = models.TextField(blank=True)

    ingredients_text = models.TextField(blank=True)
    cuisine_name = models.CharField(max_length=120, blank=True)
    meal_type_name = models.CharField(max_length=120, blank=True)

    dietary_preferences = models.JSONField(
        default=list,
        blank=True,
        help_text="Diet preferences selected when the recipe was generated.",
    )

    allergies = models.TextField(blank=True)
    cooking_time_minutes = models.PositiveIntegerField(default=30)

    servings = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Number of people/servings requested by the user.",
    )

    difficulty = models.CharField(
        max_length=20,
        choices=Recipe.DIFFICULTY_CHOICES,
        default="easy",
    )

    spice_level = models.CharField(max_length=100, blank=True)
    budget_level = models.CharField(max_length=100, blank=True)
    nutrition_goal = models.CharField(max_length=100, blank=True)

    cooking_equipment = models.JSONField(default=list, blank=True)
    utensils = models.JSONField(default=list, blank=True)

    additional_notes = models.TextField(blank=True)

    generated_image = models.ImageField(
        upload_to="recipe_history_images/",
        null=True,
        blank=True,
        help_text="AI-generated image connected to this history item.",
    )

    generated_image_prompt = models.TextField(blank=True)

    quality_score = models.PositiveSmallIntegerField(null=True, blank=True)
    validation_status = models.CharField(max_length=100, blank=True)
    validation_risk_level = models.CharField(max_length=50, blank=True)
    validation_badge = models.CharField(max_length=50, blank=True)
    validation_attempts = models.PositiveSmallIntegerField(default=0)

    validation_report = models.JSONField(default=dict, blank=True)
    validation_attempt_history = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Recipe History"
        verbose_name_plural = "Recipe History"

    def __str__(self):
        return f"{self.user.username} - {self.title}"

    @property
    def is_saved_to_library(self):
        return self.saved_recipe_id is not None
