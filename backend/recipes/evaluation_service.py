"""
Phase 5 evaluation: the numbers behind "does CulinaAI work?".

Everything here reads what CulinaAI already stores (RecipeHistory, cooking
sessions, the cuisine data) and counts it. No AI calls. Used by
`python manage.py evaluate`, which writes the report to evaluation/results/.

Two honest rules for every figure:
- it says how many recipes or sessions it is based on, and
- a cross-check uses a different method from the thing it checks (for example,
  allergens found from the food data, not from the validation engine's own report).
"""

import csv
import re
import statistics
from collections import Counter

from .cuisine_service import DATA_DIR as CUISINE_DATA_DIR
from .cuisine_service import cuisine_check, load_regions
from .risk_service import ALLERGEN_KEYWORDS, allergens_for_user_allergies

MEAT_WORDS = [
    "chicken", "beef", "pork", "lamb", "mutton", "bacon", "ham", "sausage", "turkey", "duck", "mince",
    "chorizo", "pancetta", "salami", "prosciutto", "veal", "venison", "gelatine", "gelatin", "lard",
]
NOT_MEAT = ["plant-based", "vegetarian", "vegan", "meat-free", "meatless", "quorn", "soya mince", "veggie mince",
            "lentil", "mushroom mince", "aubergine", "eggplant"]
VEGAN_EXTRA = ALLERGEN_KEYWORDS["Milk"] + ALLERGEN_KEYWORDS["Eggs"] + ["honey"]
NOT_ANIMAL = ["coconut milk", "almond milk", "oat milk", "soy milk", "soya milk", "rice milk", "plant",
              "vegan", "dairy-free", "dairy free", "eggplant", "peanut butter", "butternut", "butter bean"]
FISH_WORDS = (ALLERGEN_KEYWORDS["Fish"] + ALLERGEN_KEYWORDS["Crustaceans"] + ALLERGEN_KEYWORDS["Molluscs"]
              + ["fish sauce", "anchovies"])


def has_word(text, word):
    return re.search(r"\b" + re.escape(word) + r"(s|es)?\b", text) is not None


def percent(part, whole):
    return round(100 * part / whole, 1) if whole else None


def history_row(entry):
    """The parts of a RecipeHistory entry the evaluation needs, as plain values."""
    return {
        "id": entry.id,
        "insights": entry.insights if isinstance(entry.insights, dict) else {},
        "attempts": entry.validation_attempts or len(entry.validation_attempt_history or []) or 1,
        "attempt_history": entry.validation_attempt_history or [],
        "quality_score": entry.quality_score,
        "allergies": entry.allergies or "",
        "diets": [str(d) for d in (entry.dietary_preferences or [])],
        "cuisine": entry.cuisine_name or "",
    }


# ---------------------------------------------------------------------------
# Recipe quality: the 10 gates, retries and the safe fallback
# ---------------------------------------------------------------------------

TARGET_SCORE = 85  # recipe_quality_engine.TARGET_VALIDATION_SCORE


def attempt_passed(step):
    """Did this attempt pass the quality gates? Older records have no "passed", so it's worked out."""
    if "passed" in step:
        return bool(step["passed"])
    return not step.get("hard_fail") and (step.get("score") or 0) >= TARGET_SCORE


def is_fallback(row):
    return any(
        step.get("fallback") or "fallback" in str(step.get("status", "")).lower() for step in row["attempt_history"]
    )


def is_error(row):
    """The AI call itself failed (no key, timeout, quota), so the safe fallback was shown."""
    return any(step.get("error") for step in row["attempt_history"])


def quality_summary(rows):
    total = len(rows)
    first_try = sum(1 for row in rows if row["attempts"] <= 1)
    # Recipes saved before the attempt history was kept can't say what happened on the first try.
    with_history = [row for row in rows if row["attempt_history"]]
    gates_first = sum(1 for row in with_history if attempt_passed(row["attempt_history"][0]))
    fallback = sum(1 for row in rows if is_fallback(row))
    failed = Counter()
    retry_for = Counter()
    objections = {}
    for row in rows:
        history = row["attempt_history"]
        for number, step in enumerate(history):
            failed.update(step.get("failed_checks") or [])
            # A request for another try only counts when another try followed.
            if number < len(history) - 1:
                retry_for.update(step.get("retry_for") or [])
            for check, details in (step.get("failed_details") or {}).items():
                words = objections.setdefault(check, Counter())
                for key, value in (details or {}).items():
                    # What was found, not what the user asked for ("user_allergies").
                    if isinstance(value, list) and not key.startswith("user"):
                        words.update(str(item) for item in value if isinstance(item, (str, int, float)))
    scores = [row["quality_score"] for row in rows if row["quality_score"] is not None]
    return {
        "recipes": total,
        "first_try": first_try,
        "first_try_pct": percent(first_try, total),
        "with_history": len(with_history),
        "gates_first": gates_first,
        "gates_first_pct": percent(gates_first, len(with_history)),
        "average_attempts": round(statistics.mean(row["attempts"] for row in rows), 2) if rows else None,
        "fallback": fallback,
        "errors": sum(1 for row in rows if is_error(row)),
        "failed_checks": failed.most_common(),
        "retry_for": retry_for.most_common(),
        "objections": {check: words.most_common(8) for check, words in sorted(objections.items()) if words},
        "median_score": statistics.median(scores) if scores else None,
    }


# ---------------------------------------------------------------------------
# Safety cross-checks (independent of the validation engine)
# ---------------------------------------------------------------------------

def ingredient_names(insights):
    return [str(item.get("name", "")).lower() for item in insights.get("ingredients") or []]


def allergy_check(row):
    """
    For a recipe made for someone with allergies: the allergens they asked to avoid
    that the allergen keywords still find in the final ingredients ("found"), and
    those only flagged as "check the label" on a bought product ("label").
    None when there were no allergies or no ingredient list.
    """
    insights = row["insights"]
    if not insights.get("available"):
        return None
    wanted_out = allergens_for_user_allergies(row["allergies"])
    if not wanted_out:
        return None
    found = set((insights.get("allergens") or {}).keys()) & wanted_out
    label = {alert.get("allergen") for alert in insights.get("hidden_allergens") or []} & wanted_out
    return {"found": sorted(found), "label": sorted(label - found)}


def contains_any(name, words, exceptions):
    if any(exception in name for exception in exceptions):
        return False
    return any(has_word(name, word) for word in words)


def diet_violations(row):
    """Ingredients that break a vegetarian or vegan choice, by keyword on the final ingredient list."""
    insights = row["insights"]
    diets = " ".join(row["diets"]).lower()
    if not insights.get("available") or not re.search(r"vegetarian|vegan", diets):
        return None
    problems = []
    for name in ingredient_names(insights):
        if contains_any(name, MEAT_WORDS + FISH_WORDS, NOT_MEAT + NOT_ANIMAL):
            problems.append(name)
        elif "vegan" in diets and contains_any(name, VEGAN_EXTRA, NOT_ANIMAL):
            problems.append(name)
    return problems


def safety_summary(rows):
    allergy_checked = [(row, allergy_check(row)) for row in rows]
    allergy_checked = [(row, result) for row, result in allergy_checked if result is not None]
    diet_checked = [(row, diet_violations(row)) for row in rows]
    diet_checked = [(row, found) for row, found in diet_checked if found is not None]
    return {
        "allergy_recipes": len(allergy_checked),
        "allergy_violations": [
            {"id": row["id"], "allergies": row["allergies"], "found": result["found"], "fallback": is_fallback(row)}
            for row, result in allergy_checked if result["found"]
        ],
        "allergy_label_checks": [
            {"id": row["id"], "allergies": row["allergies"], "label": result["label"]}
            for row, result in allergy_checked if result["label"]
        ],
        "diet_recipes": len(diet_checked),
        "diet_violations": [
            {"id": row["id"], "diets": row["diets"], "found": found} for row, found in diet_checked if found
        ],
    }


# ---------------------------------------------------------------------------
# Nutrition: how much was matched, and how far the AI's own calorie guess is
# ---------------------------------------------------------------------------

def nutrition_summary(rows):
    available = [row for row in rows if row["insights"].get("available")]
    complete = [row for row in available if (row["insights"].get("nutrition") or {}).get("is_complete")]
    matched = sum(len((row["insights"].get("nutrition") or {}).get("matched") or []) for row in available)
    unmatched_names = Counter()
    for row in available:
        unmatched_names.update(str(name).lower() for name in (row["insights"].get("nutrition") or {}).get("unmatched") or [])
    unmatched = sum(unmatched_names.values())

    differences = []
    for row in complete:
        insights = row["insights"]
        ai_kcal = insights.get("ai_kcal_per_serving")
        code_kcal = ((insights.get("nutrition") or {}).get("per_serving") or {}).get("energy_kcal")
        if ai_kcal and code_kcal:
            differences.append(abs(ai_kcal - code_kcal) / code_kcal * 100)

    return {
        "recipes": len(rows),
        "available": len(available),
        "complete": len(complete),
        "complete_pct": percent(len(complete), len(available)),
        "ingredients_matched": matched,
        "ingredients_unmatched": unmatched,
        "match_rate_pct": percent(matched, matched + unmatched),
        "top_unmatched": unmatched_names.most_common(10),
        "ai_kcal_compared": len(differences),
        "ai_kcal_median_diff_pct": round(statistics.median(differences), 1) if differences else None,
        "ai_kcal_within_10_pct": percent(sum(d <= 10 for d in differences), len(differences)),
        "ai_kcal_within_25_pct": percent(sum(d <= 25 for d in differences), len(differences)),
    }


def meal_style_summary(rows):
    everyday = [row for row in rows if (row["insights"].get("meal_style") or {}).get("chosen") == "everyday"]
    judged = [row for row in everyday if row["insights"]["meal_style"].get("met") is not None]
    met = sum(1 for row in judged if row["insights"]["meal_style"]["met"])
    return {"asked": len(everyday), "judged": len(judged), "met": met, "met_pct": percent(met, len(judged))}


# ---------------------------------------------------------------------------
# AI swap ideas and the cuisine check
# ---------------------------------------------------------------------------

def swaps_summary(rows):
    records = [row["insights"].get("ai_swaps") for row in rows]
    records = [record for record in records if isinstance(record, dict) and record.get("available")]
    suggested = sum(record.get("suggested", 0) for record in records)
    accepted = sum(record.get("accepted", 0) for record in records)
    reasons = Counter(item.get("reason", "") for record in records for item in record.get("rejected") or [])
    return {
        "recipes": len(records),
        "suggested": suggested,
        "accepted": accepted,
        "accepted_pct": percent(accepted, suggested),
        "rejected_reasons": reasons.most_common(),
    }


def cuisine_summary(rows):
    checks = [row["insights"].get("cuisine") for row in rows]
    checks = [check for check in checks if isinstance(check, dict)]
    scored = [check for check in checks if check.get("available")]
    levels = Counter(check.get("level") for check in scored)
    retried = sum(1 for row in rows for step in row["attempt_history"] if "Cuisine" in (step.get("retry_for") or []))
    return {
        "with_cuisine": len(checks),
        "scored": len(scored),
        "levels": {level: levels.get(level, 0) for level in ("very", "typical", "less")},
        "typical_or_better_pct": percent(levels.get("very", 0) + levels.get("typical", 0), len(scored)),
        "retries": retried,
    }


def cuisine_data_summary():
    """The held-out test of the signature lists, and the classic dishes, from the stored data."""
    import json

    regions = load_regions()
    with open(CUISINE_DATA_DIR / "cuisine_regions.csv", newline="", encoding="utf-8") as handle:
        stored = {row["region"]: row for row in csv.DictReader(handle)}
    table = [
        {
            "region": info["name"],
            "recipes": info["recipes"],
            "own": round(float(stored[key]["heldout_own_2plus"]) * 100, 1),
            "others": round(float(stored[key]["heldout_others_2plus"]) * 100, 1),
            "checked": info["checked"],
        }
        for key, info in sorted(regions.items(), key=lambda pair: -float(stored[pair[0]]["gap"]))
    ]
    with open(CUISINE_DATA_DIR / "classic_dishes.json", encoding="utf-8") as handle:
        dishes = json.load(handle)["dishes"]
    results = []
    for dish in dishes:
        check = cuisine_check({"cuisine": dish["cuisine"]}, dish["ingredients"])
        results.append({
            "dish": dish["dish"], "cuisine": dish["cuisine"], "expected": dish["expected"],
            "level": check["level"], "found": len(check["found"]), "usable": check["usable"],
            "retry": check["retry"],
        })
    return {"regions": table, "dishes": results,
            "dishes_as_expected": sum(1 for result in results if result["level"] == result["expected"])}


# ---------------------------------------------------------------------------
# Cooking mode: sessions, trouble and the adjusted timers
# ---------------------------------------------------------------------------

TROUBLE_WORDS = {"longer": "took longer", "unclear": "instructions unclear", "technique": "tricky technique"}
OUTCOME_WORDS = {"great": "turned out great", "ok": "it was OK", "bad": "didn't go well"}


def cooking_summary(sessions, records):
    """
    sessions: CookingSession objects; records: CookingStepRecord objects of those sessions.
    Compares sessions with adjusted timers against the rest (small samples: reported, not claimed).
    """
    by_session = {}
    for record in records:
        by_session.setdefault(record.session_id, []).append(record)

    def group(selected):
        steps = [record for session in selected for record in by_session.get(session.id, [])]
        completed = [record for record in steps if record.completed]
        answered = [record for record in steps if record.trouble or record.went_fine]
        trouble = [record for record in steps if record.trouble]
        return {
            "sessions": len(selected),
            "finished_pct": percent(sum(1 for session in selected if session.finished), len(selected)),
            "steps_completed": len(completed),
            "steps_answered": len(answered),
            "trouble_pct_of_answered": percent(len(trouble), len(answered)),
            "outcomes": dict(Counter(OUTCOME_WORDS.get(session.outcome, session.outcome)
                                     for session in selected if session.outcome)),
        }

    # Sessions where nothing was recorded on any step (cooking mode opened, a timer started) are counted
    # but left out of the comparison.
    all_sessions = list(sessions)
    sessions = [session for session in all_sessions if by_session.get(session.id)]
    trouble_reasons = Counter(TROUBLE_WORDS.get(record.trouble, record.trouble) for record in records if record.trouble)
    return {
        "opened": len(all_sessions),
        "all": group(sessions),
        "voice_sessions": sum(1 for session in all_sessions if session.voice_used),
        "with_adjusted_timers": group([session for session in sessions if session.timers_adjusted]),
        "without_adjusted_timers": group([session for session in sessions if not session.timers_adjusted]),
        "trouble_reasons": trouble_reasons.most_common(),
        "notes": sum(1 for record in records if record.note),
    }


# ---------------------------------------------------------------------------
# User study: System Usability Scale (Brooke, 1996) and the feature questions
# ---------------------------------------------------------------------------

SUS_QUESTIONS = [f"sus{number}" for number in range(1, 11)]


def sus_score(answers):
    """
    The standard SUS score (0-100) from ten answers on a 1-5 scale. Odd items
    count (answer - 1), even items (5 - answer); the sum is multiplied by 2.5.
    Returns None if any answer is missing or outside 1-5.
    """
    values = []
    for number, key in enumerate(SUS_QUESTIONS, start=1):
        try:
            value = int(str(answers.get(key, "")).strip())
        except ValueError:
            return None
        if not 1 <= value <= 5:
            return None
        values.append(value - 1 if number % 2 else 5 - value)
    return sum(values) * 2.5


def sus_grade(score):
    """
    The adjective for a mean SUS score, using the means Bangor, Kortum & Miller (2009)
    found for each word (excellent 85.5, good 71.4, OK 50.9, poor 35.7).
    """
    if score is None:
        return ""
    for floor, word in ((85.5, "excellent"), (71.4, "good"), (50.9, "OK"), (35.7, "poor")):
        if score >= floor:
            return word
    return "awful"


def sus_against_average(score):
    """SUS scores are usually compared with 68, the average across many studies."""
    if score is None:
        return ""
    if score == 68:
        return "the same as the usual average of 68"
    return f"{'above' if score > 68 else 'below'} the usual average of 68"


# The CulinaAI questions in questionnaire.md, for the report.
FEATURE_QUESTIONS = {
    "f_recipe": "The recipe is one I would actually cook",
    "f_preferences": "The recipe followed what I asked for",
    "f_trust": "I trusted the allergy and diet checks",
    "f_nutrition": "Nutrition, cost and carbon were easy to understand",
    "f_cuisine": "The cuisine note matched my sense of the dish",
    "f_cooking_mode": "Cooking mode made the recipe easier to follow",
    "f_voice": "The voice assistant understood me",
    "f_voice_natural": "Talking to it felt natural",
    "f_timers": "The step timers were about right",
    "f_step_check": "Being asked how each step went was useful",
}


def whole_number(value):
    try:
        return int(str(value or "0").strip() or 0)
    except ValueError:
        return 0


def study_summary(rows):
    """rows: dicts from the responses CSV (evaluation/user_study/responses_template.csv)."""
    scores = [score for score in (sus_score(row) for row in rows) if score is not None]
    feature_keys = list(dict.fromkeys(key for row in rows for key in row if key and key.startswith("f_")))
    features = {}
    for key in feature_keys:
        values = []
        for row in rows:
            try:
                values.append(int(str(row.get(key, "")).strip()))
            except ValueError:
                continue
        if values:
            features[key] = {"answers": len(values), "mean": round(statistics.mean(values), 2)}
    voice_tried = sum(whole_number(row.get("voice_commands_tried")) for row in rows)
    voice_ok = sum(whole_number(row.get("voice_commands_understood")) for row in rows)
    mean = round(statistics.mean(scores), 1) if scores else None
    return {
        "participants": len(rows),
        "sus_scores": len(scores),
        "sus_mean": mean,
        "sus_sd": round(statistics.stdev(scores), 1) if len(scores) > 1 else None,
        "sus_grade": sus_grade(mean),
        "features": features,
        "voice_tried": voice_tried,
        "voice_understood": voice_ok,
        "voice_pct": percent(voice_ok, voice_tried),
    }


# ---------------------------------------------------------------------------
# The report (Markdown), as written by `python manage.py evaluate`
# ---------------------------------------------------------------------------

LEVEL_WORDS = {"very": "Very typical", "typical": "Typical", "less": "Less typical"}


def show(value, suffix=""):
    return "n/a" if value is None else f"{value:g}{suffix}" if isinstance(value, (int, float)) else str(value)


def counts_text(pairs):
    return ", ".join(f"{name} ({count})" for name, count in pairs) or "none"


def table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def benchmark_table(lines, rows_by_id):
    """One row per benchmark case: how it went and what the checks said."""
    out = []
    for line in lines:
        row = rows_by_id.get(line.get("history_id"))
        if not row:
            out.append([line["case"], "-", "-", "-", "-", "-", line.get("problem", "not found")])
            continue
        insights = row["insights"]
        cuisine = insights.get("cuisine") or {}
        style = insights.get("meal_style") or {}
        allergy = allergy_check(row)
        out.append([
            line["case"],
            row["attempts"],
            show(row["quality_score"]),
            show(line.get("seconds"), "s"),
            LEVEL_WORDS.get(cuisine.get("level"), "not checked"),
            {True: "met", False: "not met", None: "not checked"}[style.get("met")] if style.get("chosen") == "everyday"
            else "-",
            "-" if allergy is None else ("FOUND: " + ", ".join(allergy["found"]) if allergy["found"] else "clear"),
        ])
    return table(["Case", "Attempts", "Score", "Time", "Cuisine", "Everyday healthy", "Allergy"], out)


def build_report(*, title, scope, rows, sessions=None, records=None, benchmark_lines=None, study_rows=None,
                 generated_at=""):
    quality = quality_summary(rows)
    safety = safety_summary(rows)
    nutrition = nutrition_summary(rows)
    style = meal_style_summary(rows)
    swaps = swaps_summary(rows)
    cuisine = cuisine_summary(rows)
    data = cuisine_data_summary()
    parts = [f"# {title}", "", f"Generated {generated_at}. {scope}", ""]

    if benchmark_lines:
        seconds = [line["seconds"] for line in benchmark_lines if line.get("seconds") is not None]
        parts += [
            "## Benchmark cases", "",
            f"{len(benchmark_lines)} fixed cases from docs/evaluation/benchmark_cases.json, run through the real "
            "pipeline with images turned off. "
            + (f"Median time per recipe {statistics.median(seconds):g}s (longest {max(seconds):g}s)." if seconds else ""),
            "",
            benchmark_table(benchmark_lines, {row["id"]: row for row in rows}),
            "",
        ]

    parts += [
        "## 1. Recipe quality", "",
        f"Based on {quality['recipes']} recipes.", "",
        f"- Passed the quality gates on the first attempt: {quality['gates_first']} of {quality['with_history']} "
        f"with an attempt record ({show(quality['gates_first_pct'], '%')})",
        f"- Shown without any retry: {quality['first_try']} ({show(quality['first_try_pct'], '%')})",
        f"- Average attempts per recipe: {show(quality['average_attempts'])}",
        f"- Median final quality score: {show(quality['median_score'])} (target 85)",
        f"- Safe fallback recipe shown: {quality['fallback']}, of which after an AI error: {quality['errors']}",
        f"- Retries asked for by code after the gates passed: {counts_text(quality['retry_for'])}",
        f"- Checks that failed on some attempt: {counts_text(quality['failed_checks'])}",
    ]
    for check, words in quality["objections"].items():
        parts.append(f"  - {check} objected to: {counts_text(words)}")
    parts += [
        "",
        "## 2. Safety cross-checks", "",
        "These use the allergen keyword lists and the diet word lists directly on the final ingredient list, "
        "not the validation engine's own report, so they are a second opinion.", "",
        f"- Recipes made for someone with allergies: {safety['allergy_recipes']}",
        f"- Of those, a declared allergen still found in the ingredients: {len(safety['allergy_violations'])}",
    ]
    for item in safety["allergy_violations"]:
        parts.append(f"  - Recipe {item['id']} (allergies: {item['allergies']}): {', '.join(item['found'])}"
                     + (" (safe fallback)" if item["fallback"] else ""))
    parts.append(f"- Of those, a bought product flagged \"check the label\": {len(safety['allergy_label_checks'])}")
    for item in safety["allergy_label_checks"]:
        parts.append(f"  - Recipe {item['id']}: {', '.join(item['label'])}")
    parts += [
        f"- Vegetarian or vegan recipes: {safety['diet_recipes']}; with a meat, fish or animal ingredient: "
        f"{len(safety['diet_violations'])}",
    ]
    for item in safety["diet_violations"]:
        parts.append(f"  - Recipe {item['id']} ({', '.join(item['diets'])}): {', '.join(item['found'])}")

    parts += [
        "", "## 3. Nutrition", "",
        f"- Recipes with an ingredient list: {nutrition['available']} of {nutrition['recipes']}",
        f"- Every ingredient found in the food data: {nutrition['complete']} ({show(nutrition['complete_pct'], '%')})",
        f"- Ingredients matched: {nutrition['ingredients_matched']} of "
        f"{nutrition['ingredients_matched'] + nutrition['ingredients_unmatched']} ({show(nutrition['match_rate_pct'], '%')})",
        f"- Most common unmatched: {counts_text(nutrition['top_unmatched'])}",
        f"- The AI's own calorie estimate against the calculated one ({nutrition['ai_kcal_compared']} recipes): "
        f"median difference {show(nutrition['ai_kcal_median_diff_pct'], '%')}, within 10%: "
        f"{show(nutrition['ai_kcal_within_10_pct'], '%')}, within 25%: {show(nutrition['ai_kcal_within_25_pct'], '%')}",
        "",
        "## 4. Meal style", "",
        f"- \"Everyday healthy\" asked for: {style['asked']}; could be checked: {style['judged']}; met: {style['met']} "
        f"({show(style['met_pct'], '%')})",
        "",
        "## 5. Cuisine check", "",
        f"- Recipes with a cuisine chosen: {cuisine['with_cuisine']}; checked against the study: {cuisine['scored']}",
        f"- Very typical {cuisine['levels']['very']}, typical {cuisine['levels']['typical']}, "
        f"less typical {cuisine['levels']['less']} (typical or better: {show(cuisine['typical_or_better_pct'], '%')})",
        f"- Retries asked for by the cuisine check: {cuisine['retries']}",
        "",
        "How well the signature ingredients tell the regions apart, on the 20% of the Ahn et al. (2011) recipes "
        "held back when the lists were made (share of recipes using 2 or more of a region's signature ingredients):",
        "",
        table(["Region", "Recipes", "Own recipes", "Other regions", "Checked"],
              [[r["region"], f"{r['recipes']:,}", f"{r['own']:g}%", f"{r['others']:g}%", "yes" if r["checked"] else "no"]
               for r in data["regions"]]),
        "",
        f"Classic dishes (backend/recipes/data/classic_dishes.json): {data['dishes_as_expected']} of "
        f"{len(data['dishes'])} got the expected level.",
        "",
        table(["Dish", "Cuisine", "Expected", "Got", "Signature found"],
              [[d["dish"], d["cuisine"], LEVEL_WORDS.get(d["expected"], d["expected"]),
                LEVEL_WORDS.get(d["level"], d["level"]), f"{d['found']} of {d['usable']}"] for d in data["dishes"]]),
        "",
        "## 6. AI swap ideas (One dish, three ways)", "",
        f"- Recipes: {swaps['recipes']}; ideas suggested: {swaps['suggested']}; accepted by the code checks: "
        f"{swaps['accepted']} ({show(swaps['accepted_pct'], '%')})",
        f"- Why ideas were turned down: {counts_text(swaps['rejected_reasons'])}",
        "",
    ]

    if sessions is not None:
        cooking = cooking_summary(sessions, records or [])

        def group_line(name, group):
            return (f"| {name} | {group['sessions']} | {show(group['finished_pct'], '%')} | {group['steps_completed']} | "
                    f"{group['steps_answered']} | {show(group['trouble_pct_of_answered'], '%')} |")

        parts += [
            "## 7. Cooking mode", "",
            f"- Times cooking mode was used: {cooking['opened']}; with at least one step recorded: "
            f"{cooking['all']['sessions']}; with voice: {cooking['voice_sessions']}; "
            f"notes written by cooks: {cooking['notes']}",
            f"- Trouble reported: {counts_text(cooking['trouble_reasons'])}",
            f"- How dishes turned out: {counts_text(sorted(cooking['all']['outcomes'].items()))}",
            "",
            "| Timers | Sessions | Finished | Steps done | Steps answered | Trouble (of answered) |",
            "|---|---|---|---|---|---|",
            group_line("Adjusted to the cook", cooking["with_adjusted_timers"]),
            group_line("Not adjusted", cooking["without_adjusted_timers"]),
            group_line("All", cooking["all"]),
            "",
            "Small numbers here describe what happened; they don't show the adjustment caused any difference.",
            "",
        ]

    if study_rows is not None:
        study = study_summary(study_rows)
        parts += [
            "## 8. User study", "",
            f"- Participants: {study['participants']}; complete SUS answers: {study['sus_scores']}",
            f"- System Usability Scale: mean {show(study['sus_mean'])}"
            + (f" (SD {show(study['sus_sd'])})" if study["sus_sd"] is not None else "")
            + (f": \"{study['sus_grade']}\" on the Bangor et al. (2009) scale, "
               f"{sus_against_average(study['sus_mean'])}" if study["sus_grade"] else ""),
            f"- Voice commands understood: {study['voice_understood']} of {study['voice_tried']} "
            f"({show(study['voice_pct'], '%')})",
        ]
        if study["features"]:
            parts += ["", table(["Question", "Answers", "Mean (1-5)"],
                                [[FEATURE_QUESTIONS.get(key, key), value["answers"], value["mean"]]
                                 for key, value in study["features"].items()])]
        parts.append("")

    parts += [
        "## Limits", "",
        "- Allergy and diet cross-checks are keyword based: they catch named ingredients, not cross-contamination "
        "or every brand's recipe.",
        "- Nutrition is only as good as the ingredient weights the AI wrote and the food data match.",
        "- The cuisine check compares with one published dataset of online recipes (Ahn et al., 2011).",
        "- Benchmark results change from run to run because the AI is not deterministic; compare runs, "
        "don't rely on one.",
        "",
    ]
    return "\n".join(parts)
