from django.conf import settings
from django.db import models
from django.utils import timezone


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


class PantryItem(models.Model):
    """
    Stores ingredients that a user currently has in their pantry.

    This supports the Smart Pantry feature:
    - Track available ingredients
    - Track quantity and unit
    - Track expiry dates
    - Warn users about expired or soon-expiring ingredients
    - Later suggest recipes based on pantry items
    """

    CATEGORY_CHOICES = [
        ("vegetable", "Vegetable"),
        ("fruit", "Fruit"),
        ("dairy", "Dairy"),
        ("grain", "Grain / Rice / Pasta"),
        ("protein", "Protein"),
        ("spice", "Spice / Seasoning"),
        ("sauce", "Sauce / Condiment"),
        ("frozen", "Frozen"),
        ("other", "Other"),
    ]

    UNIT_CHOICES = [
        ("g", "grams"),
        ("kg", "kilograms"),
        ("ml", "millilitres"),
        ("l", "litres"),
        ("pcs", "pieces"),
        ("tbsp", "tablespoons"),
        ("tsp", "teaspoons"),
        ("pack", "pack"),
        ("other", "other"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pantry_items",
    )

    ingredient_name = models.CharField(
        max_length=120,
        help_text="Name of the pantry ingredient.",
    )

    quantity = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Quantity available, for example 1.5 or 500.",
    )

    unit = models.CharField(
        max_length=20,
        choices=UNIT_CHOICES,
        default="pcs",
    )

    category = models.CharField(
        max_length=30,
        choices=CATEGORY_CHOICES,
        default="other",
    )

    expiry_date = models.DateField(
        null=True,
        blank=True,
        help_text="Optional expiry date for this ingredient.",
    )

    is_available = models.BooleanField(
        default=True,
        help_text="Marks whether the item is still available in the pantry.",
    )

    notes = models.TextField(
        blank=True,
        help_text="Optional notes, for example brand, storage location or freshness.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def days_until_expiry(self):
        if not self.expiry_date:
            return None

        today = timezone.localdate()
        return (self.expiry_date - today).days

    @property
    def expiry_status(self):
        days_left = self.days_until_expiry

        if days_left is None:
            return "No expiry date"

        if days_left < 0:
            return "Expired"

        if days_left == 0:
            return "Expires today"

        if days_left <= 3:
            return "Expiring soon"

        return "Fresh"

    class Meta:
        ordering = ["expiry_date", "ingredient_name"]
        indexes = [
            models.Index(fields=["user", "ingredient_name"]),
            models.Index(fields=["user", "expiry_date"]),
        ]

    def __str__(self):
        return f"{self.ingredient_name} ({self.user.username})"


class FridgeScan(models.Model):
    """
    Stores one AI-assisted refrigerator scan.

    Purpose:
    - User uploads a refrigerator image.
    - AI detects possible ingredients from the image.
    - User reviews/edits the detected ingredients.
    - Confirmed ingredients can be added to the pantry or used for recipe generation.

    This model supports the AI Refrigerator Scanner feature and connects it
    safely with the Smart Pantry workflow.
    """

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="fridge_scans",
    )

    image = models.ImageField(
        upload_to="fridge_scans/",
        help_text="Refrigerator image uploaded by the user.",
    )

    detected_items = models.JSONField(
        default=list,
        blank=True,
        help_text="Raw list of ingredients detected by the AI scanner.",
    )

    confirmed_items = models.JSONField(
        default=list,
        blank=True,
        help_text="Final ingredient list confirmed or edited by the user.",
    )

    raw_ai_response = models.TextField(
        blank=True,
        help_text="Raw AI response from the refrigerator image scan.",
    )

    scan_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        help_text="Current status of the refrigerator scan.",
    )

    error_message = models.TextField(
        blank=True,
        help_text="Stores scanning or AI error details if the scan fails.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def detected_count(self):
        if isinstance(self.detected_items, list):
            return len(self.detected_items)

        return 0

    @property
    def confirmed_count(self):
        if isinstance(self.confirmed_items, list):
            return len(self.confirmed_items)

        return 0

    @property
    def has_confirmed_items(self):
        return self.confirmed_count > 0

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "scan_status"]),
            models.Index(fields=["created_at"]),
        ]
        verbose_name = "Fridge Scan"
        verbose_name_plural = "Fridge Scans"

    def __str__(self):
        return f"{self.user.username} - Fridge Scan #{self.id}"


class CookingChatSession(models.Model):
    """
    Stores one AI cooking assistant chat session for a saved recipe.

    Purpose:
    - Keeps chat history connected to a user and a recipe.
    - Supports recipe-specific after-use cooking help.
    - Example use cases:
      ingredient substitution, cooking mistakes, step explanation,
      pantry-aware suggestions, and dietary adjustments.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cooking_chat_sessions",
    )

    recipe = models.ForeignKey(
        "Recipe",
        on_delete=models.CASCADE,
        related_name="cooking_chat_sessions",
    )

    title = models.CharField(
        max_length=180,
        default="AI Cooking Assistant",
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-updated_at", "-created_at"]
        indexes = [
            models.Index(fields=["user", "recipe"]),
            models.Index(fields=["updated_at"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.recipe.title}"


class CookingChatMessage(models.Model):
    """
    Stores individual messages inside a cooking assistant chat session.

    Messages can be from:
    - user
    - assistant
    - system

    This makes the AI assistant advanced because previous messages
    can be shown again and reused as context.
    """

    SENDER_USER = "user"
    SENDER_ASSISTANT = "assistant"
    SENDER_SYSTEM = "system"

    SENDER_CHOICES = [
        (SENDER_USER, "User"),
        (SENDER_ASSISTANT, "Assistant"),
        (SENDER_SYSTEM, "System"),
    ]

    session = models.ForeignKey(
        CookingChatSession,
        on_delete=models.CASCADE,
        related_name="messages",
    )

    sender = models.CharField(
        max_length=20,
        choices=SENDER_CHOICES,
    )

    message = models.TextField()

    quick_prompt_label = models.CharField(
        max_length=120,
        blank=True,
    )

    ai_model = models.CharField(
        max_length=80,
        blank=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["session", "created_at"]),
            models.Index(fields=["sender"]),
        ]

    def __str__(self):
        return f"{self.sender}: {self.message[:60]}"