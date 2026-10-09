# CulinaAI benchmark evaluation

Generated 09 October 2026, 18:04. Benchmark run benchmark_2026-10-09_1748.jsonl: 30 cases.

## Benchmark cases

30 fixed cases from docs/evaluation/benchmark_cases.json, run through the real pipeline with images turned off. Median time per recipe 18.05s (longest 69.1s).

| Case | Attempts | Score | Time | Cuisine | Everyday healthy | Allergy |
|---|---|---|---|---|---|---|
| thai-plain | 1 | 100 | 21.5s | Very typical | - | - |
| thai-everyday | 2 | 100 | 33.2s | Very typical | not checked | - |
| thai-vegetarian | 1 | 100 | 16.4s | Very typical | - | - |
| thai-allergy | 1 | 100 | 18.5s | Very typical | - | clear |
| thai-treat-protein | 1 | 100 | 19.5s | Very typical | - | - |
| italian-plain | 1 | 100 | 16.2s | Very typical | - | - |
| italian-everyday | 3 | 100 | 39.5s | Very typical | not met | - |
| italian-vegetarian | 1 | 100 | 14.6s | Very typical | - | - |
| italian-allergy | 1 | 100 | 15s | Very typical | - | clear |
| italian-treat-protein | 1 | 100 | 15.7s | Very typical | - | - |
| indian-plain | 1 | 96 | 23.3s | Very typical | - | - |
| indian-everyday | 1 | 100 | 23.3s | Very typical | met | - |
| indian-vegetarian | 1 | 96 | 19s | Typical | - | - |
| indian-allergy | 4 | 98 | 69.1s | Typical | - | clear |
| indian-treat-protein | 1 | 100 | 18.3s | Very typical | - | - |
| mexican-plain | 1 | 100 | 17.4s | Very typical | - | - |
| mexican-everyday | 1 | 100 | 15.3s | Typical | not checked | - |
| mexican-vegetarian | 1 | 100 | 15.3s | Very typical | - | - |
| mexican-allergy | 1 | 100 | 19s | Very typical | - | clear |
| mexican-treat-protein | 1 | 100 | 25.6s | Very typical | - | - |
| chinese-plain | 1 | 100 | 21.2s | Typical | - | - |
| chinese-everyday | 2 | 100 | 29.8s | Typical | met | - |
| chinese-vegetarian | 1 | 100 | 16.4s | Typical | - | - |
| chinese-allergy | 1 | 100 | 17.8s | Typical | - | clear |
| chinese-treat-protein | 1 | 100 | 15.2s | Typical | - | - |
| moroccan-plain | 1 | 100 | 17.1s | Very typical | - | - |
| moroccan-everyday | 3 | 100 | 50.8s | Very typical | not met | - |
| moroccan-vegetarian | 1 | 100 | 16.1s | Very typical | - | - |
| moroccan-allergy | 1 | 100 | 17.3s | Very typical | - | clear |
| moroccan-treat-protein | 1 | 100 | 16.4s | Very typical | - | - |

## 1. Recipe quality

Based on 30 recipes.

- Passed the quality gates on the first attempt: 29 of 30 with an attempt record (96.7%)
- Shown without any retry: 25 (83.3%)
- Average attempts per recipe: 1.3
- Median final quality score: 100 (target 85)
- Safe fallback recipe shown: 1, of which after an AI error: 0
- Checks that failed on some attempt: Allergy Safety (3), Difficulty Match (3)
- Retries asked for by code after the gates passed: Meal Style (8)

## 2. Safety cross-checks

These use the allergen keyword lists and the diet word lists directly on the final ingredient list, not the validation engine's own report, so they are a second opinion.

- Recipes made for someone with allergies: 6
- Of those, a declared allergen still found in the ingredients: 0
- Of those, a bought product flagged "check the label": 0
- Vegetarian or vegan recipes: 6; with a meat, fish or animal ingredient: 0

## 3. Nutrition

- Recipes with an ingredient list: 30 of 30
- Every ingredient found in the food data: 21 (70%)
- Ingredients matched: 383 of 423 (90.5%)
- Most common unmatched: flour tortilla (4), red chili powder (4), jasmine rice (4), chili paste (3), ginger paste (3), fish sauce (3), chinese egg noodles (2), oyster sauce (2), rice vinegar (2), gluten-free couscous (1)
- The AI's own calorie estimate against the calculated one (21 recipes): median difference 22.6%, within 10%: 4.8%, within 25%: 57.1%

## 4. Meal style

- "Everyday healthy" asked for: 6; could be checked: 4; met: 2 (50%)

## 5. Cuisine check

- Recipes with a cuisine chosen: 30; checked against the study: 30
- Very typical 22, typical 8, less typical 0 (typical or better: 100%)
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

- Recipes: 29; ideas suggested: 232; accepted by the code checks: 159 (68.5%)
- Why ideas were turned down: New ingredient not found in the food data (44), Not an ingredient of this recipe that is in the food data (28), Same food as the original (1)

## Limits

- Allergy and diet cross-checks are keyword based: they catch named ingredients, not cross-contamination or every brand's recipe.
- Nutrition is only as good as the ingredient weights the AI wrote and the food data match.
- The cuisine check compares with one published dataset of online recipes (Ahn et al., 2011).
- Benchmark results change from run to run because the AI is not deterministic; compare runs, don't rely on one.
