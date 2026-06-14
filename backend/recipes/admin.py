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
    list_display = (
        "title",
        "user",
        "cuisine",
        "meal_type",
        "difficulty",
        "cooking_time_minutes",
        "is_ai_generated",
        "is_saved",
        "created_at",
    )
    list_filter = (
        "cuisine",
        "meal_type",
        "difficulty",
        "is_ai_generated",
        "is_saved",
        "created_at",
    )
    search_fields = (
        "title",
        "description",
        "ingredients_text",
        "instructions_text",
        "user__username",
    )
    filter_horizontal = ("diet_preferences", "ingredients")
    readonly_fields = ("created_at", "updated_at")


@admin.register(FavouriteRecipe)
class FavouriteRecipeAdmin(admin.ModelAdmin):
    list_display = ("user", "recipe", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "recipe__title")


@admin.register(RecipeRating)
class RecipeRatingAdmin(admin.ModelAdmin):
    list_display = ("user", "recipe", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("user__username", "recipe__title")


@admin.register(RecipeFeedback)
class RecipeFeedbackAdmin(admin.ModelAdmin):
    list_display = ("user", "recipe", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "recipe__title", "comment")