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