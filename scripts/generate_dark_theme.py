"""
Generate CulinaAI's dark-mode colours from the light-theme CSS.

Run from the project root:
    pip install tinycss2          # development only, not needed on Render
    python scripts/generate_dark_theme.py

Why a script?
    The site has about 30,000 lines of CSS with colours written directly into
    each rule. Writing a dark version of every rule by hand would be slow and
    easy to get out of sync. This script reads each light rule and writes a
    matching dark rule, so new pages only need the script to be re-run.

What it changes (hue is kept, only lightness flips):
    - light backgrounds  -> dark surfaces   (cream -> dark brown, pale green -> dark green)
    - dark text          -> light text      (near-black -> cream, dark orange -> light orange)
    - light borders      -> subtle dark borders
    Brand colours in the middle (orange buttons, gold, green badges) are left alone.

Output:
    frontend/static/css/dark_theme_generated.css   (do not edit by hand)
Hand-written fixes live in dark_mode.css, which loads after the generated file.
"""

import colorsys
import re
from pathlib import Path

import tinycss2

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSS_DIR = PROJECT_ROOT / "frontend" / "static" / "css"
OUTPUT_FILE = CSS_DIR / "dark_theme_generated.css"
SKIP_FILES = {"dark_mode.css", "dark_theme_generated.css"}
DARK_PREFIX = 'html[data-theme="dark"]'

# Which properties hold which kind of colour.
BACKGROUND_PROPERTIES = {"background", "background-color", "background-image"}
TEXT_PROPERTIES = {"color", "fill", "-webkit-text-fill-color", "caret-color", "text-decoration-color"}
BORDER_PROPERTIES = {
    "border", "border-color", "border-top", "border-bottom", "border-left", "border-right",
    "border-top-color", "border-bottom-color", "border-left-color", "border-right-color",
    "outline", "outline-color", "stroke",
}

COLOUR_PATTERN = re.compile(
    r"#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3,4}\b|rgba?\([^)]*\)|\bwhite\b|\bblack\b"
)
VARIABLE_PATTERN = re.compile(r"var\(\s*(--[a-z0-9-]+)\s*\)")

# Warm brown hue used for neutral colours, so greys and whites match the site's brown dark theme.
WARM_HUE = 26 / 360


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def parse_colour(text):
    """Turn '#fff8ef', 'rgba(1, 2, 3, 0.5)' or 'white' into (r, g, b, alpha) with r/g/b from 0 to 1."""
    text = text.strip().lower()
    if text == "white":
        return 1.0, 1.0, 1.0, 1.0
    if text == "black":
        return 0.0, 0.0, 0.0, 1.0
    if text.startswith("#"):
        digits = text[1:]
        if len(digits) in (3, 4):
            digits = "".join(d * 2 for d in digits)
        red, green, blue = (int(digits[i:i + 2], 16) / 255 for i in (0, 2, 4))
        alpha = int(digits[6:8], 16) / 255 if len(digits) == 8 else 1.0
        return red, green, blue, alpha
    if text.startswith("rgb"):
        parts = [p for p in re.split(r"[\s,/()]+", text[text.index("(") + 1:]) if p]
        if len(parts) < 3:
            return None
        try:
            red, green, blue = (float(p) / 255 for p in parts[:3])
            alpha = float(parts[3].rstrip("%")) / (100 if parts[3].endswith("%") else 1) if len(parts) > 3 else 1.0
        except ValueError:
            return None
        return red, green, blue, alpha
    return None


def format_colour(red, green, blue, alpha):
    red, green, blue = (round(max(0.0, min(1.0, v)) * 255) for v in (red, green, blue))
    if alpha >= 0.999:
        return f"#{red:02x}{green:02x}{blue:02x}"
    return f"rgba({red}, {green}, {blue}, {round(alpha, 3)})"


def with_new_lightness(colour, new_lightness, max_saturation):
    """Keep the colour's hue, set a new lightness. Near-greys take the site's warm brown hue."""
    red, green, blue, alpha = colour
    hue, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
    if saturation < 0.12 or lightness > 0.97 or lightness < 0.03:
        hue, saturation = WARM_HUE, 0.35
    saturation = min(saturation, max_saturation)
    red, green, blue = colorsys.hls_to_rgb(hue, new_lightness, saturation)
    return format_colour(red, green, blue, alpha)


def lightness_of(colour):
    return colorsys.rgb_to_hls(*colour[:3])[1]


def saturation_of(colour):
    return colorsys.rgb_to_hls(*colour[:3])[2]


def dark_background(colour):
    """Light backgrounds become dark surfaces. White -> L 0.12, pale tints a little lighter.
    Faint see-through whites (under 35% opacity) are highlights that already work on dark, so they stay."""
    lightness = lightness_of(colour)
    if lightness < 0.72 or colour[3] < 0.35:
        return None
    return with_new_lightness(colour, 0.12 + (1 - lightness) * 0.28, max_saturation=0.45)


def light_text(colour):
    """Dark text becomes light text. Near-black -> cream, dark orange -> light orange."""
    lightness = lightness_of(colour)
    if lightness >= 0.55:
        return None
    return with_new_lightness(colour, 0.95 - lightness * 0.45, max_saturation=0.85)


def dark_border(colour):
    """Light borders become subtle borders that still show on dark surfaces."""
    if lightness_of(colour) < 0.72 or colour[3] < 0.35:
        return None
    return with_new_lightness(colour, 0.26, max_saturation=0.5)


# ---------------------------------------------------------------------------
# CSS helpers
# ---------------------------------------------------------------------------

def collect_variables(stylesheets):
    """Read colour variables such as --culina-cream from every :root rule."""
    variables = {}
    for rules in stylesheets:
        for rule in rules:
            if rule.type == "qualified-rule" and tinycss2.serialize(rule.prelude).strip() == ":root":
                for declaration in tinycss2.parse_declaration_list(rule.content, skip_whitespace=True, skip_comments=True):
                    if declaration.type == "declaration":
                        variables[f"--{declaration.lower_name.lstrip('-')}"] = tinycss2.serialize(declaration.value).strip()
    return variables


def is_strong_background(value):
    """True when a background is a saturated brand colour, e.g. an orange button. Its text stays as it is."""
    for match in COLOUR_PATTERN.finditer(value):
        colour = parse_colour(match.group())
        if colour and colour[3] > 0.6 and saturation_of(colour) > 0.45 and 0.25 < lightness_of(colour) < 0.72:
            return True
    return False


def collect_strong_selectors(stylesheets, variables):
    """Selectors whose background is a brand colour, e.g. '.culina-signup-action'.
    Text inside them (icons, hover states) keeps its light-theme colour."""
    strong = set()

    def walk(rules):
        for rule in rules:
            if rule.type == "qualified-rule":
                for declaration in tinycss2.parse_declaration_list(rule.content, skip_whitespace=True, skip_comments=True):
                    if declaration.type == "declaration" and declaration.lower_name in BACKGROUND_PROPERTIES:
                        value = VARIABLE_PATTERN.sub(lambda m: variables.get(m.group(1), m.group(0)), tinycss2.serialize(declaration.value))
                        if is_strong_background(value):
                            strong.update(s.strip() for s in tinycss2.serialize(rule.prelude).split(",") if s.strip())
            elif rule.type == "at-rule" and rule.lower_at_keyword == "media" and rule.content:
                walk(tinycss2.parse_rule_list(rule.content, skip_whitespace=True, skip_comments=True))

    for rules in stylesheets:
        walk(rules)
    return strong


def is_inside_strong(selector, strong_selectors):
    """True if the selector is a brand-coloured element (e.g. an orange button) or something inside it."""
    return any(
        selector == s or selector.startswith((s + " ", s + ":", s + ">", s + " >"))
        for s in strong_selectors
    )


def convert_value(value, converter):
    """Replace every colour in a CSS value using the converter. Returns None when nothing changed.
    A gradient that contains a brand colour is left alone, so orange-to-gold buttons stay as they are."""
    if "gradient" in value and is_strong_background(value):
        return None
    changed = False

    def replace(match):
        nonlocal changed
        colour = parse_colour(match.group())
        new_colour = converter(colour) if colour else None
        if new_colour is None:
            return match.group()
        changed = True
        return new_colour

    new_value = COLOUR_PATTERN.sub(replace, value)
    return new_value if changed else None


def dark_declarations(rule, variables, strong_selectors):
    """Return the dark-mode declarations for one rule as two lists:
    surface (backgrounds and borders) and text colours, e.g. ['background: #241a12 !important']."""
    declarations = [
        d for d in tinycss2.parse_declaration_list(rule.content, skip_whitespace=True, skip_comments=True)
        if d.type == "declaration"
    ]
    values = {}
    for declaration in declarations:
        value = tinycss2.serialize(declaration.value).strip()
        value = VARIABLE_PATTERN.sub(lambda m: variables.get(m.group(1), m.group(0)), value)
        values[declaration.lower_name] = (value, declaration.important)

    has_strong_background = any(
        is_strong_background(values[name][0]) for name in BACKGROUND_PROPERTIES if name in values
    )

    surface, text = [], []
    for name, (value, important) in values.items():
        if name in BACKGROUND_PROPERTIES:
            new_value, target = convert_value(value, dark_background), surface
        elif name in TEXT_PROPERTIES and not has_strong_background:
            new_value, target = convert_value(value, light_text), text
        elif name in BORDER_PROPERTIES:
            new_value, target = convert_value(value, dark_border), surface
        else:
            new_value = None
        if new_value:
            target.append(f"{name}: {new_value}{' !important' if important else ''}")
    return surface, text


def prefix_selectors(selector_list):
    """['.card', '.panel h2'] -> 'html[data-theme="dark"] .card, html[data-theme="dark"] .panel h2'."""
    selectors = []
    for selector in selector_list:
        if not selector or selector.startswith(":root"):
            continue
        if selector.startswith("html") or selector.startswith("body"):
            # 'body.x' -> 'html[data-theme="dark"] body.x'; 'html' itself -> the dark html
            selector = DARK_PREFIX + selector[4:] if selector.startswith("html") else f"{DARK_PREFIX} {selector}"
        else:
            selector = f"{DARK_PREFIX} {selector}"
        selectors.append(selector)
    return ",\n".join(selectors)


def convert_rules(rules, variables, strong_selectors, indent=""):
    """Walk the rules (including @media blocks) and build the dark CSS text."""
    lines = []
    for rule in rules:
        if rule.type == "qualified-rule":
            selector_list = [s.strip() for s in tinycss2.serialize(rule.prelude).split(",") if s.strip()]
            surface, text = dark_declarations(rule, variables, strong_selectors)
            # Text inside brand-coloured buttons keeps its light-theme colour.
            text_selectors = [s for s in selector_list if not is_inside_strong(s, strong_selectors)]
            blocks = [(selector_list, surface), (text_selectors, text)]
            if surface and text and text_selectors == selector_list:
                blocks = [(selector_list, surface + text)]
            for chosen, declarations in blocks:
                selectors = prefix_selectors(chosen)
                if selectors and declarations:
                    body = "".join(f"{indent}    {d};\n" for d in declarations)
                    lines.append(f"{indent}{selectors.replace(chr(10), chr(10) + indent)} {{\n{body}{indent}}}\n")
        elif rule.type == "at-rule" and rule.lower_at_keyword == "media" and rule.content:
            condition = tinycss2.serialize(rule.prelude).strip()
            if "print" in condition:
                continue  # printing always uses the light theme
            inner = convert_rules(
                tinycss2.parse_rule_list(rule.content, skip_whitespace=True, skip_comments=True),
                variables, strong_selectors, indent + "    ",
            )
            if inner:
                lines.append(f"{indent}@media {condition} {{\n{inner}{indent}}}\n")
        # @keyframes, @font-face and others are left as they are.
    return "".join(lines)


def main():
    css_files = sorted(p for p in CSS_DIR.glob("*.css") if p.name not in SKIP_FILES)
    parsed = {
        path: tinycss2.parse_stylesheet(path.read_text(encoding="utf-8"), skip_whitespace=True, skip_comments=True)
        for path in css_files
    }
    variables = collect_variables(parsed.values())
    strong_selectors = collect_strong_selectors(parsed.values(), variables)

    sections = []
    for path, rules in parsed.items():
        dark_css = convert_rules(rules, variables, strong_selectors)
        if dark_css:
            sections.append(f"/* ---------- from {path.name} ---------- */\n\n{dark_css}")

    header = (
        "/* =========================================================\n"
        "   CulinaAI dark theme: GENERATED FILE, do not edit by hand.\n"
        "   Re-create it with:  python scripts/generate_dark_theme.py\n"
        "   Hand-written fixes belong in dark_mode.css.\n"
        "   ========================================================= */\n\n"
    )
    OUTPUT_FILE.write_text(header + "\n".join(sections), encoding="utf-8")
    rule_count = sum(s.count("{") for s in sections)
    print(f"Wrote {OUTPUT_FILE.relative_to(PROJECT_ROOT)} ({rule_count} rule blocks from {len(css_files)} files)")


if __name__ == "__main__":
    main()
