# CulinaAI benchmark evaluation

Generated 10 October 2026, 17:55. Benchmark run benchmark_2026-10-10_1752.jsonl: 2 cases.

## Benchmark cases

2 fixed cases from docs/evaluation/benchmark_cases.json, run through the real pipeline with images turned off. Median time per recipe 37.05s (longest 38.3s).

| Case | Attempts | Score | Time | Cuisine | Everyday healthy | Allergy |
|---|---|---|---|---|---|---|
| thai-everyday | 3 | 100 | 38.3s | Very typical | not met: salt 2.1 g (max 1.8), mostly salt | - |
| chinese-everyday | 3 | 100 | 35.8s | Typical | met | - |

## 1. Recipe quality

Based on 2 recipes.

- Passed the quality gates on the first attempt: 2 of 2 with an attempt record (100%)
- Shown without any retry: 0 (0%)
- Average attempts per recipe: 3
- Median final quality score: 100 (target 85)
- Safe fallback recipe shown: 0, of which after an AI error: 0
- Retries asked for by code after the gates passed: Meal Style (4)
- Checks that failed on some attempt: none

## 2. Safety cross-checks

These use the allergen keyword lists and the diet word lists directly on the final ingredient list, not the validation engine's own report, so they are a second opinion.

- Recipes made for someone with allergies: 0
- Of those, a declared allergen still found in the ingredients: 0
- Of those, a bought product flagged "check the label": 0
- Vegetarian or vegan recipes: 0; with a meat, fish or animal ingredient: 0

## 3. Nutrition

- Recipes with an ingredient list: 2 of 2
- Every ingredient found in the food data: 2 (100%)
- Ingredients matched: 25 of 25 (100%)
- Most common unmatched: none
- The AI's own calorie estimate against the calculated one (2 recipes): median difference 9.3%, within 10%: 50%, within 25%: 100%

## 4. Meal style

- "Everyday healthy" asked for: 2; could be checked: 2; met: 1 (50%)

## 5. Cuisine check

- Recipes with a cuisine chosen: 2; checked against the study: 2
- Very typical 1, typical 1, less typical 0 (typical or better: 100%)
- Retries asked for by the cuisine check: 0

How well the signature ingredients tell the regions apart, on the 20% of the Ahn et al. (2011) recipes held back when the lists were made (share of recipes using 2 or more of a region's signature ingredients):

| Region | Recipes | Own recipes | Other regions | Checked |
|---|---|---|---|---|
| Southeast Asian | 457 | 88.1% | 31.8% | yes |
| East Asian | 2,512 | 82.9% | 27.7% | yes |
| Northern European | 250 | 80% | 36.1% | yes |
| Southern European | 4,180 | 71.2% | 27.7% | yes |
| South Asian | 621 | 81.2% | 38.1% | yes |
| Latin American | 2,917 | 82.2% | 42.6% | yes |
| Eastern European | 381 | 84% | 45.9% | yes |
| African | 352 | 77% | 39.6% | yes |
| Middle Eastern | 645 | 72.2% | 38% | yes |
| Western European | 2,659 | 69.5% | 36.3% | yes |
| North American | 41,524 | 54.1% | 35.2% | no |

Classic dishes (backend/recipes/data/classic_dishes.json): 13 of 13 got the expected level.

| Dish | Cuisine | Expected | Got | Signature found |
|---|---|---|---|---|
| green curry | Thai | Typical | Typical | 4 of 12 |
| pad thai | Thai | Typical | Typical | 6 of 12 |
| carbonara | Italian | Typical | Typical | 2 of 12 |
| mushroom risotto | Italian | Typical | Typical | 3 of 12 |
| chana masala | Indian | Typical | Typical | 7 of 12 |
| butter chicken | Indian | Typical | Typical | 5 of 12 |
| chicken tacos | Mexican | Very typical | Very typical | 7 of 12 |
| egg fried rice | Chinese | Typical | Typical | 5 of 12 |
| teriyaki salmon | Japanese | Very typical | Very typical | 8 of 12 |
| chicken tagine | Moroccan | Very typical | Very typical | 7 of 12 |
| greek salad | Greek | Typical | Typical | 4 of 12 |
| shepherd's pie | British | Typical | Typical | 3 of 8 |
| bolognese labelled Thai | Thai | Less typical | Less typical | 1 of 12 |

## 6. AI swap ideas (One dish, three ways)

- Recipes: 2; ideas suggested: 16; accepted by the code checks: 11 (68.8%)
- Why ideas were turned down: New ingredient not found in the food data (4), Same food as the original (1)

## Limits

- Allergy and diet cross-checks are keyword based: they catch named ingredients, not cross-contamination or every brand's recipe.
- Nutrition is only as good as the ingredient weights the AI wrote and the food data match.
- The cuisine check compares with one published dataset of online recipes (Ahn et al., 2011).
- Benchmark results change from run to run because the AI is not deterministic; compare runs, don't rely on one.
