from django.contrib import admin

from .models import CarbonCategory, CofidFood, IngredientAlias


@admin.register(CofidFood)
class CofidFoodAdmin(admin.ModelAdmin):
    list_display = ("food_code", "name", "source", "energy_kcal", "protein_g", "fat_g", "sugars_g", "salt_g", "carbon_category")
    search_fields = ("food_code", "name")
    list_filter = ("source", "food_group", "carbon_category")


@admin.register(IngredientAlias)
class IngredientAliasAdmin(admin.ModelAdmin):
    list_display = ("alias", "food", "notes")
    search_fields = ("alias", "food__name")
    autocomplete_fields = ("food",)


@admin.register(CarbonCategory)
class CarbonCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "kg_co2e_per_kg", "land_use_change", "farm", "animal_feed", "processing", "transport", "packaging")
    search_fields = ("name",)
