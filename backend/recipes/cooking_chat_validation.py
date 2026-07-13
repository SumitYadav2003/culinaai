"""
AI Cooking Chat Guardrails and Response Validation for CulinaAI.

Purpose:
- Validates user questions before calling the AI.
- Detects question type, safety/allergy risk, off-topic prompts and missing recipe context.
- Cleans and validates AI replies before saving/displaying them.
- Produces validation metadata that can be stored inside CookingChatMessage.metadata.

This file must be placed here:
backend/recipes/cooking_chat_validation.py
"""

import re
from typing import Dict, List


ALLERGY_TERMS = [
    "allergy",
    "allergic",
    "allergen",
    "intolerance",
    "peanut",
    "nuts",
    "nut",
    "milk",
    "dairy",
    "egg",
    "eggs",
    "gluten",
    "wheat",
    "soy",
    "sesame",
    "shellfish",
    "fish",
]

FOOD_SAFETY_TERMS = [
    "raw",
    "undercooked",
    "expired",
    "mould",
    "mold",
    "smell bad",
    "food poisoning",
    "left overnight",
    "reheat",
    "safe to eat",
    "spoiled",
    "rotten",
]

OFF_TOPIC_TERMS = [
    "write my assignment",
    "football",
    "cricket score",
    "stock market",
    "crypto",
    "movie",
    "dating",
    "visa",
    "coding homework",
    "python code",
    "django code",
    "hack",
    "password",
]

COOKING_RELEVANT_TERMS = [
    "ingredient",
    "replace",
    "substitute",
    "instead",
    "cook",
    "cooking",
    "recipe",
    "step",
    "spicy",
    "sweet",
    "salty",
    "sour",
    "bitter",
    "bland",
    "watery",
    "dry",
    "burnt",
    "burned",
    "thick",
    "thin",
    "sauce",
    "pantry",
    "healthy",
    "healthier",
    "cheap",
    "cheaper",
    "protein",
    "calorie",
    "calories",
    "vegetarian",
    "vegan",
    "gluten",
    "allergy",
    "allergic",
    "serve",
    "serving",
    "meal",
    "flavour",
    "flavor",
    "taste",
    "texture",
    "oven",
    "pan",
    "boil",
    "fry",
    "bake",
    "grill",
    "roast",
    "mix",
    "chop",
    "slice",
    "blend",
]


def normalise_text(value: str) -> str:
    return str(value or "").strip().lower()


def detect_question_type(question: str) -> str:
    text = normalise_text(question)

    if any(term in text for term in ["replace", "substitute", "instead", "don't have", "do not have", "without"]):
        return "ingredient_substitution"

    if any(term in text for term in ["pantry", "already have", "available ingredients"]):
        return "pantry_adaptation"

    if any(term in text for term in ["explain", "step", "simple", "beginner"]):
        return "step_explanation"

    if any(term in text for term in ["too spicy", "too dry", "too watery", "burnt", "burned", "bland", "mistake", "fix"]):
        return "cooking_problem_fix"

    if any(term in text for term in ["cheap", "cheaper", "budget", "cost"]):
        return "budget_adaptation"

    if any(term in text for term in ["healthy", "healthier", "calorie", "calories", "fat", "oil"]):
        return "health_adaptation"

    if any(term in text for term in ["protein", "high protein"]):
        return "protein_adaptation"

    if any(term in text for term in ["allergy", "allergic", "intolerance", "safe to eat"]):
        return "safety_or_allergy"

    return "general_cooking_help"


def detect_terms(text: str, terms: List[str]) -> List[str]:
    lower_text = normalise_text(text)
    matches = []

    for term in terms:
        if term in lower_text:
            matches.append(term)

    return sorted(set(matches))


def is_cooking_related(question: str, recipe) -> bool:
    text = normalise_text(question)

    if any(term in text for term in COOKING_RELEVANT_TERMS):
        return True

    recipe_terms = []

    if recipe:
        recipe_terms.append(getattr(recipe, "title", ""))

        ingredients_text = getattr(recipe, "ingredients_text", "") or ""

        for ingredient in re.split(r"[\n,;|]+", ingredients_text):
            clean_ingredient = normalise_text(ingredient)

            if len(clean_ingredient) >= 3:
                recipe_terms.append(clean_ingredient)

    for term in recipe_terms:
        clean_term = normalise_text(term)

        if clean_term and clean_term in text:
            return True

    return False


def validate_recipe_context(recipe) -> Dict:
    missing_fields = []

    if not getattr(recipe, "title", ""):
        missing_fields.append("title")

    if not getattr(recipe, "ingredients_text", ""):
        missing_fields.append("ingredients")

    if not (getattr(recipe, "instructions_text", "") or getattr(recipe, "ai_response", "")):
        missing_fields.append("instructions")

    score = 100

    if missing_fields:
        score -= len(missing_fields) * 20

    score = max(0, score)

    return {
        "score": score,
        "status": "ok" if score >= 70 else "limited_context",
        "missing_fields": missing_fields,
        "has_enough_context": score >= 70,
    }


def validate_user_question(question: str, recipe=None, quick_prompt_key: str = "") -> Dict:
    clean_question = str(question or "").strip()

    flags = []
    warnings = []

    if not clean_question and not quick_prompt_key:
        return {
            "is_allowed": False,
            "score": 0,
            "status": "blocked",
            "reason": "empty_question",
            "message": "Please type a cooking question or choose a quick prompt.",
            "question_type": "empty",
            "flags": ["empty_question"],
            "warnings": [],
            "requires_safety_warning": False,
            "matched_allergy_terms": [],
            "matched_safety_terms": [],
        }

    if len(clean_question) > 1200:
        flags.append("question_too_long")
        warnings.append("Question was very long and may need shortening.")

    matched_off_topic_terms = detect_terms(clean_question, OFF_TOPIC_TERMS)

    if matched_off_topic_terms:
        flags.append("off_topic")
        return {
            "is_allowed": False,
            "score": 10,
            "status": "blocked",
            "reason": "off_topic",
            "message": "I can only help with this recipe, cooking steps, ingredients, pantry items, substitutions, diet changes and cooking problems.",
            "question_type": "off_topic",
            "flags": flags,
            "warnings": warnings,
            "requires_safety_warning": False,
            "matched_allergy_terms": [],
            "matched_safety_terms": [],
        }

    cooking_related = is_cooking_related(clean_question, recipe)

    if not cooking_related and not quick_prompt_key:
        flags.append("possibly_off_topic")
        warnings.append("Question may not be strongly related to the current recipe.")

    matched_allergy_terms = detect_terms(clean_question, ALLERGY_TERMS)
    matched_safety_terms = detect_terms(clean_question, FOOD_SAFETY_TERMS)

    if matched_allergy_terms:
        flags.append("allergy_related")

    if matched_safety_terms:
        flags.append("food_safety_related")

    requires_safety_warning = bool(matched_allergy_terms or matched_safety_terms)

    score = 100

    if "question_too_long" in flags:
        score -= 20

    if "possibly_off_topic" in flags:
        score -= 25

    if requires_safety_warning:
        score -= 5

    score = max(0, score)

    return {
        "is_allowed": score >= 40,
        "score": score,
        "status": "approved" if score >= 70 else "approved_with_warnings",
        "reason": "",
        "message": "",
        "question_type": detect_question_type(clean_question),
        "flags": flags,
        "warnings": warnings,
        "requires_safety_warning": requires_safety_warning,
        "matched_allergy_terms": matched_allergy_terms,
        "matched_safety_terms": matched_safety_terms,
    }


def clean_assistant_reply(reply: str) -> str:
    if not reply:
        return ""

    cleaned_reply = str(reply).strip()

    cleaned_reply = re.sub(
        r"^\s*#{1,6}\s*",
        "",
        cleaned_reply,
        flags=re.MULTILINE,
    )

    cleaned_reply = cleaned_reply.replace("**", "")
    cleaned_reply = cleaned_reply.replace("__", "")
    cleaned_reply = cleaned_reply.replace("`", "")

    cleaned_reply = re.sub(
        r"^\s*[-*]\s+",
        "• ",
        cleaned_reply,
        flags=re.MULTILINE,
    )

    cleaned_reply = re.sub(
        r"\n{3,}",
        "\n\n",
        cleaned_reply,
    )

    return cleaned_reply.strip()


def safety_warning_text(question_validation: Dict) -> str:
    if not question_validation.get("requires_safety_warning"):
        return ""

    allergy_terms = question_validation.get("matched_allergy_terms", [])
    safety_terms = question_validation.get("matched_safety_terms", [])

    if allergy_terms:
        return (
            "Safety note: If this involves an allergy or intolerance, please check ingredient labels carefully "
            "and avoid the ingredient completely if you have a severe allergy."
        )

    if safety_terms:
        return (
            "Food safety note: If food smells bad, looks spoiled, is expired, or has been stored unsafely, "
            "it is safer not to eat it."
        )

    return ""


def validate_assistant_reply(reply: str, question_validation: Dict, recipe_context_validation: Dict) -> Dict:
    cleaned_reply = clean_assistant_reply(reply)

    flags = []
    warnings = []

    if not cleaned_reply:
        flags.append("empty_reply")
        warnings.append("Assistant reply was empty.")

    if len(cleaned_reply) > 2600:
        flags.append("reply_too_long")
        warnings.append("Assistant reply is quite long.")

    if any(symbol in cleaned_reply for symbol in ["###", "**", "__", "`"]):
        flags.append("markdown_not_cleaned")

    if not recipe_context_validation.get("has_enough_context", False):
        flags.append("limited_recipe_context")
        warnings.append("Recipe context is incomplete.")

    required_warning = safety_warning_text(question_validation)

    if required_warning and required_warning.lower() not in cleaned_reply.lower():
        cleaned_reply = f"{cleaned_reply}\n\n{required_warning}".strip()
        flags.append("safety_warning_added")

    score = 100

    if "empty_reply" in flags:
        score -= 80

    if "reply_too_long" in flags:
        score -= 15

    if "markdown_not_cleaned" in flags:
        score -= 15

    if "limited_recipe_context" in flags:
        score -= 10

    if "safety_warning_added" in flags:
        score -= 5

    score = max(0, score)

    if score >= 85:
        status = "verified"
    elif score >= 70:
        status = "verified_with_notes"
    elif score >= 50:
        status = "needs_caution"
    else:
        status = "failed"

    return {
        "score": score,
        "status": status,
        "flags": flags,
        "warnings": warnings,
        "cleaned_reply": cleaned_reply,
        "safety_warning_required": question_validation.get("requires_safety_warning", False),
    }


def build_guardrail_instruction(question_validation: Dict, recipe_context_validation: Dict) -> str:
    instruction_lines = [
        "GUARDRAIL INSTRUCTIONS",
        f"Question type: {question_validation.get('question_type')}",
        f"Question validation status: {question_validation.get('status')}",
        f"Recipe context status: {recipe_context_validation.get('status')}",
        "Answer only about the current recipe, cooking, ingredients, pantry, dietary changes or cooking problems.",
        "Do not use Markdown symbols such as ###, ##, #, **, __ or backticks.",
        "Use plain text headings such as Best substitute: or What to do:",
        "Keep the answer practical and not too long.",
    ]

    if question_validation.get("requires_safety_warning"):
        instruction_lines.append(
            "The question includes allergy or food-safety risk. Include a clear safety note."
        )

    if not recipe_context_validation.get("has_enough_context"):
        instruction_lines.append(
            "The recipe context is limited. Be careful and mention when information is missing."
        )

    return "\n".join(instruction_lines)


def build_validation_metadata(
    *,
    question_validation: Dict,
    recipe_context_validation: Dict,
    reply_validation: Dict = None,
) -> Dict:
    return {
        "question_validation": question_validation,
        "recipe_context_validation": recipe_context_validation,
        "reply_validation": reply_validation or {},
        "guardrails_version": "cooking-chat-guardrails-v1",
    }
