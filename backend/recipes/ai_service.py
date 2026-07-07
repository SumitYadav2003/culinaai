from django.conf import settings
from openai import OpenAI


COMMON_AVOIDANCE_SYNONYMS = {
    "tomato": [
        "tomato",
        "tomatoes",
        "tomato sauce",
        "tomato puree",
        "tomato paste",
        "passata",
        "ketchup",
        "marinara",
    ],
    "peanut": [
        "peanut",
        "peanuts",
        "groundnut",
        "groundnuts",
        "peanut butter",
        "peanut oil",
        "satay",
    ],
    "nut": [
        "nuts",
        "almonds",
        "cashews",
        "walnuts",
        "hazelnuts",
        "pistachios",
        "pecans",
        "nut butter",
    ],
    "dairy": [
        "milk",
        "cheese",
        "butter",
        "cream",
        "yogurt",
        "yoghurt",
        "paneer",
        "ghee",
        "whey",
        "curd",
    ],
    "gluten": [
        "wheat",
        "flour",
        "bread",
        "pasta",
        "barley",
        "rye",
        "semolina",
        "breadcrumbs",
        "soy sauce",
    ],
    "egg": [
        "egg",
        "eggs",
        "omelette",
        "omelet",
        "mayonnaise",
        "mayo",
    ],
    "fish": [
        "fish",
        "salmon",
        "tuna",
        "cod",
        "mackerel",
        "anchovy",
    ],
    "shellfish": [
        "shellfish",
        "prawn",
        "prawns",
        "shrimp",
        "crab",
        "lobster",
        "mussels",
        "oyster",
    ],
    "soy": [
        "soy",
        "soya",
        "tofu",
        "tempeh",
        "soy sauce",
        "edamame",
    ],
}


def normalise_text(value):
    """
    Converts a value into clean lower-case text.
    """

    if value is None:
        return ""

    return str(value).strip().lower()


def split_user_items(value):
    """
    Splits comma-separated or list-based user inputs into clean values.
    """

    if not value:
        return []

    if isinstance(value, (list, tuple, set)):
        items = []

        for item in value:
            items.extend(split_user_items(item))

        return items

    text = str(value)
    text = text.replace("\n", ",")
    text = text.replace(";", ",")
    text = text.replace("|", ",")

    return [
        item.strip()
        for item in text.split(",")
        if item.strip()
        and item.strip().lower()
        not in ["none", "none provided", "n/a", "na"]
    ]


def build_avoidance_terms(allergy_text):
    """
    Builds a stricter avoid-list for the AI prompt.

    Example:
    If user enters tomato, the model is also told to avoid tomato sauce,
    tomato puree, tomato paste, passata, ketchup and marinara.
    """

    user_allergies = split_user_items(allergy_text)
    avoid_terms = set()

    for allergy in user_allergies:
        clean_allergy = normalise_text(allergy)
        avoid_terms.add(clean_allergy)

        if clean_allergy.endswith("s"):
            avoid_terms.add(clean_allergy[:-1])
        else:
            avoid_terms.add(f"{clean_allergy}s")

        for key, synonyms in COMMON_AVOIDANCE_SYNONYMS.items():
            if key in clean_allergy or clean_allergy in key:
                avoid_terms.update(synonyms)

    return sorted(term for term in avoid_terms if term)


def build_diet_rule_text(diet_preferences):
    """
    Converts diet preferences into clear instructions for the AI.
    """

    diet_text = ", ".join(diet_preferences) if diet_preferences else "No specific diet preference"
    clean_diets = [normalise_text(diet) for diet in diet_preferences]

    rules = []

    if any(
        diet in [
            "eggetarian",
            "eggitarian",
            "eggeterian",
            "egg vegetarian",
            "egg-vegetarian",
            "ovo vegetarian",
            "ovo-vegetarian",
        ]
        for diet in clean_diets
    ):
        rules.append(
            "Eggetarian rule: eggs are allowed, but meat, fish, seafood, chicken, beef, pork, lamb, bacon and ham are not allowed."
        )

    elif any("vegetarian" in diet for diet in clean_diets):
        rules.append(
            "Vegetarian rule: do not use meat, fish, seafood, chicken, beef, pork, lamb, bacon or ham."
        )

    if any("vegan" in diet for diet in clean_diets):
        rules.append(
            "Vegan rule: do not use meat, fish, seafood, dairy, eggs, honey, butter, cheese, milk, cream, paneer, ghee or yogurt."
        )

    if any("halal" in diet for diet in clean_diets):
        rules.append(
            "Halal rule: do not use pork, bacon, ham, alcohol, wine, beer or non-halal meat."
        )

    if any("gluten" in diet for diet in clean_diets):
        rules.append(
            "Gluten-free rule: do not use wheat, flour, bread, pasta, barley, rye, semolina, breadcrumbs or soy sauce unless clearly gluten-free."
        )

    if any("dairy" in diet for diet in clean_diets):
        rules.append(
            "Dairy-free rule: do not use milk, cheese, butter, cream, paneer, ghee, yogurt or whey."
        )

    if any("egg free" in diet or "egg-free" in diet for diet in clean_diets):
        rules.append(
            "Egg-free rule: do not use eggs, omelette, mayonnaise or mayo."
        )

    if not rules:
        rules.append("No additional diet restriction rule is required beyond the selected diet preference.")

    return diet_text, "\n".join(f"- {rule}" for rule in rules)


def build_equipment_rule_text(cooking_equipment):
    """
    Builds a clear equipment restriction for the AI.
    """

    if not cooking_equipment:
        return (
            "No specific equipment selected",
            "- The user did not select specific equipment. Use simple everyday cooking methods where possible.",
        )

    equipment_text = ", ".join(cooking_equipment)

    return (
        equipment_text,
        f"- Only use this available cooking equipment: {equipment_text}.\n"
        "- Do not ask the user to use an oven, microwave, blender, air fryer or pressure cooker unless it is listed above.",
    )


def build_recipe_prompt(preferences):
    """
    Builds a strict AI prompt from the user's recipe preferences.

    Important:
    This prompt is designed to reduce validation failure before the backend
    validation engine runs.
    """

    diet_preferences = preferences.get("diet_preferences") or []
    cooking_equipment = preferences.get("cooking_equipment") or []

    diet_text, diet_rule_text = build_diet_rule_text(diet_preferences)
    equipment_text, equipment_rule_text = build_equipment_rule_text(cooking_equipment)

    allergy_text = preferences.get("allergies") or "None provided"
    avoid_terms = build_avoidance_terms(allergy_text)
    avoid_text = ", ".join(avoid_terms) if avoid_terms else "No allergy ingredients provided"

    prompt = f"""
You are CulinaAI, a professional AI chef and meal personalisation assistant.

Your task is to generate a recipe that follows the user's constraints exactly.
This is not a casual recipe. It will be checked by a backend validation engine.

USER PREFERENCES:
- Available ingredients: {preferences.get("ingredients")}
- Cuisine: {preferences.get("cuisine")}
- Meal type: {preferences.get("meal_type")}
- Diet preferences: {diet_text}
- Allergies or ingredients to avoid: {allergy_text}
- Expanded avoid-list: {avoid_text}
- Cooking time limit: {preferences.get("cooking_time_minutes")} minutes
- Servings: {preferences.get("servings")}
- Difficulty: {preferences.get("difficulty")}
- Spice level: {preferences.get("spice_level")}
- Budget level: {preferences.get("budget_level")}
- Nutrition goal: {preferences.get("nutrition_goal")}
- Available cooking equipment: {equipment_text}
- Additional notes: {preferences.get("additional_notes")}


STRICT SAFETY AND VALIDATION RULES:
- The generated recipe must follow the user's constraints exactly.
- Treat allergies, avoided ingredients, diet restrictions and unavailable equipment as hard constraints.
- Do not include avoided ingredients anywhere in the final recipe output, including title, ingredients, steps, allergy notes, chef tips, storage advice or substitutions.
- In allergy notes, write only: "The user-provided restricted ingredients have been excluded from this recipe."
- Do not name the restricted ingredient in the final output, even to say it is excluded.

ALLERGY AND AVOIDANCE RULES:
- If the user says tomato allergy or avoid tomato, do not use tomato, tomatoes, tomato sauce, tomato puree, tomato paste, passata, ketchup, marinara or salsa.
- If the user says peanut allergy, do not use peanut, peanuts, groundnut, peanut butter, peanut oil, satay or nut-based sauces.
- If the user says nut allergy, do not use peanuts, almonds, cashews, walnuts, hazelnuts, pistachios, pecans, nut butter or nut toppings.
- If the user says dairy allergy or dairy-free, do not use milk, cheese, butter, cream, yogurt, yoghurt, paneer, ghee, whey or curd.
- If the user says gluten-free, do not use wheat, flour, bread, pasta, barley, rye, semolina, breadcrumbs or soy sauce unless clearly gluten-free.
- If the user says egg-free, do not use eggs, omelette, mayonnaise or mayo.
- If the user says soy allergy, do not use soy, soya, tofu, tempeh, edamame or soy sauce.
- If the user says sesame allergy, do not use sesame seeds, sesame oil or tahini.
- If the user says mustard allergy, do not use mustard, mustard seeds or mustard powder.
- If the user says fish allergy, do not use fish, tuna, salmon, cod, mackerel or anchovies.
- If the user says shellfish allergy, do not use prawns, shrimp, crab, lobster, mussels or oysters.
- If the user says alcohol-free, do not use wine, beer, rum, vodka, whisky, brandy or cooking alcohol.

DIET RULES:
- If the user says vegetarian, do not use meat, fish, seafood, chicken, beef, pork, lamb, bacon or ham.
- If the user says eggetarian, eggs are allowed, but meat, fish, seafood, chicken, beef, pork, lamb, bacon and ham are not allowed.
- If the user says vegan, do not use meat, fish, seafood, dairy, eggs, honey, butter, cheese, milk, cream, paneer, ghee or yogurt.
- If the user says halal, do not use pork, bacon, ham, alcohol, wine, beer or non-halal meat.
- If the user says dairy-free, gluten-free, nut-free, egg-free, soy-free or sesame-free, follow those restrictions strictly.
- If one user ingredient conflicts with allergy or diet rules, exclude only that unsafe ingredient and continue using the remaining safe ingredients.
- If a cuisine normally uses a restricted ingredient, create a safe alternative instead of using that ingredient.

INGREDIENT AND PERSONALISATION RULES:
- Use the user's available ingredients as much as possible.
- Do not add major new ingredients unless they are basic pantry items such as oil, salt, pepper, herbs, water or common spices.
- Quantities must be realistic for the selected number of servings.
- Do not include ingredients that are clearly unsuitable for the selected meal type.
- Match the selected cuisine style without violating safety or diet rules.
- Match the selected nutrition goal where possible.
- For high protein, include protein-focused safe ingredients from the user's list where possible.
- For low calorie, avoid excessive oil, cream, cheese, sugar and deep frying.
- For low carb, reduce rice, bread, pasta and potato where possible, unless they are the main user-provided ingredients.
- For comfort food, make the recipe warm, filling and satisfying without breaking restrictions.
- For balanced, include a reasonable mix of carbohydrate, protein and vegetables where possible.
- For low budget, avoid expensive or rare ingredients.
- For premium, you may improve flavour with higher-quality but realistic ingredients.

COOKING TIME AND DIFFICULTY RULES:
- Keep the cooking time within the user's requested time limit as closely as possible.
- If the requested time is short, choose quick cooking techniques.
- Match the selected difficulty level.
- For easy difficulty, keep the method simple, use fewer steps and avoid advanced cooking techniques.
- For medium difficulty, use moderate steps but avoid professional-level techniques.
- For hard difficulty, more advanced methods are allowed, but the recipe must still be practical.
- Do not use complex techniques such as sous-vide, fermentation, overnight marination, smoking, dehydrating or tempering unless the user selected hard difficulty.

EQUIPMENT RULES:
- Do not require unavailable equipment.
- If oven is not listed as available equipment, do not bake, roast in an oven or use a baking tray.
- If blender is not listed as available equipment, do not ask the user to blend, puree, grind, use a mixer, use a food processor, or make a smooth paste. Use chopping, stirring, mashing or pan-cooking methods instead.
- If microwave is not listed as available equipment, do not use a microwave.
- If air fryer is not listed as available equipment, do not use an air fryer.
- If pressure cooker is not listed as available equipment, do not use a pressure cooker or instant pot.
- If only stove is available, use pan, pot, skillet or saucepan methods only.
- If gas burner is selected, use normal pan, pot, tawa, kadai or saucepan cooking methods.
- If induction hob is selected, use induction-safe pan, pot or saucepan methods only.
- If portable camping stove is selected, keep the recipe simple, quick and one-pan where possible.
- If electric hot plate is selected, use simple pan or pot cooking methods and avoid high-flame techniques.
- If traditional clay stove or chulha is selected, use simple pot, pan or tawa cooking methods and avoid electric appliances.
- Do not assume the user has oven, microwave, blender, air fryer or pressure cooker unless selected.

OUTPUT QUALITY RULES:
- The recipe must include a clear title, short description, match summary, ingredients with quantities, cooking time, servings, difficulty, numbered steps, allergy/diet notes, chef tips, storage advice and substitutions.
- Steps must be clear, numbered and practical.
- Do not provide unsafe cooking advice.
- Do not claim professional medical, allergy or nutrition certainty.
- Do not say the recipe is medically guaranteed.
- Do not suggest allergy ingredients as substitutions.
- Substitutions must also follow the user's allergies, diet and equipment restrictions.
- Return only the recipe in the requested structure.

{diet_rule_text}
{equipment_rule_text}

{diet_rule_text}
{equipment_rule_text}
{diet_rule_text}
{equipment_rule_text}

OUTPUT FORMAT RULES:
Return only the recipe.
Do not add markdown tables.
Do not add explanations outside the recipe.
Use this exact structure and headings:

RECIPE TITLE:
A clear, attractive recipe title.

SHORT DESCRIPTION:
2-3 sentences describing the recipe.

MATCH SUMMARY:
Explain how the recipe matches the user's ingredients, cuisine, meal type, diet, allergy restrictions, time, difficulty and equipment.

INGREDIENTS WITH QUANTITIES:
Use bullet points with realistic quantities.
Include the user's safe ingredients wherever possible.
Do not include avoided ingredients.

COOKING TIME:
Write the total time in minutes.

SERVINGS:
Write the number of servings.

DIFFICULTY:
Write the selected difficulty level.

STEPS:
Use numbered steps.
Keep the steps practical and easy to follow.
Do not use equipment that the user did not select.

ALLERGY AND DIET NOTES:
Write only: "The user-provided restricted ingredients have been excluded from this recipe." Do not name the avoided ingredients.
Mention any safe substitutions.
Do not suggest using avoided ingredients.

CHEF TIPS:
Give 2-3 practical cooking tips.

STORAGE ADVICE:
Explain how to store leftovers.

SUBSTITUTIONS:
Suggest safe ingredient substitutions only.
Do not suggest or name any allergy or avoided ingredients.
"""

    return prompt.strip()


def generate_ai_recipe(preferences):
    """
    Sends the user's preferences to OpenAI and returns the generated recipe text.
    """

    if not settings.OPENAI_API_KEY:
        raise ValueError(
            "OpenAI API key is missing. Please add OPENAI_API_KEY to your .env file."
        )

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    prompt = build_recipe_prompt(preferences)

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
        max_output_tokens=1400,
        temperature=0.3,
    )

    return {
        "prompt": prompt,
        "recipe_text": response.output_text,
    }


def build_recipe_modification_prompt(recipe, modification_type, custom_instruction=""):
    """
    Builds a structured OpenAI prompt for modifying an existing saved recipe.
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

STRICT MODIFICATION RULES:
- Return a complete modified recipe, not only notes.
- Preserve the original recipe's allergy, diet and safety restrictions.
- Do not introduce any new allergy risks.
- Do not introduce ingredients that conflict with the original allergy notes.
- If the original recipe excluded an ingredient, keep it excluded.
- If the modification request conflicts with allergy, diet, safety or practicality, prioritise safety first.
- Keep the recipe practical for a normal home cook.
- Keep ingredients realistic and easy to understand.
- Use clear quantities for all main ingredients.
- Keep cooking instructions numbered and step-by-step.
- Keep the cooking time realistic.
- Do not claim professional medical, allergy or nutrition certainty.

HEALTHIER MODIFICATION:
- If making the recipe healthier, reduce excessive oil, sugar, cream, deep frying or heavy ingredients where possible.
- Prefer grilling, steaming, boiling, pan-cooking or light sautéing over deep frying.
- Add vegetables or protein only if they do not conflict with restrictions.

CHEAPER MODIFICATION:
- If making the recipe cheaper, replace expensive ingredients with affordable common alternatives.
- Avoid rare, imported or premium ingredients unless already present in the original recipe.
- Keep the recipe budget-friendly and realistic for students.

QUICKER MODIFICATION:
- If making the recipe quicker, reduce steps and cooking time realistically.
- Do not remove necessary cooking steps that make the food safe.
- Use simple one-pan or low-preparation methods where possible.

VEGETARIAN MODIFICATION:
- If making the recipe vegetarian, remove meat, fish, seafood, chicken, beef, pork, lamb, bacon and ham.
- Replace removed meat with safe vegetarian protein such as paneer, tofu, lentils, beans, chickpeas or eggs only if allowed.

VEGAN MODIFICATION:
- If making the recipe vegan, remove meat, fish, seafood, dairy, eggs, honey, butter, cheese, milk, cream, paneer, ghee and yogurt.
- Use plant-based alternatives only if they do not conflict with allergies.

SPICIER MODIFICATION:
- If making the recipe spicier, increase spice using safe spices, chilli, pepper, paprika or spice blends.
- Do not add restricted ingredients or unsafe sauces.
- Keep spice balanced and edible.

SIMPLER MODIFICATION:
- If making the recipe simpler, reduce the number of steps and avoid complex techniques.
- Avoid unnecessary equipment.
- Keep the final recipe easy to follow.

CUSTOM MODIFICATION:
- If custom instruction is provided, follow it only if it does not conflict with allergy, diet, safety, equipment or practicality.
- If the custom instruction is unsafe or conflicts with restrictions, create the closest safe alternative.
- Do not follow a custom instruction that adds restricted ingredients.

EQUIPMENT AND OUTPUT RULES:
- Do not use unavailable or unnecessary equipment.
- Do not suggest unsafe substitutions.
- Include modified title, what changed, ingredients with quantities, cooking time, servings, difficulty, instructions, allergy/diet notes, chef tips and storage advice.

Return the modified recipe using this exact structure:

MODIFIED RECIPE TITLE:
A clear title for the modified recipe.

WHAT CHANGED:
Briefly explain what changed from the original recipe.

INGREDIENTS WITH QUANTITIES:
List the updated ingredients clearly with quantities.

COOKING TIME:
Write the total time in minutes.

SERVINGS:
Write the number of servings if known, otherwise estimate it.

DIFFICULTY:
Write easy, medium or hard.

INSTRUCTIONS:
Give step-by-step cooking instructions.

ALLERGY AND DIET NOTES:
Mention any important allergy, diet, or safety notes.

CHEF TIPS:
Give practical tips to improve the final result.

STORAGE ADVICE:
Explain how to store leftovers safely.
""".strip()


def modify_ai_recipe(recipe, modification_type, custom_instruction=""):
    """
    Sends an existing saved recipe to OpenAI and returns a modified version.
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
        max_output_tokens=1400,
        temperature=0.3,
    )

    return {
        "prompt": prompt,
        "modified_recipe_text": response.output_text,
    }


























def build_recipe_image_prompt(recipe_title, preferences):
    """
    Builds a safe, professional image prompt for a generated recipe.

    The image should look like a realistic food photography image.
    We do not include allergy or medical claims in the image.
    """

    ingredients = preferences.get("ingredients") or "fresh ingredients"
    cuisine = preferences.get("cuisine") or "home-style cuisine"
    meal_type = preferences.get("meal_type") or "meal"
    diet_preferences = preferences.get("diet_preferences") or []
    diet_text = ", ".join(diet_preferences) if diet_preferences else "general"

    return f"""
Create a realistic, professional food photography image for this recipe.

Recipe title:
{recipe_title}

Recipe context:
- Main ingredients: {ingredients}
- Cuisine style: {cuisine}
- Meal type: {meal_type}
- Diet style: {diet_text}

Visual requirements:
- Show the finished cooked dish only.
- Make it look appetising, realistic and freshly prepared.
- Use natural lighting.
- Use a clean kitchen or dining table background.
- Use a modern plate or bowl presentation.
- No people.
- No text, labels, logos, watermarks or brand names.
- Do not show raw unsafe food.
- Do not show ingredients that are not suitable for the recipe.
- Make the image suitable for a professional recipe web application.
""".strip()


def generate_recipe_image_base64(recipe_title, preferences):
    """
    Generates a Base64 recipe image using OpenAI image generation.

    This function only returns Base64 image data.
    The Django view will save it into the Recipe.generated_image field.
    """

    if not settings.OPENAI_API_KEY:
        raise ValueError(
            "OpenAI API key is missing. Please add OPENAI_API_KEY to your .env file."
        )

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    image_prompt = build_recipe_image_prompt(
        recipe_title=recipe_title,
        preferences=preferences,
    )

    response = client.responses.create(
        model=getattr(settings, "OPENAI_IMAGE_MODEL", "gpt-5.5"),
        input=image_prompt,
        tools=[
            {
                "type": "image_generation",
                "size": "1024x1024",
            }
        ],
    )

    image_data = [
        output.result
        for output in response.output
        if output.type == "image_generation_call"
    ]

    if not image_data:
        return {
            "image_prompt": image_prompt,
            "image_base64": "",
        }

    return {
        "image_prompt": image_prompt,
        "image_base64": image_data[0],
    }