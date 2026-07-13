from django.contrib import admin

from .models import (
    Cuisine,
    DietPreference,
    FavouriteRecipe,
    Ingredient,
    MealType,
    Recipe,
    RecipeFeedback,
    RecipeRating,
    PantryItem,
    CookingChatSession,
    CookingChatMessage,
)


@admin.register(Cuisine)
class CuisineAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)


@admin.register(DietPreference)
class DietPreferenceAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)


@admin.register(MealType)
class MealTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    """
    Admin configuration for CulinaAI recipes.

    The list page is intentionally kept clean and readable.
    Detailed AI prompt data, modification tracking, timestamps, and recipe text
    are available inside the individual recipe edit page.
    """

    list_display = (
        "title",
        "user",
        "recipe_type",
        "modification_summary",
        "source_recipe",
        "cuisine",
        "meal_type",
        "is_saved",
        "created_at",
    )

    list_display_links = ("title",)

    list_filter = (
        "cuisine",
        "meal_type",
        "difficulty",
        "modification_type",
        "is_ai_generated",
        "is_saved",
        "created_at",
    )

    search_fields = (
        "title",
        "description",
        "ingredients_text",
        "instructions_text",
        "modification_instruction",
        "user__username",
        "original_recipe__title",
    )

    filter_horizontal = ("diet_preferences", "ingredients")

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    date_hierarchy = "created_at"

    list_select_related = (
        "user",
        "cuisine",
        "meal_type",
        "original_recipe",
    )

    fieldsets = (
        (
            "Recipe Owner",
            {
                "fields": (
                    "user",
                )
            },
        ),
        (
            "Recipe Details",
            {
                "fields": (
                    "title",
                    "description",
                    "cuisine",
                    "meal_type",
                    "diet_preferences",
                    "ingredients",
                    "ingredients_text",
                    "instructions_text",
                    "cooking_time_minutes",
                    "difficulty",
                    "allergy_notes",
                )
            },
        ),
        (
            "AI Generation Data",
            {
                "fields": (
                    "is_ai_generated",
                    "ai_prompt",
                    "ai_response",
                )
            },
        ),
        (
            "Recipe Modification Tracking",
            {
                "description": (
                    "These fields are used when a saved recipe has been modified "
                    "with AI. They allow the system to compare the original recipe "
                    "against the modified version."
                ),
                "fields": (
                    "original_recipe",
                    "modification_type",
                    "modification_instruction",
                ),
            },
        ),
        (
            "Save Status and Timestamps",
            {
                "fields": (
                    "is_saved",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def recipe_type(self, obj):
        """
        Shows whether a recipe is a normal saved recipe or an AI-modified version.
        This keeps the admin list simpler than showing many separate columns.
        """
        if obj.is_modified_version:
            return "Modified"

        return "Original"

    recipe_type.short_description = "Type"

    def modification_summary(self, obj):
        """
        Shows the selected modification type in a clean admin-friendly format.
        """
        if obj.modification_type:
            return obj.get_modification_type_display()

        return "—"

    modification_summary.short_description = "Modification"

    def source_recipe(self, obj):
        """
        Shows the original recipe title for modified recipes.
        Normal recipes show a dash because they have no source recipe.
        """
        if obj.original_recipe:
            return obj.original_recipe.title

        return "—"

    source_recipe.short_description = "Source recipe"


@admin.register(FavouriteRecipe)
class FavouriteRecipeAdmin(admin.ModelAdmin):
    list_display = ("user", "recipe", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "recipe__title")
    date_hierarchy = "created_at"
    list_select_related = ("user", "recipe")


@admin.register(RecipeRating)
class RecipeRatingAdmin(admin.ModelAdmin):
    list_display = ("user", "recipe", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("user__username", "recipe__title")
    date_hierarchy = "created_at"
    list_select_related = ("user", "recipe")


@admin.register(RecipeFeedback)
class RecipeFeedbackAdmin(admin.ModelAdmin):
    list_display = ("user", "recipe", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "recipe__title", "comment")
    date_hierarchy = "created_at"
    list_select_related = ("user", "recipe")









@admin.register(PantryItem)
class PantryItemAdmin(admin.ModelAdmin):
    list_display = (
        "ingredient_name",
        "user",
        "quantity",
        "unit",
        "category",
        "expiry_date",
        "expiry_status",
        "is_available",
        "updated_at",
    )

    list_filter = (
        "category",
        "unit",
        "is_available",
        "expiry_date",
    )

    search_fields = (
        "ingredient_name",
        "user__username",
        "user__email",
        "notes",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "days_until_expiry",
        "expiry_status",
    )

    ordering = (
        "expiry_date",
        "ingredient_name",
    )










class CookingChatMessageInline(admin.TabularInline):
    model = CookingChatMessage
    extra = 0
    readonly_fields = ("sender", "message", "quick_prompt_label", "ai_model", "created_at")
    can_delete = False


@admin.register(CookingChatSession)
class CookingChatSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "recipe",
        "title",
        "is_active",
        "created_at",
        "updated_at",
    )
    list_filter = ("is_active", "created_at", "updated_at")
    search_fields = ("user__username", "recipe__title", "title")
    inlines = [CookingChatMessageInline]


@admin.register(CookingChatMessage)
class CookingChatMessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "session",
        "sender",
        "quick_prompt_label",
        "created_at",
    )
    list_filter = ("sender", "created_at")
    search_fields = ("message", "session__recipe__title", "session__user__username")
    readonly_fields = ("created_at",)