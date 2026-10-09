# Cuisine data for the cuisine check

Used by `backend/recipes/cuisine_service.py`. Built by `scripts/build_cuisine_signatures.py`.

## Source

Ahn, Y.-Y., Ahnert, S. E., Bagrow, J. P. and Barabási, A.-L. (2011). *Flavor network and the
principles of food pairing.* Scientific Reports 1, 196. https://doi.org/10.1038/srep00196

Data: supplementary file `srep00196-s3.csv` (56,498 recipes from allrecipes.com,
epicurious.com and menupan.com, each with its region and ingredient list).
Dataset record: https://doi.org/10.5281/zenodo.11449657, licence CC BY 4.0.
Only the derived lists below are stored here, with this attribution.

## Regions

The study groups cuisines into 11 regions (Supplementary Table S2), for example
Southeast Asian = Indonesian, Malaysian, Filipino, Thai, Vietnamese. CulinaAI maps a
cuisine chosen on the site to one of these regions (`REGION_NAMES` in
`cuisine_service.py`; the study's own groupings plus a few close variants such as
"British" for English/Scottish). So "Thai" is checked as Southeast Asian.

## Method

For each region and ingredient, the paper's relative prevalence:

    P(i, c) = share of region c's recipes that use ingredient i
    p(i, c) = P(i, c) - average P(i, c') over the other regions

A region's signature ingredients are its 12 highest p(i, c), keeping only those at
least 5 points above the other regions. Five words are too vague to identify a
cuisine and are skipped: vegetable, vegetable_oil, seed, pepper, chicken.

## Does it work? Held-out test

The lists were rebuilt from a random 80% of recipes (seed 42) and counted on the
other 20%. "2+" = share of recipes using at least 2 of the region's signature
ingredients. Other regions are averaged equally.

| Region | Recipes | Own recipes 2+ | Other regions 2+ | Gap | Checked |
|---|---:|---:|---:|---:|---|
| Southeast Asian | 457 | 88.1% | 31.8% | +56 | yes |
| East Asian | 2,512 | 82.9% | 27.7% | +55 | yes |
| Northern European | 250 | 80.0% | 36.1% | +44 | yes |
| Southern European | 4,180 | 71.2% | 27.7% | +44 | yes |
| South Asian | 621 | 81.2% | 38.1% | +43 | yes |
| Latin American | 2,917 | 82.2% | 42.6% | +40 | yes |
| Eastern European | 381 | 84.0% | 45.9% | +38 | yes |
| African | 352 | 77.0% | 39.6% | +37 | yes |
| Middle Eastern | 645 | 72.2% | 38.0% | +34 | yes |
| Western European | 2,659 | 69.5% | 36.3% | +33 | yes |
| North American | 41,524 | 54.1% | 35.2% | +19 | **no** |

A region is checked only if the gap is at least 30 points. North American recipes
mostly share everyday baking ingredients (milk, butter, vanilla, eggs), so they are
not scored; the recipe page says so.

## How many signature ingredients real recipes use

No real dish uses all 12, so a recipe is compared with real recipes of its region,
not with "12 out of 12". From all the study's recipes (`real_low`, `real_typical`,
`real_high` in `cuisine_regions.csv`: lower quartile, median, upper quartile):

| Region | Most real recipes use | A typical one uses |
|---|---|---|
| Southeast Asian | 3 to 6 | 4 |
| East Asian | 2 to 6 | 4 |
| South Asian | 2 to 7 | 5 |
| Latin American | 2 to 6 | 4 |
| African | 2 to 5 | 4 |
| Southern European | 1 to 5 | 3 |
| Eastern European | 2 to 4 | 3 |
| Northern European | 2 to 4 | 3 |
| Western European | 1 to 4 | 2 |
| Middle Eastern | 1 to 3 | 2 |
| North American (not checked) | 1 to 3 | 2 |

Pushing a recipe far above this would mean stuffing it with ingredients that don't
belong together, which makes it less authentic, not more.

## How a recipe is scored

- Recipe ingredients are matched to the study's words by `INGREDIENT_RULES` (for
  example "fish sauce" → fish, "spring onions" → scallion, "spaghetti" → macaroni,
  "Thai curry paste" → chilli, since chillies are its main ingredient).
- Signature ingredients the user can't have (diet, allergies, anything they asked
  to avoid) are left out first, so a vegan Thai dish isn't marked down for no fish sauce.
- Very typical: more than most real recipes of the region use (above the upper quartile).
  Typical: within the range most real recipes use. Less typical: below it.
- A recipe is sent back to the AI once, with missing signature ingredients as
  suggestions, only when it is below the usual range **and** uses at most one, through
  the same retry as the meal style check. A recipe that passed the quality gates is
  never replaced by one that failed them.

## Limits

- It measures typical ingredients, not taste or technique.
- Regions, not countries (Thai and Vietnamese share a list).
- The recipes are mostly from US and Korean websites (2011), so the lists reflect
  those sites' versions of each cuisine.
- Some genuine recipes use very few signature ingredients (for example about 12% of
  Southeast Asian ones use fewer than 2), so a retry can occasionally happen on a
  recipe that was fine.
- Ingredients the 2011 data has no word for (kaffir lime leaves, galangal, gochujang)
  don't count, even when they are very typical.
