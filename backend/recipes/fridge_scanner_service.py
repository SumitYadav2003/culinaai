import base64
import json
import mimetypes
import os
import re
from pathlib import Path

from django.conf import settings
from openai import OpenAI

from .models import FridgeScan


# Image validation stays strict.
# Ingredient detection is flexible enough to include visible cooking items,
# sauces, condiments, packaged cooking items, leafy greens, carrots, and staples.
MIN_IMAGE_CONFIDENCE = 55
MIN_INGREDIENT_CONFIDENCE = 25
MAX_DETECTED_INGREDIENTS = 35


VALID_IMAGE_CONTEXTS = {
    "refrigerator",
    "fridge",
    "pantry",
    "kitchen_counter",
    "grocery_items",
    "food_storage",
    "food_items",
}


INVALID_IMAGE_CONTEXTS = {
    "person",
    "face",
    "document",
    "screenshot",
    "laptop",
    "phone",
    "room",
    "vehicle",
    "outdoor_scene",
    "animal",
    "non_food",
    "unclear",
}


NON_FOOD_WORDS = {
    "bottle",
    "container",
    "box",
    "packet",
    "jar",
    "bag",
    "plastic",
    "drawer",
    "shelf",
    "fridge",
    "refrigerator",
    "carton",
    "can",
    "label",
    "lid",
    "door",
    "tray",
    "wrapper",
    "packaging",
    "brand",
    "logo",
    "barcode",
    "sticker",
    "hand",
    "person",
    "plate",
    "bowl",
    "cup",
    "glass",
    "fork",
    "spoon",
    "knife",
}


PACKAGING_WORDS_TO_REMOVE = {
    "bottle",
    "container",
    "box",
    "packet",
    "jar",
    "bag",
    "plastic",
    "carton",
    "can",
    "label",
    "lid",
    "tray",
    "wrapper",
    "packaging",
    "pack",
    "tin",
    "tub",
    "cup",
    "pot",
    "pouch",
    "bottled",
}


# These are food/drink items, but they are not useful cooking ingredients
# for this recipe-generation context.
NON_COOKING_BEVERAGES = {
    "coke",
    "coca cola",
    "cola",
    "diet coke",
    "pepsi",
    "fanta",
    "sprite",
    "7up",
    "seven up",
    "soft drink",
    "soft drinks",
    "soda",
    "carbonated drink",
    "carbonated drinks",
    "energy drink",
    "energy drinks",
    "sports drink",
    "sports drinks",
    "bottled water",
    "water",
    "mineral water",
    "sparkling water",
    "tonic water",
    "lemonade drink",
}


INGREDIENT_NAME_NORMALISATION = {
    "salad leaves": "Leafy Greens",
    "salad green": "Leafy Greens",
    "salad greens": "Leafy Greens",
    "green leaves": "Leafy Greens",
    "leafy green": "Leafy Greens",
    "leafy greens": "Leafy Greens",
    "spinach leaves": "Spinach",
    "baby spinach": "Spinach",
    "lettuce leaves": "Lettuce",
    "carrot": "Carrots",
    "tomato": "Tomatoes",
    "egg": "Eggs",
    "wrap": "Wraps",
    "wraps": "Wraps",
    "tortilla wraps": "Wraps",
    "flatbread": "Wraps",
    "peri peri sauce": "Peri Peri Sauce",
    "perinaise": "Peri Peri Sauce",
    "peri-naise": "Peri Peri Sauce",
    "mayonnaise sauce": "Mayonnaise",
    "mayo": "Mayonnaise",
    "hot sauce": "Hot Sauce",
    "tomato sauce": "Tomato Sauce",
    "canned bean": "Canned Beans",
    "canned beans": "Canned Beans",
    "beans can": "Canned Beans",
    "canned food": "Canned Food",
    "canned vegetables": "Canned Vegetables",
}


def image_file_to_data_url(image_path):
    """
    Converts an uploaded image into a base64 data URL so it can be sent
    to the OpenAI vision model.

    Validation included:
    - File must exist.
    - File must be JPG, PNG or WEBP.
    """

    image_path = Path(image_path)

    if not image_path.exists():
        raise ValueError("Uploaded image file could not be found.")

    content_type, _ = mimetypes.guess_type(str(image_path))

    allowed_types = {
        "image/jpeg",
        "image/png",
        "image/webp",
    }

    if content_type not in allowed_types:
        raise ValueError("Only JPG, PNG or WEBP images are supported.")

    image_bytes = image_path.read_bytes()

    if not image_bytes:
        raise ValueError("Uploaded image is empty.")

    encoded_image = base64.b64encode(image_bytes).decode("utf-8")

    return f"data:{content_type};base64,{encoded_image}"


def extract_json_from_ai_response(response_text):
    """
    Extracts JSON from the AI response.

    The prompt requests strict JSON, but this function protects the app
    if the model accidentally adds markdown or extra text.
    """

    if not response_text:
        return {}

    response_text = response_text.strip()

    # Remove markdown code fences if the model accidentally adds them.
    response_text = response_text.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", response_text, re.DOTALL)

    if not match:
        return {}

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def normalise_confidence(value, default=0):
    """
    Converts confidence values into an integer percentage between 0 and 100.

    Handles values like:
    - 85
    - "85"
    - 0.85
    - "0.85"
    """

    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = float(default)

    if 0 <= confidence <= 1:
        confidence = confidence * 100

    confidence = max(0, min(100, confidence))

    return int(round(confidence))


def clean_text(value):
    """
    Cleans a simple ingredient text value.
    """

    if not isinstance(value, str):
        return ""

    value = value.strip().lower()
    value = re.sub(r"[^a-zA-Z0-9\s\-]", "", value)
    value = re.sub(r"\s+", " ", value).strip()

    return value


def normalise_context(value):
    """
    Normalises AI context values.

    Example:
    - "kitchen counter" -> "kitchen_counter"
    - "Kitchen-Counter" -> "kitchen_counter"
    - "outdoor scene" -> "outdoor_scene"
    """

    if not isinstance(value, str):
        return "unclear"

    value = value.strip().lower()
    value = re.sub(r"[\s\-]+", "_", value)
    value = re.sub(r"[^a-z_]", "", value)
    value = re.sub(r"_+", "_", value).strip("_")

    return value or "unclear"


def remove_packaging_words(item_name):
    """
    Removes container/packaging terms from ingredient names.

    Example:
    - "milk carton" becomes "milk"
    - "cheese packet" becomes "cheese"
    - "yogurt cup" becomes "yogurt"
    - "coke can" becomes "coke" and then gets filtered as non-cooking beverage
    """

    words = item_name.split()

    cleaned_words = [
        word
        for word in words
        if word not in PACKAGING_WORDS_TO_REMOVE
    ]

    return " ".join(cleaned_words).strip()


def normalise_ingredient_name(item_name):
    """
    Converts common AI variations into cleaner pantry-friendly ingredient names.
    """

    item_name = clean_text(item_name)

    if not item_name:
        return ""

    if item_name in INGREDIENT_NAME_NORMALISATION:
        return INGREDIENT_NAME_NORMALISATION[item_name]

    return item_name.title()


def is_non_cooking_beverage(item_name):
    """
    Returns True if the item is a ready-to-drink beverage that should not be
    used as a cooking ingredient for recipe generation.
    """

    item_name = clean_text(item_name)

    if item_name in NON_COOKING_BEVERAGES:
        return True

    words = set(item_name.split())

    beverage_markers = {
        "coke",
        "cola",
        "pepsi",
        "fanta",
        "sprite",
        "soda",
        "7up",
    }

    if words.intersection(beverage_markers):
        return True

    return False


def is_invalid_food_name(item_name):
    """
    Returns True if the cleaned item is clearly not a useful cooking ingredient.
    """

    item_name = clean_text(item_name)

    if not item_name:
        return True

    if len(item_name) < 2:
        return True

    if len(item_name) > 60:
        return True

    if item_name in NON_FOOD_WORDS:
        return True

    words = set(item_name.split())

    # Reject if the item is only packaging/object words.
    if words and words.issubset(NON_FOOD_WORDS):
        return True

    # Reject drinks that are not useful cooking ingredients.
    if is_non_cooking_beverage(item_name):
        return True

    return False


def clean_detected_items(raw_items):
    """
    Cleans AI-detected ingredients.

    Supports both formats:
    1. ["Milk", "Tomatoes"]
    2. [{"name": "Milk", "confidence": 90}, {"name": "Tomatoes", "confidence": 82}]

    Validation included:
    - Removes very low-confidence ingredients.
    - Removes duplicates.
    - Removes packaging/object words.
    - Removes non-food terms.
    - Removes non-cooking drinks like Coke.
    - Keeps cooking sauces, condiments, dairy, vegetables, grains, proteins and staples.
    - Limits the total number of ingredients.
    """

    cleaned_items = []
    seen_items = set()

    if not isinstance(raw_items, list):
        return cleaned_items

    for raw_item in raw_items:
        ingredient_name = ""
        ingredient_confidence = 100

        if isinstance(raw_item, dict):
            ingredient_name = raw_item.get("name", "")
            ingredient_confidence = normalise_confidence(
                raw_item.get("confidence", 100),
                default=100,
            )

        elif isinstance(raw_item, str):
            ingredient_name = raw_item
            ingredient_confidence = 100

        else:
            continue

        if ingredient_confidence < MIN_INGREDIENT_CONFIDENCE:
            continue

        ingredient_name = clean_text(ingredient_name)
        ingredient_name = remove_packaging_words(ingredient_name)
        ingredient_name = clean_text(ingredient_name)

        if is_invalid_food_name(ingredient_name):
            continue

        ingredient_name = normalise_ingredient_name(ingredient_name)
        duplicate_key = clean_text(ingredient_name)

        if duplicate_key in seen_items:
            continue

        seen_items.add(duplicate_key)
        cleaned_items.append(ingredient_name)

        if len(cleaned_items) >= MAX_DETECTED_INGREDIENTS:
            break

    return cleaned_items


def get_openai_client():
    """
    Creates the OpenAI client using the API key from Django settings
    or environment variables.
    """

    api_key = getattr(settings, "OPENAI_API_KEY", None) or os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing.")

    return OpenAI(api_key=api_key)


def build_validation_error_message(parsed_response):
    """
    Creates a user-friendly validation message when an image is rejected.
    """

    rejection_reason = parsed_response.get("rejection_reason", "")
    image_context = normalise_context(parsed_response.get("image_context", "unclear"))
    image_quality = normalise_context(parsed_response.get("image_quality", "unclear"))
    confidence = normalise_confidence(parsed_response.get("confidence", 0))

    if rejection_reason:
        return rejection_reason

    if image_context in INVALID_IMAGE_CONTEXTS:
        return (
            "This does not appear to be a refrigerator, pantry, grocery, "
            "kitchen counter, or visible food storage image. Please upload a clear food-related image."
        )

    if image_quality == "poor":
        return (
            "The image quality is too poor for reliable ingredient detection. "
            "Please upload a brighter and clearer image."
        )

    if confidence < MIN_IMAGE_CONFIDENCE:
        return (
            "CulinaAI could not confidently verify this as a valid food or refrigerator image. "
            "Please upload a clearer fridge, pantry, grocery, or food storage image."
        )

    return (
        "The uploaded image could not be validated for ingredient scanning. "
        "Please upload a clearer refrigerator or food-related image."
    )


def validate_ai_image_response(parsed_response):
    """
    Validates the AI's image-level response.

    Checks:
    - Whether the image is food/fridge/pantry related.
    - Whether the image quality is acceptable.
    - Whether the confidence score is high enough.
    """

    if not isinstance(parsed_response, dict):
        return False, "Invalid AI response format."

    image_context = normalise_context(parsed_response.get("image_context", "unclear"))
    image_quality = normalise_context(parsed_response.get("image_quality", "unclear"))
    confidence = normalise_confidence(parsed_response.get("confidence", 0))

    is_valid_food_storage_image = parsed_response.get(
        "is_valid_food_storage_image",
        False,
    )

    if isinstance(is_valid_food_storage_image, str):
        is_valid_food_storage_image = (
            is_valid_food_storage_image.strip().lower() == "true"
        )

    if image_context in INVALID_IMAGE_CONTEXTS:
        return False, build_validation_error_message(parsed_response)

    if image_context not in VALID_IMAGE_CONTEXTS and not is_valid_food_storage_image:
        return False, build_validation_error_message(parsed_response)

    if image_quality == "poor":
        return False, build_validation_error_message(parsed_response)

    if confidence < MIN_IMAGE_CONFIDENCE:
        return False, build_validation_error_message(parsed_response)

    return True, ""


def build_professional_scanner_prompt():
    """
    Builds the professional validation prompt for the AI vision model.

    This keeps image validation strict, improves ingredient recall,
    includes sauces/condiments, and excludes non-cooking beverages.
    """

    return """
You are the professional validation and ingredient detection engine for CulinaAI,
an AI-assisted recipe generation and meal personalisation system.

Your task is to identify ingredients that are useful for COOKING or RECIPE GENERATION.

You must complete TWO stages.

STAGE 1: Validate the uploaded image.
Check whether the image is suitable for refrigerator, pantry, grocery, kitchen counter,
or visible food ingredient scanning.

Valid image types:
- Open refrigerator with visible food items
- Pantry shelf with visible food items
- Kitchen counter with visible ingredients
- Grocery items or food storage image
- Food ingredients arranged together

Invalid image types:
- Person or face photo
- Document, screenshot, laptop, phone, room, car, outdoor image
- Image with no visible food
- Image too dark, blurry, blocked, or impossible to inspect

STAGE 2: Detect cooking-relevant ingredients only.

Important meaning of "ingredient":
Include items that can reasonably be used for cooking, recipe preparation, seasoning,
sauce-making, serving, or meal personalisation.

You SHOULD include:
- Vegetables: tomatoes, onions, lettuce, spinach, salad greens, leafy greens, carrots,
  peppers, cucumber, cabbage, potatoes, mushrooms and other visible vegetables.
- Fruits if useful for meals.
- Dairy items: milk, yogurt, kefir, cheese, cream, butter.
- Protein items: eggs, paneer, tofu, meat, fish, beans, lentils.
- Grains and staples: rice, pasta, noodles, bread, wraps, tortillas.
- Canned cooking items: beans, sweetcorn, chopped tomatoes, tuna, soup, canned vegetables.
- Sauces and condiments used in cooking: mayonnaise, peri peri sauce, perinaise, ketchup,
  mustard, chutney, dressing, soy sauce, hot sauce, tomato sauce, pasta sauce, curry paste.
- Herbs, spices, seasoning mixes, stock cubes, spreads, cooking pastes, dips and marinades.

You SHOULD NOT include:
- Ready-to-drink soft drinks such as Coke, Coca-Cola, Pepsi, Fanta, Sprite, soda, energy drinks.
- Plain bottled water, mineral water, sparkling water or tonic water.
- Containers or packaging as ingredients.
- Shelves, packets, jars, boxes, bottles, cartons, cans, lids, labels, trays, fridge door, hands, plates.
- Brand names.
- Non-food objects.
- Hidden items that are not visible or strongly indicated.

Very important packaged-food rule:
If packaging is visible and the food type is readable or strongly indicated, return the
GENERIC FOOD ITEM, not the package and not the brand.

Examples:
- A yogurt tub should return "Yogurt".
- A milk bottle should return "Milk".
- A kefir bottle should return "Kefir".
- A cheese packet should return "Cheese".
- A mayonnaise/perinaise bottle should return "Mayonnaise" or "Peri Peri Sauce".
- A sauce bottle should return the generic sauce type if readable, such as "Hot Sauce",
  "Tomato Sauce", "Mayonnaise", "Peri Peri Sauce", or "Ketchup".
- A tortilla/wraps packet should return "Tortilla" or "Wraps".
- A canned food item should return the readable generic food, such as "Canned Beans",
  "Sweetcorn", "Tuna", "Canned Tomatoes", or "Canned Vegetables".
- Green leafy vegetables should return "Spinach", "Lettuce", "Salad Greens", or "Leafy Greens"
  depending on what is most visually likely.
- Orange root vegetables should return "Carrots" when visible or strongly indicated.
- A Coke can should NOT return "Coke" because it is a ready-to-drink beverage, not a cooking ingredient.
- A water bottle should NOT return "Water" because it is not useful as a detected cooking ingredient here.

Vegetable checklist:
Before finalising the JSON, specifically check the image for:
- Tomatoes
- Onions
- Spinach
- Lettuce
- Leafy greens
- Salad greens
- Carrots
- Peppers
- Cucumber
- Potatoes
- Mushrooms

Dairy and protein checklist:
Before finalising the JSON, specifically check the image for:
- Milk
- Yogurt
- Kefir
- Cheese
- Eggs
- Paneer
- Cream
- Butter

Packaged cooking item checklist:
Before finalising the JSON, specifically check the image for:
- Wraps
- Tortillas
- Rice
- Pasta
- Noodles
- Canned Beans
- Canned Food
- Mayonnaise
- Peri Peri Sauce
- Hot Sauce
- Ketchup
- Tomato Sauce
- Dressing

Detection style:
- Be systematic and stable.
- Scan from top shelf to bottom shelf.
- Then scan the refrigerator door from top to bottom.
- Look at the front area, back area, and fridge door shelves separately.
- Do not stop after only the most obvious items.
- For a well-stocked fridge, identify all useful visible or strongly indicated cooking ingredients.
- Be careful, but do not be so conservative that you miss obvious packaged cooking items or visible vegetables.
- Avoid duplicates.
- Use simple generic names.

Confidence rules:
- Give each ingredient a confidence score from 0 to 100.
- Include strong packaged-food detections if the label or item type is reasonably clear.
- Include partially visible vegetables if the shape, colour, or location strongly indicates them.
- If exact leafy green type is unclear, return "Leafy Greens" rather than ignoring it.
- If exact canned item is unclear, return "Canned Food" rather than ignoring it.
- If exact sauce type is unclear but it is clearly a cooking sauce, return "Sauce" rather than ignoring it.
- Do not include uncertain items below reasonable confidence.
- If the image is invalid, return an empty ingredients list and explain rejection_reason.

Return ONLY valid JSON.
Do not include markdown.
Do not include explanation outside JSON.

Return JSON exactly in this structure:

{
  "is_valid_food_storage_image": true,
  "image_context": "refrigerator",
  "image_quality": "clear",
  "confidence": 85,
  "rejection_reason": "",
  "ingredients": [
    {
      "name": "Eggs",
      "confidence": 92,
      "category": "protein",
      "visible_evidence": "eggs visible on fridge shelf"
    },
    {
      "name": "Milk",
      "confidence": 90,
      "category": "dairy",
      "visible_evidence": "milk bottle visible"
    },
    {
      "name": "Spinach",
      "confidence": 78,
      "category": "vegetable",
      "visible_evidence": "green leafy vegetables visible on fridge shelf"
    },
    {
      "name": "Carrots",
      "confidence": 76,
      "category": "vegetable",
      "visible_evidence": "orange root vegetables visible in fridge"
    },
    {
      "name": "Peri Peri Sauce",
      "confidence": 82,
      "category": "condiment",
      "visible_evidence": "sauce bottle visible on fridge door"
    }
  ],
  "notes": [
    "User should confirm ingredients before saving or generating recipes."
  ]
}
"""


def scan_fridge_image(fridge_scan):
    """
    Professional AI Refrigerator Scanner service.

    Validation pipeline:
    1. Mark scan as processing.
    2. Validate image file type and existence.
    3. Send image to OpenAI vision model.
    4. Ask AI to validate whether image is fridge/food/pantry related.
    5. Reject invalid non-food images.
    6. Check image quality and confidence.
    7. Extract ingredient-level detections.
    8. Remove duplicates, non-food objects, packaging terms, weak detections,
       and non-cooking drinks.
    9. Save cleaned results into FridgeScan.
    10. Require user confirmation before pantry or recipe use.
    """

    fridge_scan.scan_status = FridgeScan.STATUS_PROCESSING
    fridge_scan.error_message = ""
    fridge_scan.detected_items = []
    fridge_scan.save(
        update_fields=[
            "scan_status",
            "error_message",
            "detected_items",
            "updated_at",
        ]
    )

    try:
        client = get_openai_client()

        image_path = fridge_scan.image.path
        image_data_url = image_file_to_data_url(image_path)

        model_name = getattr(settings, "OPENAI_VISION_MODEL", "gpt-4o-mini")
        prompt = build_professional_scanner_prompt()

        response = client.responses.create(
            model=model_name,
            temperature=0,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": prompt,
                        },
                        {
                            "type": "input_image",
                            "image_url": image_data_url,
                            "detail": "high",
                        },
                    ],
                }
            ],
        )

        response_text = getattr(response, "output_text", "")
        parsed_response = extract_json_from_ai_response(response_text)

        is_valid_image, validation_error = validate_ai_image_response(parsed_response)

        if not is_valid_image:
            fridge_scan.detected_items = []
            fridge_scan.raw_ai_response = response_text
            fridge_scan.scan_status = FridgeScan.STATUS_FAILED
            fridge_scan.error_message = validation_error
            fridge_scan.save(
                update_fields=[
                    "detected_items",
                    "raw_ai_response",
                    "scan_status",
                    "error_message",
                    "updated_at",
                ]
            )

            return {
                "success": False,
                "detected_items": [],
                "message": validation_error,
                "validation": {
                    "is_valid_food_storage_image": False,
                    "image_context": parsed_response.get("image_context", "unclear"),
                    "image_quality": parsed_response.get("image_quality", "unclear"),
                    "confidence": normalise_confidence(
                        parsed_response.get("confidence", 0)
                    ),
                },
            }

        detected_items = clean_detected_items(parsed_response.get("ingredients", []))

        fridge_scan.detected_items = detected_items
        fridge_scan.raw_ai_response = response_text
        fridge_scan.scan_status = FridgeScan.STATUS_COMPLETED

        image_quality = normalise_context(parsed_response.get("image_quality", "unclear"))
        confidence = normalise_confidence(parsed_response.get("confidence", 0))

        if not detected_items:
            fridge_scan.error_message = (
                "The image was accepted as food-related, but no clear cooking ingredients were detected. "
                "Please upload a clearer image or enter ingredients manually."
            )
        elif image_quality == "acceptable" or confidence < 75:
            fridge_scan.error_message = (
                "Some ingredients may be unclear. Please carefully review and edit the detected list before using it."
            )
        else:
            fridge_scan.error_message = ""

        fridge_scan.save(
            update_fields=[
                "detected_items",
                "raw_ai_response",
                "scan_status",
                "error_message",
                "updated_at",
            ]
        )

        return {
            "success": True,
            "detected_items": detected_items,
            "message": "Fridge scan completed and validated successfully.",
            "validation": {
                "is_valid_food_storage_image": True,
                "image_context": parsed_response.get("image_context", "unclear"),
                "image_quality": image_quality,
                "confidence": confidence,
                "ingredient_count": len(detected_items),
            },
        }

    except Exception as error:
        fridge_scan.scan_status = FridgeScan.STATUS_FAILED
        fridge_scan.error_message = str(error)
        fridge_scan.detected_items = []
        fridge_scan.save(
            update_fields=[
                "scan_status",
                "error_message",
                "detected_items",
                "updated_at",
            ]
        )

        return {
            "success": False,
            "detected_items": [],
            "message": str(error),
            "validation": {
                "is_valid_food_storage_image": False,
                "image_context": "error",
                "image_quality": "unknown",
                "confidence": 0,
            },
        }