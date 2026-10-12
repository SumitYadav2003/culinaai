"""
One-off: move CulinaAI's stylesheets from the old orange/gold/cream look to the
calmer palette (warm neutral greys, one herb-green accent). Kept in the repo so
the change can be explained and repeated.

Run from the project root, then regenerate dark mode:
    python scripts/apply_palette.py
    python scripts/generate_dark_theme.py

What it does to every stylesheet except the generated dark theme:
- Colours: near-greys, creams and browns become green-tinted greys of the same
  lightness; the orange, gold and green brand colours become the green accent
  scale; reds and blues are left alone. In rules about warnings, allergies,
  expiry or deleting, orange becomes red, because warnings are red on this site. recipe_insights.css keeps its
  orange and amber, which mean "caution" there, not brand.
- Decorative gradients become the solid colour underneath them. Gradients over
  images, fades to transparent and loading shimmers are kept.
- Large soft shadows and coloured glows become a thin 1-3 px shadow.
- Corner radius: 18 px and over becomes 12 px, 14-17 px becomes 10 px.
- Headings: weights 800-950 become 700, tight letter-spacing is relaxed, and
  ALL-CAPS labels go back to normal case.
"""

import colorsys
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSS_DIR = PROJECT_ROOT / "frontend" / "static" / "css"
# Generated, or already written in the new colours with the tokens in site.css.
SKIP = {"dark_theme_generated.css", "site.css", "recipe_page.css", "recipe_card.css", "generate_page.css", "recipe_list.css", "app_pages.css"}
SEMANTIC_WARM = {"recipe_insights.css"}  # orange there means "caution"

COLOUR = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b|rgba?\([^)]*\)")
DECLARATION = re.compile(r"(?P<prop>-?[a-zA-Z-]+)(?P<sep>\s*:\s*)(?P<value>[^;{}]+?)(?P<end>\s*(?:!important)?\s*;)")

NEUTRAL_HUE = 120 / 360  # a hint of green in the greys
NEUTRAL_SAT = 0.07

# The green accent scale, by the lightness of the colour it replaces.
GREENS = [
    (0.20, "#173a22"),
    (0.30, "#1f4d2b"),
    (0.58, "#2d6a3e"),
    (0.72, "#4f8f5f"),
    (0.84, "#a9cdb1"),
    (0.92, "#d6e7da"),
    (1.01, "#eef5ef"),
]


def parse(text):
    text = text.lower()
    if text.startswith("#"):
        digits = text[1:]
        if len(digits) == 3:
            digits = "".join(d * 2 for d in digits)
        return tuple(int(digits[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (1.0,)
    parts = [p for p in re.split(r"[\s,/()]+", text[text.index("(") + 1:]) if p]
    try:
        rgb = tuple(float(p) / 255 for p in parts[:3])
        alpha = float(parts[3]) if len(parts) > 3 else 1.0
    except ValueError:
        return None
    return rgb + (alpha,)


def fmt(rgb, alpha):
    r, g, b = (round(max(0, min(1, v)) * 255) for v in rgb)
    if alpha >= 0.999:
        return f"#{r:02x}{g:02x}{b:02x}"
    return f"rgba({r}, {g}, {b}, {round(alpha, 3)})"


def hex_rgb(value):
    return tuple(int(value[i:i + 2], 16) / 255 for i in (1, 3, 5))


# Warnings must stay red, so warm colours in rules about warnings become reds.
WARNING_SELECTOR = re.compile(r"warn|caution|alert|danger|error|expir|unsafe|risk|allerg|delete|destructive", re.I)
REDS = [(0.30, "#7f1d1d"), (0.45, "#991b1b"), (0.62, "#dc2626"), (0.85, "#fca5a5"), (0.93, "#fee2e2"), (1.01, "#fef2f2")]


def new_colour(text, semantic_warm, warning=False):
    colour = parse(text)
    if colour is None:
        return text
    r, g, b, alpha = colour
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    degrees = hue * 360

    if light >= 0.995:
        return text  # white stays white
    if light > 0.95 and sat >= 0.3:
        # Pale tints behind warnings: pale red stays pale red, and in warning
        # rules a pale orange becomes pale red too.
        if degrees < 15 or degrees >= 330:
            return text
        if 15 <= degrees < 65 and semantic_warm:
            return text
        if 15 <= degrees < 65 and warning:
            return fmt(hex_rgb(REDS[-1][1]), alpha)
    neutral = sat < 0.3 or light < 0.14 or light > 0.95
    if neutral:
        # Very light warm tints (creams) become an almost-white grey.
        if light > 0.95:
            light = max(light, 0.965)
        return fmt(colorsys.hls_to_rgb(NEUTRAL_HUE, light, NEUTRAL_SAT if light < 0.95 else 0.12), alpha)
    if degrees < 15 or degrees >= 330:
        return text  # reds: warnings and danger
    if 180 <= degrees < 330:
        return text  # blues and purples: charts and info
    if 15 <= degrees < 65 and semantic_warm:
        return text
    if 15 <= degrees < 65 and warning:
        for limit, value in REDS:
            if light < limit:
                return fmt(hex_rgb(value), alpha)
    for limit, value in GREENS:
        if light < limit:
            return fmt(hex_rgb(value), alpha)
    return text


def colours_in(value):
    return COLOUR.findall(value)


def flatten_gradient(prop, value):
    """A decorative gradient becomes the solid colour under it."""
    if "gradient(" not in value:
        return value
    lowered = value.lower()
    if "url(" in lowered or "transparent" in lowered or "shimmer" in lowered:
        return value
    if prop == "background-image":
        return "none"
    # Several layers: the last one is at the bottom. A plain colour after the
    # last gradient is the base; otherwise use the first stop of the last gradient.
    tail = value[value.rfind(")") + 1:]
    tail_colours = colours_in(tail)
    if tail_colours:
        return tail_colours[-1]
    last_gradient = value[value.rfind("gradient("):]
    stops = colours_in(last_gradient)
    if not stops:
        return value
    # Prefer an opaque stop, so a see-through glow doesn't become the background.
    opaque = [s for s in stops if (parse(s) or (0, 0, 0, 0))[3] > 0.6]
    return (opaque or stops)[0]


def calm_shadow(value):
    if "inset" in value or value.strip() == "none":
        return value
    blurs = [float(n) for n in re.findall(r"(?:^|\s)-?\d+(?:\.\d+)?px\s+-?\d+(?:\.\d+)?px\s+(\d+(?:\.\d+)?)px", value)]
    if blurs and max(blurs) > 16:
        return "0 1px 3px rgba(28, 36, 30, 0.08)"
    if blurs and any(parse(c) and colorsys.rgb_to_hls(*parse(c)[:3])[2] > 0.3 for c in colours_in(value)):
        return "0 1px 2px rgba(28, 36, 30, 0.08)"  # coloured glow
    return value


def calm_radius(value):
    def fix(match):
        number = float(match.group(1))
        if number >= 999:
            return match.group(0)
        if number >= 18:
            return "12px"
        if number >= 14:
            return "10px"
        return match.group(0)
    return re.sub(r"(\d+(?:\.\d+)?)px", fix, value)


RULE = re.compile(r"(?P<selector>[^{}]+)\{(?P<body>[^{}]*)\}")


def convert(css, semantic_warm):
    def rule(match):
        selector, body = match.group("selector"), match.group("body")
        # Keep comments and blank lines before the selector as they are.
        cut = selector.rfind("*/") + 2 if "*/" in selector else 0
        prefix, selectors = selector[:cut], selector[cut:]
        parts = [part for part in selectors.split(",")]
        warning = [part for part in parts if WARNING_SELECTOR.search(part)]
        if not warning or "(" in selectors:
            flag = bool(warning) and len(warning) == len(parts)
            return selector + "{" + convert_block(body, semantic_warm, flag) + "}"
        if len(warning) == len(parts):
            return selector + "{" + convert_block(body, semantic_warm, True) + "}"
        # A group that mixes warnings with other things is split, so only the
        # warning selectors turn red.
        others = [part for part in parts if part not in warning]
        trailing = selectors[len(selectors.rstrip()):]
        return (
            prefix + ",".join(others).rstrip() + " {" + convert_block(body, semantic_warm, False) + "}\n\n"
            + ",".join(warning).strip() + trailing + "{" + convert_block(body, semantic_warm, True) + "}"
        )

    return RULE.sub(rule, css)


def convert_block(css, semantic_warm, warning):
    def declaration(match):
        prop = match.group("prop").lower()
        value = match.group("value")
        if prop in ("background", "background-image"):
            value = flatten_gradient(prop, value)
        if prop == "box-shadow":
            value = calm_shadow(value)
        if prop.startswith("border") and "radius" in prop:
            value = calm_radius(value)
        if prop == "font-weight" and value.strip() in ("800", "850", "900", "950"):
            value = "700"
        if prop == "letter-spacing":
            number = re.match(r"\s*(-?\d*\.?\d+)(px|em|rem)", value)
            if number:
                if number.group(2) == "px" and float(number.group(1)) < -0.6:
                    value = "-0.01em"
                elif number.group(2) in ("em", "rem") and float(number.group(1)) < -0.03:
                    value = "-0.01em"
                elif float(number.group(1)) > 0.5 and number.group(2) == "px":
                    value = "0"
                elif number.group(2) in ("em", "rem") and float(number.group(1)) > 0.04:
                    value = "0"
        if prop == "text-transform" and value.strip() == "uppercase":
            value = "none"
        if prop == "font-family" and "Segoe UI" in value:
            value = '"Libre Franklin", system-ui, -apple-system, "Segoe UI", sans-serif'
        value = COLOUR.sub(lambda m: new_colour(m.group(0), semantic_warm, warning), value)
        return f"{match.group('prop')}{match.group('sep')}{value}{match.group('end')}"

    return DECLARATION.sub(declaration, css)


def main():
    files = sorted(p for p in CSS_DIR.glob("*.css") if p.name not in SKIP)
    for path in files:
        before = path.read_text(encoding="utf-8")
        after = convert(before, path.name in SEMANTIC_WARM)
        if after != before:
            path.write_text(after, encoding="utf-8")
            print(f"updated {path.name}")


if __name__ == "__main__":
    sys.exit(main())
