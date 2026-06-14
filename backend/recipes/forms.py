from django import forms

from .models import Cuisine, DietPreference, MealType, Recipe


class RecipeGenerationForm(forms.Form):
    ingredients = forms.CharField(
        label="Available Ingredients",
        widget=forms.Textarea(attrs={
            "class": "form-control recipe-input",
            "rows": 4,
            "placeholder": "Example: chicken, rice, tomatoes, garlic, spinach",
        }),
    )

    cuisine = forms.ModelChoiceField(
        queryset=Cuisine.objects.all(),
        required=False,
        empty_label="Any cuisine",
        widget=forms.Select(attrs={
            "class": "form-select recipe-input",
        }),
    )

    meal_type = forms.ModelChoiceField(
        queryset=MealType.objects.all(),
        required=False,
        empty_label="Any meal type",
        widget=forms.Select(attrs={
            "class": "form-select recipe-input",
        }),
    )

    diet_preferences = forms.ModelMultipleChoiceField(
        queryset=DietPreference.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={
            "class": "recipe-checkbox",
        }),
    )

    allergies = forms.CharField(
        required=False,
        label="Allergies or Ingredients to Avoid",
        widget=forms.Textarea(attrs={
            "class": "form-control recipe-input",
            "rows": 3,
            "placeholder": "Example: peanuts, shellfish, dairy, gluten",
        }),
    )

    cooking_time_minutes = forms.IntegerField(
        min_value=5,
        max_value=240,
        initial=30,
        label="Cooking Time",
        widget=forms.NumberInput(attrs={
            "class": "form-control recipe-input",
            "placeholder": "30",
        }),
    )

    difficulty = forms.ChoiceField(
        choices=Recipe.DIFFICULTY_CHOICES,
        initial="easy",
        widget=forms.Select(attrs={
            "class": "form-select recipe-input",
        }),
    )

    additional_notes = forms.CharField(
        required=False,
        label="Additional Notes",
        widget=forms.Textarea(attrs={
            "class": "form-control recipe-input",
            "rows": 3,
            "placeholder": "Example: make it spicy, high protein, low budget, suitable for dinner",
        }),
    )