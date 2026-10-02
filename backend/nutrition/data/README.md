# Nutrition data

## cofid_2021.csv

A trimmed copy of **McCance and Widdowson's Composition of Foods Integrated Dataset (CoFID) 2021**,
published by Public Health England:
https://www.gov.uk/government/publications/composition-of-foods-integrated-dataset-cofid

Contains public sector information licensed under the
[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

Only the columns CulinaAI uses are kept: energy (kcal, kJ), protein, fat, saturates, carbohydrate,
total sugars, fibre and salt, all per 100 g. It is created from the official Excel file with
`scripts/extract_cofid.py`:

- "Tr" (trace) becomes 0; "N" (no reliable figure) and blanks stay empty, never zero.
- Salt is worked out from sodium: salt (g) = sodium (mg) x 2.5 / 1000.
- Fibre is AOAC fibre (the method on UK labels). 1,055 foods have no AOAC figure, so their older
  NSP fibre figure is used instead, which tends to read lower.
- 33 foods (mostly spices and stock cubes) have no energy figure in CoFID. They count as 0 kcal,
  which matters little because they are used in small amounts.

Load it with `python manage.py load_cofid` (or everything at once with `load_food_data`).

## ingredient_aliases.csv

Hand-checked links from everyday ingredient names ("chicken breast") to the CoFID food that
represents them ("Chicken, light meat, raw"), with a note where a choice needed explaining.
Load with `python manage.py load_ingredient_aliases` (after `load_cofid`).

## usda_supplement.csv

Seven common ingredients that CoFID doesn't cover: cornflour, dry breadcrumbs, black beans (cooked),
maple syrup, chia seeds, unsweetened oat drink and dry rice noodles. Values come from
**USDA FoodData Central** (SR Legacy, and Foundation Foods for the oat drink), which is US government
data in the public domain. Each row keeps its USDA FDC ID in the food code (e.g. `USDA-169698`), and
the app labels these foods "USDA FoodData Central" so users can see they are not UK figures.

Values were read from getfoodfacts.com, which republishes USDA data by FDC ID, because the USDA API
was not reachable from the build environment. Cross-checks on a second site:

- Cornflour, breadcrumbs, rice noodles and maple syrup matched triagemethod.com exactly.
- Black beans matched recipal.com on energy, protein, fat and carbohydrate (saturates and sugars
  differed slightly).
- Chia seeds: the second site uses a newer USDA entry (490 kcal instead of 486), so it is not a
  like-for-like check. The SR Legacy entry (FDC 170554) is used here.
- Oat drink: not cross-checked. Worth confirming against the USDA site (FDC 2257046) when possible.

Converted to match CoFID:

- **Carbohydrate:** USDA reports carbohydrate "by difference", which includes fibre. CoFID does not.
  So `carbohydrate_g` = USDA carbohydrate minus fibre (the original USDA figure is kept in
  `usda_carbohydrate_by_difference_g`). For chia seeds that is 42.1 - 34.4 = 7.7 g.
- **Salt** = sodium (mg) x 2.5 / 1000, and **kJ** = kcal x 4.184.
- **Energy** is kept as USDA states it. USDA and UK methods credit fibre slightly differently, so
  energy for very high-fibre foods (chia) may differ a little from a UK label.

Load everything (CoFID, this supplement, aliases) with `python manage.py load_food_data`.

## carbon_poore_nemecek_2018.csv

Greenhouse gas emissions for 43 food categories, in kg CO2-equivalent per kg of food, from:

> Poore, J. and Nemecek, T. (2018). Reducing food's environmental impacts through producers and
> consumers. *Science*, 360(6392), 987-992. https://doi.org/10.1126/science.aaq0216

taken from Our World in Data's "Food: greenhouse gas emissions across the supply chain"
chart (https://ourworldindata.org/grapher/food-emissions-supply-chain), licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

- Each row has the eight supply-chain stages the study reports (land use change, farm, animal feed,
  processing, transport, retail, packaging, losses). `kg_co2e_per_kg` is their sum. Every total was
  checked against OWID's separate per-kg list and all matched.
- These are **global averages**. A UK-grown product can be higher or lower, so the app shows the
  figure as "about" and uses it to compare dishes, not to certify one.
- A few figures look odd because a stage is negative. Nuts come out at 0.43 because the study
  credits nut orchards with storing carbon (land use change -3.26). That is how it is reported.
- "Wheat & Rye" was measured for bread and is used here for flour, pasta and other wheat foods.

## carbon_food_map.csv

Which category each food counts as (126 foods, the ones the ingredient aliases use), with a note
wherever the category is a stand-in, e.g. the wheat figure for pasta or the milk figure for yogurt.

Some foods are deliberately left **without** a category because nothing in the 43 fits well enough,
and borrowing a figure would mislead: butter, ghee, cream, creme fraiche, wild-caught fish (cod,
tuna, mackerel, sardines), coconut milk, oat drink, Quorn, quinoa, honey, maple syrup, milk
chocolate, cocoa, seeds, spices, herbs, sauces and stock cubes. The app lists these as "no carbon
figure" and says what share of the recipe the carbon estimate covers. Tap water and salt count as
zero, since their footprint is negligible.

Beef uses the beef-herd figure (99.5). Beef from dairy herds, a large share of UK beef, is about a
third of that (33.3), so beef dishes may read high for UK-sourced meat.

Load with `python manage.py load_carbon` (after `load_cofid`), or with `load_food_data`.
