# Ingredient coverage check, 4 October 2026

How well does CulinaAI's ingredient matcher handle the ingredients people actually cook with, across
cuisines? This check runs a published list of common recipe ingredients through the matcher and
records, for each one, whether it matched through a hand-checked alias, matched by the word-based
guess, or did not match at all.

## Data

The 56,498 recipes and 381 ingredients from:

> Ahn, Y.-Y., Ahnert, S. E., Bagrow, J. P. and Barabási, A.-L. (2011). Flavor network and the
> principles of food pairing. *Scientific Reports*, 1, 196. https://doi.org/10.1038/srep00196

The recipe file (`srep00196-s3.csv`, Supplementary Dataset 1) is licensed CC BY-NC-SA 3.0. It is not
copied into this repository. `ingredient_coverage_2026-10-04.csv` is derived from it and is shared
under the same licence. The recipe counts were checked against the paper: 56,498 recipes, 381
distinct ingredients, 11 regions.

73% of the recipes are North American, so ranking by raw frequency would favour North American
cooking. Instead, each ingredient is ranked by its **average share of recipes across the 11 regions**
(African, East Asian, Eastern European, Latin American, Middle Eastern, North American, Northern
European, South Asian, Southeast Asian, Southern European, Western European). An ingredient used in
half of South Asian recipes ranks as high as one used in half of North American recipes.

Ingredient names are the dataset's own (e.g. "scallion", "cane molasses"), so some are not how a
UK recipe would write them.

## Results

| | Before | After |
|---|---|---|
| Top 100: matched | 90 | 93 |
| Top 100: matched to a wrong food (judged by hand) | 12 | 0 |
| Top 100: matched and priced | not measured | 78 |
| Top 200: matched | 169 | 176 |
| Top 200: matched to a wrong food (judged by hand) | 22 | 0 |
| Top 200: matched and priced | not measured | 123 |

"Wrong food" means the guess picked something a cook would not mean, for example "vanilla" matched to
vanilla ice cream, "corn" to corn-fed chicken, "cherry" to cherry tomatoes and "peach" to peach melba.
The 22 are marked in the CSV (`before_judged_wrong`). After the changes, the 60 remaining guessed
matches in the top 200 were read through by hand. None were clearly wrong; two are ambiguous and left
as they are: "coconut" (matches desiccated coconut) and "roasted beef" (matches pot-roasted flank).

## What changed

- **Two matching rules** (`nutrition/services.py`):
  - A guess must name the main food, the part of the CoFID name before the first comma. "Peach
    melba" no longer counts as a match for "peach", and "Tomatoes, cherry" not for "cherry".
  - Vague one-word names (vegetable, fruit, meat, fish, seed, root, herb, spice, seafood) are never
    guessed. They stay unmatched unless an alias says what is meant.
  - The principle: an unmatched ingredient is reported to the user; a wrong match is silently wrong.
    Some correct guesses (cayenne, pecan, shiitake) were lost by the first rule and given aliases.
- **69 aliases**, including US and dataset names (cilantro, scallion, beet, molasses), spices common
  in South Asian, East Asian and Middle Eastern cooking (fenugreek, star anise, caraway, cayenne, bay,
  tamarind paste), and seaweeds.
- **24 newly priced foods**: 17 averages of Tesco, Sainsbury's and Morrisons shelf prices (4 October
  2026), and 7 estimates whose note says what was assumed (one shop only, a marketplace seller, the
  frozen form, or the coffee label's 1.8 g per 200 ml).

## Still unmatched in the top 200 (24)

- **Too vague to guess on purpose:** fish, meat, vegetable, fruit, seed, root.
- **Not in CoFID, so no UK nutrition figure to use:** lemongrass, galangal, sake, brandy, rum,
  buttermilk, enoki mushroom, romano cheese, clam, rye bread, celery oil, rose, smoke.
- **Too broad to map safely:** beef broth, orange peel, smoked sausage, cured pork.

Some of these could come from USDA FoodData Central, as seven foods already do.

## Limits

- The dataset is from 2011 and its recipes come from three websites, mostly North American.
- "Wrong" is a judgement made by reading each match, not an automatic test.
- 53 of the matched top-200 ingredients still have no price, mostly herbs, spices, wines and fruits
  matched by guessing. The cost panel names them as "no price yet".
