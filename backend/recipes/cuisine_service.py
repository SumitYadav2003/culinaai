"""
Cuisine check: does a generated recipe use the ingredients that set its cuisine
apart? Worked out by code from published data, never by the AI.

Data: Ahn, Ahnert, Bagrow & Barabási (2011), "Flavor network and the principles
of food pairing", Scientific Reports 1:196 (56,498 recipes, CC BY 4.0). The
study groups cuisines into 11 regions; scripts/build_cuisine_signatures.py turns
its recipes into each region's signature ingredients (the paper's "relative
prevalence") and tests the lists on held-out recipes. See recipes/data/README.md.

What it measures, honestly: typical ingredients, at region level ("Thai" is
judged as Southeast Asian). Not taste, technique or one country's cooking.
"""

import csv
import re
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
NO_CUISINE = {"", "none", "none provided", "n/a", "na", "any", "any cuisine", "no preference"}

# Cuisine names on the site -> the study's regions. The study's own groupings
# (Supplementary Table S2) are listed first for each region; the extra names
# are CulinaAI's mapping of close variants.
REGION_NAMES = {
    "NorthAmerican": ("North American", ["american", "canadian", "cajun", "creole", "soul food", "southern us",
                                         "southwestern", "usa", "us"]),
    "SouthernEuropean": ("Southern European", ["greek", "italian", "mediterranean", "spanish", "portuguese"]),
    "LatinAmerican": ("Latin American", ["caribbean", "central american", "south american", "mexican", "brazilian",
                                         "peruvian", "argentinian", "argentine", "colombian", "cuban", "jamaican",
                                         "latin american", "latin"]),
    "WesternEuropean": ("Western European", ["french", "austrian", "belgian", "english", "scottish", "dutch", "swiss",
                                             "german", "irish", "british", "welsh", "western european"]),
    "EastAsian": ("East Asian", ["korean", "chinese", "japanese", "east asian", "cantonese", "sichuan", "szechuan"]),
    "MiddleEastern": ("Middle Eastern", ["iranian", "persian", "jewish", "lebanese", "turkish", "middle eastern",
                                         "israeli", "syrian", "arabic", "arab"]),
    "SouthAsian": ("South Asian", ["bangladeshi", "bangladeshian", "indian", "pakistani", "south asian", "punjabi",
                                   "bengali", "gujarati", "south indian", "north indian"]),
    "SoutheastAsian": ("Southeast Asian", ["indonesian", "malaysian", "filipino", "thai", "vietnamese",
                                           "southeast asian", "south east asian"]),
    "EasternEuropean": ("Eastern European", ["eastern european", "russian", "polish", "ukrainian", "hungarian"]),
    "African": ("African", ["moroccan", "east african", "north african", "south african", "west african", "african",
                            "ethiopian", "nigerian", "egyptian", "tunisian", "ghanaian", "kenyan"]),
    "NorthernEuropean": ("Northern European", ["scandinavian", "swedish", "norwegian", "danish", "finnish", "nordic",
                                               "northern european"]),
}

# How the study's ingredient words are found in a recipe's ingredient names.
# Checked in this order; each recipe ingredient counts for one signature only.
# (pattern, study ingredient, words shown to the user)
INGREDIENT_RULES = [
    (r"\bpeanut butter|\bbutter ?beans?|\bbutternut", None, ""),
    (r"\bcoconut", "coconut", "coconut or coconut milk"),
    (r"\b(?:almond|oat|soy|soya|rice) milk", None, ""),
    (r"\bcream cheese", None, ""),
    (r"\bfish sauce|\bfish\b|\bcod\b|\bsalmon|\btuna|\bhaddock|\bmackerel|\banchov|\bsardine|\btilapia|\bsea ?bass"
     r"|\btrout|\bpollock|\bhake|\bbonito|\bdashi", "fish", "fish or fish sauce"),
    (r"\bsoy sauce|\btamari|\bshoyu|\blight soy|\bdark soy|\bsoy\b", "soy_sauce", "soy sauce"),
    (r"\btofu|\bmiso|\bedamame|\bsoya? ?beans?|\btempeh", "soybean", "tofu, miso or soybeans"),
    (r"\bsesame oil", "sesame_oil", "sesame oil"),
    (r"\bsesame", "roasted_sesame_seed", "sesame seeds"),
    (r"\bsake\b|\bmirin|\brice wine|\bshaoxing", "sake", "sake or mirin"),
    (r"\brice vinegar|\brice flour", None, ""),
    (r"\brice\b|\bbasmati|\bjasmine", "rice", "rice"),
    (r"\bspring onion|\bscallion|\bgreen onion", "scallion", "spring onions"),
    (r"\bshiitake", "shiitake", "shiitake mushrooms"),
    (r"\blemongrass|\blemon grass", "lemongrass", "lemongrass"),
    (r"\blime leaves|\blime leaf", None, ""),
    (r"\blime", "lime_juice", "lime"),
    (r"\blemon juice|\bjuice of (?:a |half a |\d )?lemon", "lemon_juice", "lemon juice"),
    (r"\blemon", "lemon", "lemon"),
    (r"\bground coriander|\bcoriander (?:seed|powder)|\bdhania powder", "coriander", "ground coriander"),
    (r"\bcoriander|\bcilantro|\bdhania", "cilantro", "fresh coriander (cilantro)"),
    (r"\bcumin|\bjeera", "cumin", "cumin"),
    (r"\bturmeric|\bhaldi", "turmeric", "turmeric"),
    (r"\bfenugreek|\bmethi", "fenugreek", "fenugreek"),
    (r"\bcardamom|\belaichi", "cardamom", "cardamom"),
    (r"\bcinnamon", "cinnamon", "cinnamon"),
    (r"\bginger", "ginger", "ginger"),
    (r"\bgarlic", "garlic", "garlic"),
    (r"\bcurry paste|\bred pepper flakes|\bchil+i|\bchile|\bcayenne|\bjalape|\bsriracha|\bgochujang|\bserrano|\bscotch bonnet"
     r"|\bbird'?s eye", "cayenne", "chilli"),
    (r"\bbell pepper|\bcapsicum|\b(?:red|green|yellow|orange) peppers?\b|\bsweet peppers?", "bell_pepper",
     "peppers (capsicum)"),
    (r"\bonion", "onion", "onion"),
    (r"\bolive oil", "olive_oil", "olive oil"),
    (r"\bparmesan|\bparmigiano|\bgrana padano|\bpecorino", "parmesan_cheese", "parmesan"),
    (r"\bmozzarella", "mozzarella_cheese", "mozzarella"),
    (r"\bcheddar|\bmonterey jack|\bcolby", "cheddar_cheese", "cheddar"),
    (r"\bcheese|\bfeta|\bricotta|\bhalloumi|\bgruyere|\bgoat'?s cheese", "cheese", "cheese"),
    (r"\bpasta|\bspaghetti|\bpenne|\bfusilli|\blinguine|\bmacaroni|\btagliatelle|\blasagn|\brigatoni|\bfarfalle"
     r"|\borzo|\bravioli|\btortellini|\bpappardelle|\bconchiglie", "macaroni", "pasta"),
    (r"\btomato|\bpassata", "tomato", "tomato"),
    (r"\bbasil", "basil", "basil"),
    (r"\boregano", "oregano", "oregano"),
    (r"\bparsley", "parsley", "parsley"),
    (r"\brosemary", "rosemary", "rosemary"),
    (r"\bthyme", "thyme", "thyme"),
    (r"\bdill\b", "dill", "dill"),
    (r"\bmint", "mint", "mint"),
    (r"\bwhite wine", "white_wine", "white wine"),
    (r"\bcornflour|\bcornstarch|\bcorn starch", None, ""),
    (r"\bsweetcorn|\bcorn\b|\bcorn tortilla|\bmasa\b|\bmaize", "corn", "corn or sweetcorn"),
    (r"\bavocado|\bguacamole", "avocado", "avocado"),
    (r"\byog(?:h)?urt|\bcurd\b|\bdahi", "yogurt", "yogurt"),
    (r"\blamb\b|\bmutton", "lamb", "lamb"),
    (r"\bchickpea|\bgarbanzo|\bchana", "chickpea", "chickpeas"),
    (r"\bwalnut", "walnut", "walnuts"),
    (r"\balmond", "almond", "almonds"),
    (r"\bbuttermilk|\bmilk", "milk", "milk"),
    (r"\bghee|\bbutter", "butter", "butter"),
    (r"\bice cream", None, ""),
    (r"\bcream|\bcreme fraiche|\bcrème fraîche", "cream", "cream"),
    (r"\begg", "egg", "eggs"),
    (r"\brye", "rye_flour", "rye flour"),
    (r"\b(?:rice|gram|chickpea|almond|coconut) flour", None, ""),
    (r"\bflour|\bwheat|\bsemolina", "wheat", "flour"),
    (r"\bvanilla", "vanilla", "vanilla"),
    (r"\bmustard", "mustard", "mustard"),
    (r"\bmolasses|\btreacle", "cane_molasses", "molasses or treacle"),
    (r"\bcocoa|\bchocolate", "cocoa", "cocoa or chocolate"),
    (r"\bsweet potato", None, ""),
    (r"\bpotato", "potato", "potatoes"),
    (r"\bsauerkraut", "sauerkraut", "sauerkraut"),
    (r"\bcabbage", "cabbage", "cabbage"),
    (r"\byeast", "yeast", "yeast"),
]
COMPILED_RULES = [(re.compile(pattern), name, words) for pattern, name, words in INGREDIENT_RULES]
WORDS = {name: words for _, name, words in INGREDIENT_RULES if name}

# Signature ingredients the user can't have, by diet or allergy wording.
RESTRICTIONS = [
    (r"vegan|vegetarian|eggetarian|plant[- ]based", {"fish", "lamb"}),
    (r"pescatarian", {"lamb"}),
    (r"fish|seafood", {"fish"}),
    (r"vegan|dairy|lactose|milk", {"butter", "milk", "cream", "cheese", "parmesan_cheese", "mozzarella_cheese",
                                   "cheddar_cheese", "yogurt"}),
    (r"vegan|\begg(?!etarian)", {"egg"}),
    (r"gluten|coeliac|celiac|wheat", {"wheat", "rye_flour", "macaroni"}),
    (r"\bnut|walnut|almond", {"walnut", "almond"}),
    (r"sesame", {"sesame_oil", "roasted_sesame_seed"}),
    (r"\bsoy|soya", {"soy_sauce", "soybean"}),
    (r"alcohol|halal", {"white_wine", "sake"}),
    (r"mustard", {"mustard"}),
    (r"coconut", {"coconut"}),
]


@lru_cache(maxsize=1)
def load_regions():
    """{region: {"name", "recipes", "checked", "own", "others", "signature": [study ingredients]}}"""
    regions = {}
    with open(DATA_DIR / "cuisine_regions.csv", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            regions[row["region"]] = {
                "name": REGION_NAMES[row["region"]][0],
                "recipes": int(row["recipes"]),
                "checked": row["checked"] == "yes",
                "own": float(row["heldout_own_2plus"]),
                "others": float(row["heldout_others_2plus"]),
                # How many signature ingredients real recipes of the region use: most use low to high.
                "real_low": int(row["real_low"]),
                "real_typical": int(row["real_typical"]),
                "real_high": int(row["real_high"]),
                "signature": [],
            }
    with open(DATA_DIR / "cuisine_signatures.csv", newline="", encoding="utf-8") as handle:
        for row in sorted(csv.DictReader(handle), key=lambda r: (r["region"], int(r["rank"]))):
            regions[row["region"]]["signature"].append(row["ingredient"])
    return regions


def region_for(cuisine):
    """The study's region for a cuisine name on the site, or None."""
    text = " " + re.sub(r"[^a-z ]+", " ", str(cuisine or "").lower()).strip() + " "
    best = None
    for region, (_, names) in REGION_NAMES.items():
        for name in names:
            if f" {name} " in text and (best is None or len(name) > best[1]):
                best = (region, len(name))
    return best[0] if best else None


def study_ingredient(name):
    """The study's word for one recipe ingredient name, or None."""
    text = str(name or "").lower()
    for pattern, ingredient, _ in COMPILED_RULES:
        if pattern.search(text):
            return ingredient
    return None


def ingredients_section(recipe_text):
    """Ingredient lines from the recipe text, for when the structured list isn't available."""
    match = re.search(r"INGREDIENTS[^\n]*:\s*(.*?)(?:\n[A-Z][A-Z &/]+:\s*\n|\Z)", recipe_text or "", re.DOTALL)
    if not match:
        return []
    return [line.strip(" -*•\t") for line in match.group(1).splitlines() if line.strip(" -*•\t")]


def restricted_for(preferences):
    words = " ".join(
        [str(item) for item in (preferences.get("diet_preferences") or [])]
        + [str(preferences.get("allergies") or "")]
    ).lower()
    if not words.strip() or words.strip() in NO_CUISINE:
        return set()
    blocked = set()
    for pattern, names in RESTRICTIONS:
        if re.search(pattern, words):
            blocked |= names
    # Anything the user named to avoid ("no tomato, mushrooms") is left out too.
    allergy_text = str(preferences.get("allergies") or "").lower()
    for part in re.split(r"[,;/\n]| and | or ", allergy_text):
        name = study_ingredient(part)
        if name:
            blocked.add(name)
    return blocked


def range_words(low, high):
    return f"most use {low}" if low == high else f"most use {low} to {high}"


def cuisine_check(preferences, ingredient_names):
    """
    The cuisine check for one recipe, as plain values for the page, or None
    when the user chose no cuisine.
    """
    cuisine = str((preferences or {}).get("cuisine") or "").strip()
    if cuisine.lower() in NO_CUISINE:
        return None

    region = region_for(cuisine)
    if not region:
        return {
            "available": False,
            "cuisine": cuisine,
            "text": f"There's no published ingredient data for {cuisine} cooking yet, so this isn't checked.",
        }

    info = load_regions()[region]
    base = {"cuisine": cuisine, "region": region, "region_name": info["name"], "recipes": info["recipes"]}

    if not info["checked"]:
        everyday = ", ".join(WORDS[name] for name in info["signature"][:4])
        return dict(base, available=False, text=(
            f"In the study, {info['name']} recipes mostly share everyday ingredients ({everyday}), "
            "so their ingredients can't reliably tell the cuisine apart. This isn't checked."
        ))

    blocked = restricted_for(preferences)
    usable = [name for name in info["signature"] if name not in blocked]
    excluded = [WORDS[name] for name in info["signature"] if name in blocked]
    in_recipe = {study_ingredient(name) for name in ingredient_names}
    found = [name for name in usable if name in in_recipe]
    missing = [name for name in usable if name not in in_recipe]

    # Compared with real recipes of the region, not with "12 out of 12": no real dish uses them all.
    low, usual, high = info["real_low"], info["real_typical"], info["real_high"]
    count = len(found)
    if count > high:
        level, headline = "very", f"Very typical of {cuisine} cooking"
    elif count >= low:
        level, headline = "typical", f"Typical of {cuisine} cooking"
    else:
        level, headline = "less", f"Less typical of {cuisine} cooking"

    uses = f"uses {count or 'none'} of its signature ingredients"
    if found:
        uses += " (" + ", ".join(WORDS[name] for name in found) + ")"
    region = info["name"]
    spread = range_words(low, high)
    if level == "very":
        comparison = f"more than most {region} recipes in the study ({spread})"
    elif count == usual:
        comparison = f"the same as a typical {region} recipe in the study ({spread})"
    elif level == "typical":
        comparison = f"in line with {region} recipes in the study ({spread})"
    else:
        comparison = f"fewer than most {region} recipes in the study ({spread})"
    text = f"{headline}: {uses}, {comparison}."

    # Sent back to the AI only when it's below the usual range and uses at most one.
    retry = level == "less" and count <= 1 and len(missing) >= 2
    if retry or (level == "less" and missing):
        text += " Typical ones include " + ", ".join(WORDS[name] for name in missing[:3]) + "."

    return dict(
        base,
        available=True,
        level=level,
        found=[WORDS[name] for name in found],
        missing=[WORDS[name] for name in missing],
        usable=len(usable),
        excluded=excluded,
        real_low=low,
        real_typical=usual,
        real_high=high,
        text=text,
        retry=retry,
    )


def cuisine_correction(insights):
    """The note sent back to the AI when the recipe uses fewer of its cuisine's typical ingredients than real recipes do."""
    check = (insights or {}).get("cuisine") or {}
    if not check.get("retry"):
        return ""
    suggestions = ", ".join(check["missing"][:5])
    return (
        f"The user asked for {check['cuisine']} food, but the recipe uses few ingredients typical of that cuisine. "
        f"Where they suit the dish and the user's ingredients, allergies and diet, use some of: {suggestions}."
    )


def recipe_cuisine_check(preferences, insights, recipe_text):
    """Runs the check on the structured ingredient list, or on the recipe text if there isn't one."""
    names = [item.get("name", "") for item in (insights or {}).get("ingredients") or []]
    if not names:
        names = ingredients_section(recipe_text)
    return cuisine_check(preferences, names)
