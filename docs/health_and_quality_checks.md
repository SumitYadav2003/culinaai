# Health panels and quality checks

This note explains what CulinaAI shows under each recipe and how it is checked. It covers the work
added after the CO7201 dissertation, which had 8 quality gates and no nutrition engine.

## Who writes what

The AI writes the recipe text. One extra, small AI call (`recipes/structure_service.py`) reads the
finished recipe and returns JSON in a fixed schema: each ingredient with a weight in grams, the
servings, and, for a known dish, the classic version's core ingredients with a suggested reason for
each one left out.

Everything the user reads about health, cost, carbon and risk is then worked out by code:

| Panel | Code | Source |
|---|---|---|
| Calories, nutrients, traffic lights | `nutrition/services.py` | CoFID 2021, FSA front-of-pack levels |
| Health benefits | `recipes/insight_service.py` | UK nutrition claim conditions, fixed sentences |
| Everyday healthy / Treat | `recipes/insight_service.py` | No red traffic light = everyday |
| Cost and carbon per serving | `nutrition/services.py` | ONS and supermarket prices; Poore & Nemecek (2018) |
| Compared with the classic | `recipes/classic_service.py` | Missing items found by code; reasons checked by rules |
| Allergens, hidden allergens, safety | `recipes/risk_service.py` | UK 14 allergens (FSA); FSA cooking advice |

If the extra AI call fails, the recipe is still shown and the panel says nutrition could not be
worked out. Recipes made before October 2026 show "Nutrition is not available".

## Compared with the classic

Code compares the classic's core ingredients with the recipe's own list, so a missing item is never
just the AI's claim. Each missing item gets one reason:

| Reason | Decided by | Rule |
|---|---|---|
| Allergy or diet setting | Code | Item matches the user's expanded avoid terms or diet rules |
| Not in your ingredients | AI, checked | Item is not in the user's ingredient list |
| Equipment | AI, checked | Needs equipment the user didn't select |
| Time limit | AI, checked | User's limit is below the classic's usual time |
| Budget | AI, checked | User chose a low budget |
| Healthier swap | AI, checked | Names a replacement that is lower in energy, fat, saturates, sugars or salt per 100 g |
| Style choice | AI | Free text; must pass gate 9 |

A reason that fails its rule is replaced by what code can prove, and gate 10 records the failure.
Example: "lettuce left out for health" fails, because nothing replaced it and nothing got healthier.

This panel is the only place a restricted ingredient may be named, and only with the allergy
reason, which code assigns whatever the AI suggested. The allergy gate still scans the recipe text
exactly as before. Three tests in `recipes/tests/test_insights_and_gates.py` cover this.

## Hidden allergens

Products that usually contain an allergen their name doesn't mention are flagged on every recipe
("Worcestershire sauce usually contains anchovies (fish). Check the label."). The table is in
`recipes/risk_service.py`. For a user who has that allergy, most of these products are also added to
the avoid list, so the AI leaves them out and the allergy gate catches them. Plain "stock" and
sausages are alerts only, because gluten-free versions are common.

## Quality gates

Two gates were added to the 8 from the dissertation:

- **Gate 9, Health Claims (critical):** no medical or unsupported health claims ("cures", "detox",
  "boosts immunity", "superfood", disease names) in the recipe text or the classic reasons. A failure
  is a hard fail and the recipe is regenerated. Ordinary cooking words such as "prevent sticking" or
  "a sweet treat" are allowed.
- **Gate 10, Explanation Consistency (major):** every classic ingredient left out has a reason that
  passes its rule. A failure lowers the score but is not a hard fail. Not applied when there is no
  structured data.

Weights now add to 100 as follows. Ingredient match and recipe structure went from 15 to 10 each to
make room; the rest are unchanged. Scores from the 8-gate version are therefore not directly
comparable with scores from this version.

| Gate | Weight (8-gate) | Weight (10-gate) |
|---|---|---|
| Allergy Safety | 20 | 20 |
| Diet Compliance | 20 | 20 |
| Ingredient Match | 15 | 10 |
| Recipe Structure | 15 | 10 |
| Cooking Time Match | 10 | 10 |
| Equipment Compatibility | 10 | 10 |
| Difficulty Match | 5 | 5 |
| Cuisine and Nutrition Relevance | 5 | 5 |
| Health Claims | - | 5 |
| Explanation Consistency | - | 5 |

Each gate still computes its own score; `apply_gate_weight` rescales it to the weight above and keeps
the raw score in the report.

## Known limits

- Nutrition uses raw ingredient weights; cooking changes weight (water lost, oil absorbed).
- The AI supplies the gram weights. Impossible weights (0 g, over 5 kg) are dropped with a warning,
  but a plausible wrong weight would go through. The "How this was calculated" table shows every
  weight and matched food so it can be checked.
- The health benefit sentences follow UK nutrition claim conditions, which govern food marketing.
  They are used here as a recognised standard; CulinaAI is not legally bound by them.
- Allergen detection works on ingredient names and the matched food names. It is a prompt to check
  the label, not a guarantee, which the disclaimer on every recipe says.
