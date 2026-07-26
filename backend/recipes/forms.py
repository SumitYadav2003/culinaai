from django import forms

from .models import (
    Cuisine,
    DietPreference,
    MealType,
    Recipe,
    PantryItem,
    FridgeScan,
)


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
        ("stove", "Stove / Hob"),
        ("gas_burner", "Gas Burner"),
        ("induction_hob", "Induction Hob"),
        ("portable_camping_stove", "Portable Camping Stove"),
        ("electric_hot_plate", "Electric Hot Plate"),
        ("traditional_chulha", "Traditional Clay Stove / Chulha"),
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


class RecipeModifyForm(forms.Form):
    """
    Form used on the saved recipe detail page to request an AI-powered
    modification of an existing saved recipe.
    """

    modification_type = forms.ChoiceField(
        label="Modification type",
        choices=[
            ("healthier", "Make it healthier"),
            ("cheaper", "Make it cheaper"),
            ("quicker", "Make it quicker"),
            ("vegetarian", "Make it vegetarian"),
            ("spicier", "Make it spicier"),
            ("simpler", "Make it simpler"),
            ("custom", "Custom instruction"),
        ],
        widget=forms.Select(
            attrs={
                "class": "recipe-input",
            }
        ),
    )

    custom_instruction = forms.CharField(
        label="Custom instruction",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "recipe-input",
                "rows": 3,
                "placeholder": "Example: Make this recipe high-protein but keep it under 20 minutes...",
            }
        ),
    )


class SavedRecipeEditForm(forms.ModelForm):
    """
    Form used to edit only user-controlled saved recipe fields.

    Important:
    - Users can rename their saved recipe.
    - Users can add personal cooking notes.
    - AI prompt, AI response, ingredients and instructions remain protected.
    """

    class Meta:
        model = Recipe
        fields = ["title", "personal_notes"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control edit-recipe-input",
                    "placeholder": "Give this saved recipe a personal title",
                    "maxlength": 255,
                }
            ),
            "personal_notes": forms.Textarea(
                attrs={
                    "class": "form-control edit-recipe-input",
                    "rows": 6,
                    "placeholder": "Add your own cooking notes, adjustments, serving ideas, or reminders...",
                }
            ),
        }
        labels = {
            "title": "Recipe title",
            "personal_notes": "Personal notes",
        }

    def clean_title(self):
        title = self.cleaned_data.get("title", "").strip()

        if not title:
            raise forms.ValidationError("Recipe title cannot be empty.")

        return title


class FridgeScanUploadForm(forms.ModelForm):
    """
    Form used for uploading a refrigerator image.

    The uploaded image will later be analysed by the AI refrigerator scanner.
    """

    class Meta:
        model = FridgeScan
        fields = ["image"]
        widgets = {
            "image": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                    "accept": "image/jpeg,image/png,image/webp",
                }
            ),
        }
        labels = {
            "image": "Upload refrigerator image",
        }
        help_texts = {
            "image": "Upload a clear fridge photo in JPG, PNG or WEBP format.",
        }

    def clean_image(self):
        image = self.cleaned_data.get("image")

        if not image:
            raise forms.ValidationError("Please upload a refrigerator image.")

        max_size_mb = 5
        max_size_bytes = max_size_mb * 1024 * 1024

        if image.size > max_size_bytes:
            raise forms.ValidationError(
                f"Image size must be less than {max_size_mb} MB."
            )

        allowed_content_types = [
            "image/jpeg",
            "image/png",
            "image/webp",
        ]

        content_type = getattr(image, "content_type", "")

        if content_type and content_type not in allowed_content_types:
            raise forms.ValidationError(
                "Only JPG, PNG or WEBP refrigerator images are allowed."
            )

        return image


class FridgeScanConfirmForm(forms.Form):
    """
    Form used after AI detection.

    The AI may detect imperfect items, so users must confirm or edit the list
    before the ingredients are added to the pantry or used for recipe generation.
    """

    confirmed_items_text = forms.CharField(
        label="Confirm detected ingredients",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 8,
                "placeholder": "Example:\nMilk\nTomatoes\nCheese\nSpinach",
            }
        ),
        help_text="Keep one ingredient per line. Remove anything incorrect and add anything missing.",
    )

    def __init__(self, *args, detected_items=None, **kwargs):
        super().__init__(*args, **kwargs)

        if detected_items and not self.is_bound:
            self.fields["confirmed_items_text"].initial = "\n".join(detected_items)

    def clean_confirmed_items_text(self):
        confirmed_items_text = self.cleaned_data.get("confirmed_items_text", "")

        raw_items = confirmed_items_text.replace(",", "\n").splitlines()

        cleaned_items = []
        seen_items = set()

        for item in raw_items:
            cleaned_item = item.strip()

            if not cleaned_item:
                continue

            normalised_item = cleaned_item.lower()

            if normalised_item in seen_items:
                continue

            seen_items.add(normalised_item)
            cleaned_items.append(cleaned_item)

        if not cleaned_items:
            raise forms.ValidationError(
                "Please confirm at least one valid ingredient."
            )

        if len(cleaned_items) > 40:
            raise forms.ValidationError(
                "Please keep the confirmed ingredient list below 40 items."
            )

        return "\n".join(cleaned_items)

    def get_confirmed_items_list(self):
        confirmed_items_text = self.cleaned_data.get("confirmed_items_text", "")

        return [
            item.strip()
            for item in confirmed_items_text.splitlines()
            if item.strip()
        ]


class PantryItemForm(forms.ModelForm):
    class Meta:
        model = PantryItem
        fields = [
            "ingredient_name",
            "quantity",
            "unit",
            "category",
            "expiry_date",
            "notes",
            "is_available",
        ]

        widgets = {
            "ingredient_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: rice, paneer, milk, tomato",
                }
            ),
            "quantity": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Optional",
                    "step": "0.01",
                    "min": "0",
                }
            ),
            "unit": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "category": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "expiry_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Optional notes, for example brand, storage location, or freshness",
                }
            ),
            "is_available": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                }
            ),
        }

        labels = {
            "ingredient_name": "Ingredient name",
            "quantity": "Quantity",
            "unit": "Unit",
            "category": "Category",
            "expiry_date": "Expiry date",
            "notes": "Notes",
            "is_available": "Currently available",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["ingredient_name"].required = True
        self.fields["quantity"].required = False
        self.fields["unit"].required = False
        self.fields["category"].required = False
        self.fields["expiry_date"].required = False
        self.fields["notes"].required = False
        self.fields["is_available"].required = False

        self.fields["quantity"].widget.attrs["placeholder"] = "Optional"
        self.fields["notes"].widget.attrs["placeholder"] = (
            "Optional notes, for example brand, storage location, or freshness"
        )

    def clean_ingredient_name(self):
        ingredient_name = self.cleaned_data.get("ingredient_name", "").strip()

        if not ingredient_name:
            raise forms.ValidationError("Ingredient name is required.")

        return ingredient_name

    def clean_quantity(self):
        quantity = self.cleaned_data.get("quantity")

        if quantity in ["", None]:
            return None

        return quantity

    def clean_unit(self):
        unit = self.cleaned_data.get("unit")

        if not unit:
            return "other"

        return unit

    def clean_category(self):
        category = self.cleaned_data.get("category")

        if not category:
            return "other"

        return category