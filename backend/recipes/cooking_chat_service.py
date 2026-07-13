"""
AI Cooking Chat Assistant service for CulinaAI.

Advanced version with guardrails and response validation.

Purpose:
- Provides recipe-specific cooking support after a recipe has been generated/saved.
- Helps users with ingredient substitutions, missing ingredients, cooking mistakes,
  step explanations, pantry-aware suggestions, dietary adjustments and cost-saving ideas.
- Saves chat history using CookingChatSession and CookingChatMessage models.
- Applies cooking chat guardrails before and after AI response generation.
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from django.conf import settings
from django.utils import timezone

from .cooking_chat_validation import (
    build_guardrail_instruction,
    build_validation_metadata,
    clean_assistant_reply,
    validate_assistant_reply,
    validate_recipe_context,
    validate_user_question,
)
from .models import (
    CookingChatMessage,
    CookingChatSession,
    PantryItem,
    Recipe,
)


QUICK_PROMPTS = [
    {
        "key": "substitute_ingredient",
        "label": "Suggest ingredient substitute",
        "icon": "bi-arrow-left-right",
        "prompt": (
            "I do not have one of the ingredients in this recipe. "
            "Suggest the best ingredient substitutes and explain which one fits this recipe best."
        ),
    },
    {
        "key": "use_pantry",
        "label": "Use my pantry items",
        "icon": "bi-basket2",
        "prompt": (
            "Check my available pantry items and suggest how I can adapt this recipe using what I already have."
        ),
    },
    {
        "key": "explain_step",
        "label": "Explain a step simply",
        "icon": "bi-list-check",
        "prompt": (
            "Explain the cooking steps in a simpler beginner-friendly way and highlight any steps where I should be careful."
        ),
    },
    {
        "key": "fix_mistake",
        "label": "Fix cooking mistake",
        "icon": "bi-tools",
        "prompt": (
            "Help me fix a cooking problem while making this recipe. "
            "Give practical rescue tips for common mistakes like too spicy, too dry, too watery, burnt, bland or overcooked."
        ),
    },
    {
        "key": "make_cheaper",
        "label": "Make it cheaper",
        "icon": "bi-cash-coin",
        "prompt": (
            "Suggest budget-friendly changes for this recipe without losing the main taste and texture."
        ),
    },
    {
        "key": "make_healthier",
        "label": "Make it healthier",
        "icon": "bi-heart-pulse",
        "prompt": (
            "Suggest healthier changes for this recipe while keeping it tasty and realistic for home cooking."
        ),
    },
    {
        "key": "less_spicy",
        "label": "Make it less spicy",
        "icon": "bi-emoji-smile",
        "prompt": (
            "Suggest how to make this recipe less spicy and how to balance the flavour if it is already too spicy."
        ),
    },
    {
        "key": "more_protein",
        "label": "Increase protein",
        "icon": "bi-lightning-charge",
        "prompt": (
            "Suggest how to increase the protein in this recipe using practical ingredients."
        ),
    },
]


@dataclass
class AssistantResult:
    """
    Structured result returned by the cooking chat assistant.
    """

    success: bool
    reply: str
    session: CookingChatSession
    user_message: Optional[CookingChatMessage] = None
    assistant_message: Optional[CookingChatMessage] = None
    error: str = ""


def get_quick_prompts() -> List[Dict[str, str]]:
    """
    Returns quick prompt buttons for the frontend chat UI.
    """

    return QUICK_PROMPTS


def get_quick_prompt(prompt_key: str) -> Optional[Dict[str, str]]:
    """
    Finds a quick prompt by key.
    """

    if not prompt_key:
        return None

    for prompt in QUICK_PROMPTS:
        if prompt["key"] == prompt_key:
            return prompt

    return None


def get_or_create_chat_session(user, recipe: Recipe) -> CookingChatSession:
    """
    Gets the active chat session for this user and recipe.
    Creates one if it does not exist.
    """

    session, _created = CookingChatSession.objects.get_or_create(
        user=user,
        recipe=recipe,
        is_active=True,
        defaults={
            "title": f"AI Cooking Assistant - {recipe.title[:120]}",
        },
    )

    return session


def get_chat_messages(session: CookingChatSession):
    """
    Returns all chat messages for one session.
    """

    return session.messages.order_by("created_at")


def build_recipe_context(recipe: Recipe) -> str:
    """
    Builds a compact recipe context for the assistant.
    """

    cuisine_name = recipe.cuisine.name if getattr(recipe, "cuisine", None) else "Not specified"
    meal_type_name = recipe.meal_type.name if getattr(recipe, "meal_type", None) else "Not specified"

    diet_preferences = []

    try:
        diet_preferences = [
            preference.name
            for preference in recipe.diet_preferences.all()
        ]
    except Exception:
        diet_preferences = []

    recipe_context = f"""
RECIPE CONTEXT
Title: {recipe.title}
Cuisine: {cuisine_name}
Meal type: {meal_type_name}
Difficulty: {recipe.difficulty or "Not specified"}
Cooking time: {recipe.cooking_time_minutes or "Not specified"} minutes
Servings: {getattr(recipe, "servings", "") or "Not specified"}
Diet preferences: {", ".join(diet_preferences) if diet_preferences else "Not specified"}

Ingredients:
{recipe.ingredients_text or "No ingredients stored."}

Instructions:
{recipe.instructions_text or recipe.ai_response or "No instructions stored."}
""".strip()

    return recipe_context


def build_pantry_context(user) -> str:
    """
    Builds a pantry-aware context from available, non-expired pantry items.
    """

    today = timezone.localdate()

    no_expiry_items = (
        PantryItem.objects.filter(
            user=user,
            is_available=True,
            expiry_date__isnull=True,
        )
        .order_by("ingredient_name")[:80]
    )

    valid_expiry_items = (
        PantryItem.objects.filter(
            user=user,
            is_available=True,
            expiry_date__gte=today,
        )
        .order_by("expiry_date", "ingredient_name")[:80]
    )

    combined_items = []
    seen_item_ids = set()

    for item in list(no_expiry_items) + list(valid_expiry_items):
        if item.id in seen_item_ids:
            continue

        seen_item_ids.add(item.id)
        combined_items.append(item)

    if not combined_items:
        return "PANTRY CONTEXT\nNo available pantry items found for this user."

    pantry_lines = []

    for item in combined_items[:80]:
        expiry_text = ""

        if item.expiry_date:
            expiry_text = f", expiry: {item.expiry_date}"

        quantity_text = ""

        if item.quantity:
            quantity_text = f", quantity: {item.quantity} {item.unit}"

        pantry_lines.append(
            f"- {item.ingredient_name} ({item.category}{quantity_text}{expiry_text})"
        )

    return "PANTRY CONTEXT\nAvailable pantry items:\n" + "\n".join(pantry_lines)


def build_recent_chat_context(session: CookingChatSession, limit: int = 10) -> str:
    """
    Builds recent chat context so the assistant can maintain continuity.
    """

    recent_messages = list(
        session.messages.order_by("-created_at")[:limit]
    )

    recent_messages.reverse()

    if not recent_messages:
        return "RECENT CHAT HISTORY\nNo previous messages yet."

    lines = []

    for message in recent_messages:
        sender = (
            "User"
            if message.sender == CookingChatMessage.SENDER_USER
            else "Assistant"
        )
        lines.append(f"{sender}: {message.message}")

    return "RECENT CHAT HISTORY\n" + "\n".join(lines)


def build_system_instruction() -> str:
    """
    System instruction for the AI Cooking Chat Assistant.
    """

    return """
You are CulinaAI's advanced recipe-specific cooking assistant.

Your role:
- Help the user after they have generated or saved a recipe.
- Give practical cooking support, ingredient substitutions, pantry-aware suggestions,
  cooking mistake fixes, step explanations, budget changes, dietary adjustments,
  flavour balancing and beginner-friendly guidance.
- Always use the provided recipe context and pantry context.
- Prefer realistic home-cooking suggestions.
- Keep answers focused on the current recipe unless the user clearly asks otherwise.
- When suggesting substitutions, explain the best option first and then alternatives.
- If the user has pantry items that can help, mention them.
- If the user's request may conflict with dietary preferences/allergies from the recipe context,
  warn them politely.
- Do not invent exact medical or allergy safety guarantees.
- Do not claim the food is safe for a severe allergy unless the user verifies ingredients.
- Keep the tone helpful, clear and friendly.
- Do not use Markdown formatting symbols.
- Do not use ###, ##, #, **bold**, __bold__, or backticks.
- Use plain text headings like Best substitute: instead of Markdown headings.
""".strip()


def build_user_prompt(
    user_question: str,
    recipe: Recipe,
    session: CookingChatSession,
    quick_prompt_label: str = "",
    question_validation: Dict = None,
    recipe_context_validation: Dict = None,
) -> str:
    """
    Builds the final user prompt for the model.
    """

    question_validation = question_validation or {}
    recipe_context_validation = recipe_context_validation or {}

    recipe_context = build_recipe_context(recipe)
    pantry_context = build_pantry_context(session.user)
    recent_chat_context = build_recent_chat_context(session)
    guardrail_instruction = build_guardrail_instruction(
        question_validation=question_validation,
        recipe_context_validation=recipe_context_validation,
    )

    quick_prompt_context = ""

    if quick_prompt_label:
        quick_prompt_context = f"\nQUICK PROMPT USED: {quick_prompt_label}\n"

    return f"""
{guardrail_instruction}

{recipe_context}

{pantry_context}

{recent_chat_context}
{quick_prompt_context}

USER QUESTION:
{user_question}

Answer as CulinaAI's cooking assistant. Be practical, recipe-specific, safe and helpful.
""".strip()


def _get_openai_client():
    """
    Creates an OpenAI client if the API key is available.
    """

    api_key = getattr(settings, "OPENAI_API_KEY", None) or os.getenv("OPENAI_API_KEY")

    if not api_key:
        return None

    try:
        from openai import OpenAI
    except ImportError:
        return None

    return OpenAI(api_key=api_key)


def call_ai_cooking_assistant(user_prompt: str) -> Tuple[str, str]:
    """
    Calls the AI model.
    """

    model_name = (
        getattr(settings, "OPENAI_CHAT_MODEL", None)
        or getattr(settings, "OPENAI_MODEL", None)
        or os.getenv("OPENAI_CHAT_MODEL")
        or os.getenv("OPENAI_MODEL")
        or "gpt-4o-mini"
    )

    client = _get_openai_client()

    if client is None:
        fallback_reply = (
            "I can help with this recipe, but the AI provider is not configured yet. "
            "Please make sure OPENAI_API_KEY is available in your environment/settings "
            "and the OpenAI package is installed. Once configured, I will answer with "
            "recipe-specific substitutions, pantry-aware suggestions and cooking guidance."
        )
        return fallback_reply, "not-configured"

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": build_system_instruction(),
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        temperature=0.45,
        max_tokens=700,
    )

    reply = response.choices[0].message.content.strip()
    reply = clean_assistant_reply(reply)

    return reply, model_name


def ask_cooking_assistant(
    *,
    user,
    recipe: Recipe,
    question: str,
    quick_prompt_key: str = "",
) -> AssistantResult:
    """
    Main service function with validation guardrails.
    """

    clean_question = (question or "").strip()

    quick_prompt = get_quick_prompt(quick_prompt_key)
    quick_prompt_label = quick_prompt["label"] if quick_prompt else ""

    if not clean_question and quick_prompt:
        clean_question = quick_prompt["prompt"]

    session = get_or_create_chat_session(user, recipe)

    recipe_context_validation = validate_recipe_context(recipe)
    question_validation = validate_user_question(
        question=clean_question,
        recipe=recipe,
        quick_prompt_key=quick_prompt_key,
    )

    if not question_validation.get("is_allowed"):
        blocked_reply = question_validation.get(
            "message",
            "I can only help with this recipe and cooking-related questions.",
        )

        user_message = None

        if clean_question:
            user_message = CookingChatMessage.objects.create(
                session=session,
                sender=CookingChatMessage.SENDER_USER,
                message=clean_question,
                quick_prompt_label=quick_prompt_label,
                metadata=build_validation_metadata(
                    question_validation=question_validation,
                    recipe_context_validation=recipe_context_validation,
                ),
            )

        assistant_message = CookingChatMessage.objects.create(
            session=session,
            sender=CookingChatMessage.SENDER_ASSISTANT,
            message=blocked_reply,
            quick_prompt_label=quick_prompt_label,
            ai_model="guardrail-blocked",
            metadata=build_validation_metadata(
                question_validation=question_validation,
                recipe_context_validation=recipe_context_validation,
            ),
        )

        return AssistantResult(
            success=False,
            reply=blocked_reply,
            session=session,
            user_message=user_message,
            assistant_message=assistant_message,
            error=question_validation.get("reason", "blocked"),
        )

    user_message = CookingChatMessage.objects.create(
        session=session,
        sender=CookingChatMessage.SENDER_USER,
        message=clean_question,
        quick_prompt_label=quick_prompt_label,
        metadata=build_validation_metadata(
            question_validation=question_validation,
            recipe_context_validation=recipe_context_validation,
        ),
    )

    try:
        user_prompt = build_user_prompt(
            user_question=clean_question,
            recipe=recipe,
            session=session,
            quick_prompt_label=quick_prompt_label,
            question_validation=question_validation,
            recipe_context_validation=recipe_context_validation,
        )

        assistant_reply, model_name = call_ai_cooking_assistant(
            user_prompt=user_prompt,
        )

        reply_validation = validate_assistant_reply(
            reply=assistant_reply,
            question_validation=question_validation,
            recipe_context_validation=recipe_context_validation,
        )

        final_reply = reply_validation["cleaned_reply"]

        assistant_message = CookingChatMessage.objects.create(
            session=session,
            sender=CookingChatMessage.SENDER_ASSISTANT,
            message=final_reply,
            quick_prompt_label=quick_prompt_label,
            ai_model=model_name,
            metadata=build_validation_metadata(
                question_validation=question_validation,
                recipe_context_validation=recipe_context_validation,
                reply_validation=reply_validation,
            ),
        )

        session.updated_at = timezone.now()
        session.save(update_fields=["updated_at"])

        return AssistantResult(
            success=True,
            reply=final_reply,
            session=session,
            user_message=user_message,
            assistant_message=assistant_message,
        )

    except Exception as error:
        error_message = (
            "Sorry, I could not generate a cooking assistant response right now. "
            "Please try again in a moment."
        )

        assistant_message = CookingChatMessage.objects.create(
            session=session,
            sender=CookingChatMessage.SENDER_ASSISTANT,
            message=error_message,
            quick_prompt_label=quick_prompt_label,
            ai_model="error",
            metadata={
                "error": str(error),
                "quick_prompt_key": quick_prompt_key,
                "recipe_id": recipe.id,
                "guardrails_version": "cooking-chat-guardrails-v1",
            },
        )

        return AssistantResult(
            success=False,
            reply=error_message,
            session=session,
            user_message=user_message,
            assistant_message=assistant_message,
            error=str(error),
        )


def build_cooking_chat_context(user, recipe: Recipe) -> Dict:
    """
    Builds context for rendering the chat UI on saved recipe detail page.
    """

    session = get_or_create_chat_session(user, recipe)

    return {
        "cooking_chat_session": session,
        "cooking_chat_messages": get_chat_messages(session),
        "cooking_chat_quick_prompts": get_quick_prompts(),
    }
