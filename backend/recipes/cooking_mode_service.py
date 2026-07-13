"""
Cooking mode service for CulinaAI.

Purpose:
- Converts a saved recipe's instruction text into clean step-by-step cooking mode data.
- Avoids treating recipe title, cooking time, ingredients, cost, pairing suggestions,
  or other AI-output metadata as cooking steps.
- Adds a sensible timer duration for each actual cooking step.
"""

import json
import re


STEP_START_PATTERN = re.compile(
    r"^\s*(?:step\s*)?(\d+)[\.\):\-]\s*",
    re.IGNORECASE,
)

TIME_PATTERN = re.compile(
    r"(\d+)\s*(?:minutes|minute|mins|min)\b",
    re.IGNORECASE,
)

INSTRUCTION_HEADING_PATTERN = re.compile(
    r"^\s*(?:cooking\s+instructions|instructions|method|directions|steps|preparation\s+method)\s*:?\s*$",
    re.IGNORECASE,
)

STOP_HEADING_PATTERN = re.compile(
    r"^\s*(?:"
    r"ingredients|ingredient\s+list|recipe\s+title|title|"
    r"servings|serving\s+suggestion|pairing\s+suggestions|"
    r"estimated\s+cost|cost|nutrition|nutritional\s+information|"
    r"allergy\s+notes|allergen\s+notes|dietary\s+tags|"
    r"tips|notes|storage|summary"
    r")\s*:?\s*$",
    re.IGNORECASE,
)

METADATA_LINE_PATTERN = re.compile(
    r"^\s*(?:"
    r"recipe\s+title|title|cuisine|meal\s+type|difficulty|"
    r"servings|serves|number\s+of\s+people|"
    r"preparation\s+time|prep\s+time|cooking\s+time|cook\s+time|total\s+time|"
    r"estimated\s+cost|cost|pairing\s+suggestions|serving\s+suggestion|"
    r"nutrition|calories|allergy\s+notes|dietary\s+tags"
    r")\s*:",
    re.IGNORECASE,
)


def _clean_line(value):
    """
    Cleans one instruction line.
    """

    if not value:
        return ""

    line = str(value).strip()
    line = re.sub(r"^[\-\*\•]\s*", "", line)
    line = re.sub(r"\s+", " ", line)

    return line.strip()


def _is_heading_only(line):
    """
    Checks if a line is only a common recipe section heading.
    """

    clean_line = _clean_line(line)

    if not clean_line:
        return True

    return bool(
        INSTRUCTION_HEADING_PATTERN.match(clean_line)
        or STOP_HEADING_PATTERN.match(clean_line)
    )


def _is_metadata_line(line):
    """
    Checks if a line belongs to recipe metadata, not cooking instructions.
    """

    clean_line = _clean_line(line)

    if not clean_line:
        return True

    if METADATA_LINE_PATTERN.match(clean_line):
        return True

    lower_line = clean_line.lower()

    # Avoid common AI output labels from becoming steps.
    blocked_prefixes = [
        "recipe title:",
        "title:",
        "ingredients:",
        "ingredient list:",
        "servings:",
        "serves:",
        "difficulty:",
        "cuisine:",
        "meal type:",
        "cooking time:",
        "cook time:",
        "preparation time:",
        "prep time:",
        "total time:",
        "estimated cost:",
        "pairing suggestions:",
        "serving suggestion:",
        "nutrition:",
        "calories:",
        "allergy notes:",
        "dietary tags:",
    ]

    return any(lower_line.startswith(prefix) for prefix in blocked_prefixes)


def _normalise_text(text):
    """
    Normalises line breaks without removing useful structure.
    """

    return str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _isolate_instruction_section(text):
    """
    Tries to extract only the actual instruction/method section from full AI output.

    This prevents lines like:
    - RECIPE TITLE: ...
    - Cooking time: 60 minutes
    - Ingredients:
    from becoming cooking steps.
    """

    normalised_text = _normalise_text(text)

    if not normalised_text:
        return ""

    lines = normalised_text.split("\n")

    # 1. Best case: find explicit "Instructions" / "Method" heading.
    start_index = None

    for index, line in enumerate(lines):
        if INSTRUCTION_HEADING_PATTERN.match(_clean_line(line)):
            start_index = index + 1
            break

    if start_index is not None:
        selected_lines = []

        for line in lines[start_index:]:
            clean_line = _clean_line(line)

            if not clean_line:
                continue

            # Stop when another recipe section starts.
            if STOP_HEADING_PATTERN.match(clean_line) or _is_metadata_line(clean_line):
                # Allow numbered instruction lines even if they contain time.
                if not STEP_START_PATTERN.match(clean_line):
                    break

            selected_lines.append(clean_line)

        if selected_lines:
            return "\n".join(selected_lines)

    # 2. Fallback: find first explicit numbered/step instruction.
    first_step_index = None

    for index, line in enumerate(lines):
        clean_line = _clean_line(line)

        if re.match(r"^\s*(?:step\s*)?1[\.\):\-]\s+", clean_line, re.IGNORECASE):
            first_step_index = index
            break

    if first_step_index is not None:
        selected_lines = []

        for line in lines[first_step_index:]:
            clean_line = _clean_line(line)

            if not clean_line:
                continue

            if STOP_HEADING_PATTERN.match(clean_line) or _is_metadata_line(clean_line):
                if not STEP_START_PATTERN.match(clean_line):
                    break

            selected_lines.append(clean_line)

        if selected_lines:
            return "\n".join(selected_lines)

    # 3. Last fallback: remove obvious metadata and headings.
    selected_lines = []

    for line in lines:
        clean_line = _clean_line(line)

        if not clean_line:
            continue

        if _is_heading_only(clean_line) or _is_metadata_line(clean_line):
            continue

        selected_lines.append(clean_line)

    return "\n".join(selected_lines)


def _split_long_paragraph(text):
    """
    Fallback splitter for recipes where instructions are saved as one long paragraph.
    """

    if not text:
        return []

    sentence_parts = re.split(r"(?<=[.!?])\s+", text)

    parts = []

    for sentence in sentence_parts:
        clean_sentence = _clean_line(sentence)

        if len(clean_sentence) >= 12 and not _is_metadata_line(clean_sentence):
            parts.append(clean_sentence)

    return parts


def extract_cooking_steps(instructions_text):
    """
    Extracts clean cooking steps from saved recipe instructions.

    Supports:
    - Step 1: ...
    - 1. ...
    - 1) ...
    - bullet points
    - paragraph fallback
    """

    isolated_text = _isolate_instruction_section(instructions_text)

    if not isolated_text:
        return [
            "Review the saved recipe instructions before starting your cooking session."
        ]

    raw_lines = isolated_text.split("\n")

    useful_lines = []

    for line in raw_lines:
        clean_line = _clean_line(line)

        if not clean_line:
            continue

        if _is_heading_only(clean_line) or _is_metadata_line(clean_line):
            continue

        useful_lines.append(clean_line)

    if not useful_lines:
        useful_lines = _split_long_paragraph(isolated_text)

    steps = []
    current_step = ""

    for line in useful_lines:
        match = STEP_START_PATTERN.match(line)

        if match:
            if current_step:
                steps.append(current_step.strip())

            current_step = STEP_START_PATTERN.sub("", line).strip()
        else:
            # Bullet-style instruction lines should usually become separate steps.
            if not current_step:
                current_step = line.strip()
            else:
                # If line looks like a new action sentence, create a new step.
                if len(current_step) > 120 and not line[0].islower():
                    steps.append(current_step.strip())
                    current_step = line.strip()
                else:
                    current_step = f"{current_step} {line}".strip()

    if current_step:
        steps.append(current_step.strip())

    # If parser created only one huge step, split it by sentences.
    if len(steps) == 1 and len(steps[0]) > 320:
        fallback_steps = _split_long_paragraph(steps[0])

        if len(fallback_steps) > 1:
            steps = fallback_steps

    clean_steps = []

    for step in steps:
        clean_step = _clean_line(step)

        if clean_step and not _is_metadata_line(clean_step):
            clean_steps.append(clean_step)

    if not clean_steps:
        clean_steps = [
            "Review the saved recipe instructions before starting your cooking session."
        ]

    return clean_steps


def estimate_step_minutes(step_text, default_minutes):
    """
    Finds a timer duration from the step text, otherwise uses default_minutes.

    Important:
    This only runs on real cooking steps after metadata has been removed.
    So recipe-level "60 minutes" will not incorrectly become Step 1 timer.
    """

    match = TIME_PATTERN.search(step_text or "")

    if match:
        try:
            minutes = int(match.group(1))
            return max(1, min(minutes, 45))
        except ValueError:
            pass

    return max(1, int(default_minutes or 3))


def make_step_title(step_text):
    """
    Builds a short title from the step text.
    """

    words = str(step_text or "").split()

    if not words:
        return "Cooking Step"

    title = " ".join(words[:7])

    if len(words) > 7:
        title += "..."

    return title


def build_cooking_mode_context(recipe):
    """
    Builds template context for interactive cooking mode.
    """

    raw_instructions = (
        recipe.instructions_text
        or recipe.ai_response
        or "Review this recipe before cooking."
    )

    extracted_steps = extract_cooking_steps(raw_instructions)

    total_minutes = recipe.cooking_time_minutes or 30
    default_step_minutes = max(1, round(total_minutes / max(len(extracted_steps), 1)))

    cooking_steps = []

    for index, step_text in enumerate(extracted_steps, start=1):
        timer_minutes = estimate_step_minutes(
            step_text=step_text,
            default_minutes=default_step_minutes,
        )

        cooking_steps.append(
            {
                "number": index,
                "title": make_step_title(step_text),
                "text": step_text,
                "timer_minutes": timer_minutes,
            }
        )

    context = {
        "recipe": recipe,
        "cooking_steps": cooking_steps,
        "cooking_steps_json": json.dumps(cooking_steps),
        "total_steps": len(cooking_steps),
        "estimated_total_minutes": total_minutes,
    }

    return context
