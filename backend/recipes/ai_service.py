from django.conf import settings
from openai import OpenAI


def build_recipe_prompt(preferences):
    """
    Builds a detailed AI prompt from the user's recipe preferences.
    """

    diet_preferences = preferences.get("diet_preferences") or []
    cooking_equipment = preferences.get("cooking_equipment") or []

    diet_text = ", ".join(diet_preferences) if diet_preferences else "No specific diet preference"
    equipment_text = ", ".join(cooking_equipment) if cooking_equipment else "No specific equipment selected"

    prompt = f"""
You are CulinaAI, a professional AI chef and meal personalisation assistant.

Generate a personalised recipe using the user's preferences below.

USER PREFERENCES:
- Available ingredients: {preferences.get("ingredients")}
- Cuisine: {preferences.get("cuisine")}
- Meal type: {preferences.get("meal_type")}
- Diet preferences: {diet_text}
- Allergies or ingredients to avoid: {preferences.get("allergies")}
- Cooking time limit: {preferences.get("cooking_time_minutes")} minutes
- Servings: {preferences.get("servings")}
- Difficulty: {preferences.get("difficulty")}
- Spice level: {preferences.get("spice_level")}
- Budget level: {preferences.get("budget_level")}
- Nutrition goal: {preferences.get("nutrition_goal")}
- Available cooking equipment: {equipment_text}
- Additional notes: {preferences.get("additional_notes")}

Return the recipe in this exact structure:

RECIPE TITLE:
A clear, attractive recipe title.

SHORT DESCRIPTION:
2-3 sentences describing the recipe.

MATCH SUMMARY:
Explain how the recipe matches the user's preferences.

INGREDIENTS:
Use bullet points with quantities.

INSTRUCTIONS:
Use numbered steps.

ALLERGY AND DIET NOTES:
Mention any allergy risks, diet conflicts, or safe substitutions.

CHEF TIPS:
Give 2-3 practical cooking tips.

STORAGE ADVICE:
Explain how to store leftovers.

SUBSTITUTIONS:
Suggest ingredient substitutions if the user is missing something.
"""

    return prompt.strip()


def generate_ai_recipe(preferences):
    """
    Sends the user's preferences to OpenAI and returns the generated recipe text.
    """

    if not settings.OPENAI_API_KEY:
        raise ValueError("OpenAI API key is missing. Please add OPENAI_API_KEY to your .env file.")

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    prompt = build_recipe_prompt(preferences)

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
        max_output_tokens=1200,
    )

    return {
        "prompt": prompt,
        "recipe_text": response.output_text,
    }













def build_recipe_modification_prompt(recipe, modification_type, custom_instruction=""):
    """
    Builds a structured OpenAI prompt for modifying an existing saved recipe.

    Why this function exists:
    - The original recipe already exists in the database.
    - The user chooses how they want the recipe changed.
    - We give OpenAI the original recipe and clear modification instructions.
    - OpenAI should return a complete modified recipe, not just small notes.

    Parameters:
    - recipe: The saved Recipe model instance.
    - modification_type: The selected modification option from RecipeModifyForm.
    - custom_instruction: Optional user-written instruction for extra control.
    """

    modification_labels = {
        "healthier": "Make the recipe healthier while keeping it tasty and practical.",
        "cheaper": "Make the recipe more budget-friendly using affordable ingredients.",
        "quicker": "Make the recipe quicker to cook while keeping the result realistic.",
        "vegetarian": "Convert the recipe into a vegetarian-friendly version.",
        "spicier": "Make the recipe spicier while keeping the flavours balanced.",
        "simpler": "Make the recipe simpler with fewer steps and easier ingredients.",
        "custom": "Follow the custom instruction provided by the user.",
    }

    selected_instruction = modification_labels.get(
        modification_type,
        "Improve the recipe based on the user's request.",
    )

    return f"""
You are CulinaAI, an AI recipe assistant.

Your task is to modify an existing saved recipe based on the user's request.

Modification request:
{selected_instruction}

Custom user instruction:
{custom_instruction if custom_instruction else "No custom instruction provided."}

Original recipe title:
{recipe.title}

Original ingredients:
{recipe.ingredients_text}

Original allergy notes:
{recipe.allergy_notes if recipe.allergy_notes else "No allergy notes provided."}

Original recipe instructions:
{recipe.instructions_text}

Return the modified recipe using this exact structure:

MODIFIED RECIPE TITLE:
A clear title for the modified recipe.

WHAT CHANGED:
Briefly explain what changed from the original recipe.

INGREDIENTS:
List the updated ingredients clearly.

INSTRUCTIONS:
Give step-by-step cooking instructions.

ALLERGY AND DIET NOTES:
Mention any important allergy, diet, or safety notes.

CHEF TIPS:
Give practical tips to improve the final result.

STORAGE ADVICE:
Explain how to store leftovers safely.
"""


def modify_ai_recipe(recipe, modification_type, custom_instruction=""):
    """
    Sends an existing saved recipe to OpenAI and returns a modified version.

    Important:
    - This function is ready for the real OpenAI call.
    - It should only be triggered when the user intentionally submits the modify form.
    - We do not run this function during normal system checks, so it does not spend API credit.
    """

    if not settings.OPENAI_API_KEY:
        raise ValueError("OpenAI API key is missing. Please check your .env file.")

    prompt = build_recipe_modification_prompt(
        recipe=recipe,
        modification_type=modification_type,
        custom_instruction=custom_instruction,
    )

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
        max_output_tokens=1200,
    )

    return {
        "prompt": prompt,
        "modified_recipe_text": response.output_text,
    }