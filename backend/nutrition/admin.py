from django.contrib import admin

from .models import CofidFood, IngredientAlias


@admin.register(CofidFood)
class CofidFoodAdmin(admin.ModelAdmin):
    list_display = ("food_code", "name", "source", "energy_kcal", "protein_g", "fat_g", "sugars_g", "salt_g")
    search_fields = ("food_code", "name")
    list_filter = ("source", "food_group")


@admin.register(IngredientAlias)
class IngredientAliasAdmin(admin.ModelAdmin):
    list_display = ("alias", "food", "notes")
    search_fields = ("alias", "food__name")
    autocomplete_fields = ("food",)
