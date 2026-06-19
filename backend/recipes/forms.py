from django import forms

from .models import Cuisine, DietPreference, MealType, Recipe


class RecipeGenerationForm(forms.Form):
    SPICE_LEVEL_CHOICES = [
        ("mild", "Mild"),
        ("medium", "Medium"),
        ("spicy", "Spicy"),
        ("extra_spicy", "Extra Spicy"),
    ]

    BUDGET_CHOICES = [
        ("low", "Low Budget"),
        ("medium", "Moderate Budget"),
        ("premium", "Premium Ingredients"),
    ]

    NUTRITION_GOAL_CHOICES = [
        ("balanced", "Balanced"),
        ("high_protein", "High Protein"),
        ("low_calorie", "Low Calorie"),
        ("low_carb", "Low Carb"),
        ("comfort_food", "Comfort Food"),
    ]

    EQUIPMENT_CHOICES = [
        ("stove", "Stove"),
        ("oven", "Oven"),
        ("microwave", "Microwave"),
        ("air_fryer", "Air Fryer"),
        ("blender", "Blender"),
        ("pressure_cooker", "Pressure Cooker"),
    ]

    ingredients = forms.CharField(
        label="Available Ingredients",
        widget=forms.Textarea(
            attrs={
                "class": "form-control recipe-input",
                "rows": 4,
                "placeholder": "Example: chicken, rice, tomatoes, garlic, spinach",
            }
        ),
    )

    cuisine = forms.ModelChoiceField(
        queryset=Cuisine.objects.all(),
        required=False,
        empty_label="Any cuisine",
        widget=forms.Select(
            attrs={
                "class": "form-select recipe-input",
            }
        ),
    )

    meal_type = forms.ModelChoiceField(
        queryset=MealType.objects.all(),
        required=False,
        empty_label="Any meal type",
        widget=forms.Select(
            attrs={
                "class": "form-select recipe-input",
            }
        ),
    )

    diet_preferences = forms.ModelMultipleChoiceField(
        queryset=DietPreference.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple(
            attrs={
                "class": "recipe-checkbox",
            }
        ),
    )

    allergies = forms.CharField(
        required=False,
        label="Allergies or Ingredients to Avoid",
        widget=forms.Textarea(
            attrs={
                "class": "form-control recipe-input",
                "rows": 3,
                "placeholder": "Example: peanuts, shellfish, dairy, gluten",
            }
        ),
    )

    cooking_time_minutes = forms.IntegerField(
        min_value=5,
        max_value=240,
        initial=30,
        label="Cooking Time",
        widget=forms.NumberInput(
            attrs={
                "class": "form-control recipe-input",
                "placeholder": "30",
            }
        ),
    )

    servings = forms.IntegerField(
        min_value=1,
        max_value=12,
        initial=2,
        label="Number of Servings",
        widget=forms.NumberInput(
            attrs={
                "class": "form-control recipe-input",
                "placeholder": "2",
            }
        ),
    )

    difficulty = forms.ChoiceField(
        choices=Recipe.DIFFICULTY_CHOICES,
        initial="easy",
        widget=forms.Select(
            attrs={
                "class": "form-select recipe-input",
            }
        ),
    )

    spice_level = forms.ChoiceField(
        choices=SPICE_LEVEL_CHOICES,
        initial="medium",
        label="Spice Level",
        widget=forms.Select(
            attrs={
                "class": "form-select recipe-input",
            }
        ),
    )

    budget_level = forms.ChoiceField(
        choices=BUDGET_CHOICES,
        initial="medium",
        label="Budget Level",
        widget=forms.Select(
            attrs={
                "class": "form-select recipe-input",
            }
        ),
    )

    nutrition_goal = forms.ChoiceField(
        choices=NUTRITION_GOAL_CHOICES,
        initial="balanced",
        label="Nutrition Goal",
        widget=forms.Select(
            attrs={
                "class": "form-select recipe-input",
            }
        ),
    )

    cooking_equipment = forms.MultipleChoiceField(
        choices=EQUIPMENT_CHOICES,
        required=False,
        label="Available Cooking Equipment",
        widget=forms.CheckboxSelectMultiple(
            attrs={
                "class": "recipe-checkbox",
            }
        ),
    )

    additional_notes = forms.CharField(
        required=False,
        label="Additional Notes",
        widget=forms.Textarea(
            attrs={
                "class": "form-control recipe-input",
                "rows": 3,
                "placeholder": "Example: make it spicy, high protein, low budget, suitable for dinner",
            }
        ),
    )










#Feedback form
class RecipeFeedbackForm(forms.Form):
    rating = forms.ChoiceField(
        label="Recipe rating",
        choices=[
            ("5", "5 - Excellent"),
            ("4", "4 - Good"),
            ("3", "3 - Okay"),
            ("2", "2 - Needs improvement"),
            ("1", "1 - Poor"),
        ],
        widget=forms.Select(
            attrs={
                "class": "recipe-input",
            }
        ),
    )

    comment = forms.CharField(
        label="Feedback comment",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "recipe-input",
                "rows": 4,
                "placeholder": "What did you like or what could be improved?",
            }
        ),
    )









# Email Form
class RecipeEmailForm(forms.Form):
    recipient_email = forms.EmailField(
        label="Recipient email address",
        widget=forms.EmailInput(
            attrs={
                "class": "recipe-input",
                "placeholder": "Enter email address...",
            }
        ),
    )

    message = forms.CharField(
        label="Optional message",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "recipe-input",
                "rows": 3,
                "placeholder": "Add a short note before sending this recipe...",
            }
        ),
    )