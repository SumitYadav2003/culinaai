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

    # Links a modified recipe back to the original recipe.
    # Normal AI-generated recipes will keep this empty.
    # Modified recipes will use this field for comparison:
    # Original Recipe vs Modified Recipe.
    original_recipe = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modified_versions",
    )

    # Stores what type of modification the user requested.
    # Example: healthier, cheaper, quicker, vegetarian, spicier, simpler, custom.
    modification_type = models.CharField(
        max_length=50,
        choices=MODIFICATION_TYPE_CHOICES,
        blank=True,
    )

    # Stores the optional custom instruction entered by the user.
    # This helps explain why the modified recipe was created.
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

    # Community sharing fields.
    # By default, saved recipes remain private.
    # A recipe appears in the community only when the owner shares it.
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
        """
        Returns True when this recipe was created from another saved recipe.

        This is useful in templates because we can show the comparison section
        only for modified recipes.
        """
        return self.original_recipe_id is not None

    @property
    def average_rating(self):
        """
        Returns the average rating for this recipe.

        This will be useful for community recipe cards and the future
        evaluation dashboard.
        """

        average = self.ratings.aggregate(
            models.Avg("rating")
        )["rating__avg"]

        if average:
            return round(average, 1)

        return 0

    @property
    def feedback_count(self):
        """
        Returns the number of feedback comments for this recipe.

        This will help show community engagement on public recipe cards.
        """

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