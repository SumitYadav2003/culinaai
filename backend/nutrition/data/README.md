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

When a name matches nothing as written, `nutrition/services.py` tries simpler versions of it before
giving up (`name_variants`): the part before a comma ("chicken breast, diced"), the name without words
that describe the cut or how it is bought ("boneless", "skinless", "fillets", "diced", "fresh",
"low-sodium" and similar), and each option of a choice in order ("water or chicken broth" tries water
first). Words that change the food ("ground", "dried", "minced", "smoked", "lean") are kept. One
known approximation: "low-sodium" stock matches ordinary stock, so its salt reads high.

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

Which carbon category each food counts as, with a note wherever the category is a stand-in (e.g. the
wheat figure for pasta, the milk figure for yogurt). Of the 216 foods the ingredient aliases use, 127
have a category.

The other 89 are left without one on purpose, because nothing in the 43 categories fits well enough
and borrowing a figure would mislead. The list below covers the first 192; the foods added in the
October 2026 coverage check (mostly spices, seeds, cheeses, seaweed and sauces) follow the same rule. Tap water and salt count as zero, since their footprint is
negligible. The remaining foods are reported in the app as "no carbon figure", and the app says what
share of the recipe the estimate covers. They are:

- dairy fats and dairy foods with no category: butter, ghee, single, double and whipping cream,
  creme fraiche
- fish with no category: cod, mackerel, fresh sardines, tinned sardines, tinned tuna (the 43
  categories only cover farmed fish)
- plant foods with no category: coconut milk, desiccated coconut, coconut oil, sesame oil, oat drink,
  Quorn, quinoa, chia seeds, sesame seeds, raisins, dates
- sweet foods: honey, maple syrup, milk chocolate, cocoa powder
- herbs and spices: basil, coriander, mint, parsley, mixed herbs, oregano, black pepper, chilli
  powder, cinnamon, coriander seeds (ground coriander), cumin, curry powder, garam masala, garlic powder, fresh and ground ginger,
  paprika, turmeric
- sauces, stocks and baking: tomato puree, ketchup, mayonnaise, mustard (smooth and wholegrain),
  pesto, curry paste, soy sauce, Worcestershire sauce, vinegar, gravy granules, stock cubes (beef,
  chicken, vegetable, and stock made up from cubes), baking powder, yeast

Beef uses the beef-herd figure (99.5). Beef from dairy herds, a large share of UK beef, is about a
third of that (33.3), so beef dishes may read high for UK-sourced meat. Soft cheeses (cream cheese,
mozzarella, paneer, feta) use the single "Cheese" figure (23.9), which was measured mostly on hard
cheese, so they probably read high. Lemon and lime juice use the whole-fruit figure, so they read low.

Load with `python manage.py load_carbon` (after `load_cofid`), or with `load_food_data`.

## ingredient_prices.csv

A price per kg for the 216 foods the ingredient aliases use. All 216 have a price; 11 are estimates. It is exported from
`docs/evaluation/CulinaAI_ingredient_prices.xlsx` with `scripts/export_prices.py`. The `status`
column says where each price came from:

- **ONS (70 foods; status starts with "ONS"):** ONS average prices for August 2026, from the ONS
  Shopping prices comparison tool
  (https://www.ons.gov.uk/economy/inflationandpriceindices/articles/shoppingpricescomparisontool/2023-05-03),
  using the data files the tool is built from (github.com/ONSvisual/cpi-items-actions). Contains
  public sector information licensed under the Open Government Licence v3.0. "Stand-in" (10 foods)
  means ONS has no exact item and the nearest one is used; the note says which. ONS averages cover
  all kinds of shops and brands.
- **Shop average (134 foods, status starts with "Shop"):** the average of shelf prices at Tesco,
  Sainsbury's and Morrisons,
  read from their websites on 2 October 2026 (ground coriander on 3 October, and 17 foods added in
  the coverage check on 4 October). Rules: the shop's own-brand standard range where one
  exists (not value, premium or organic), otherwise the cheapest normal-size brand; the smallest
  normal household pack; the regular price, not Clubcard or Nectar prices. A food needs prices from
  at least two shops. Two are stand-ins that borrow another food's prices, and the note says which:
  raw sweetcorn uses tinned sweetcorn (recipes mostly mean tinned), and rapeseed oil uses own-brand
  vegetable oil, whose label reads "Ingredients: Rapeseed Oil." (Tesco). Branded 1 L rapeseed oil
  averaged £3.51/kg; those rows are kept in the evidence, marked not used.
- **Free (1 food):** tap water.
- **Estimate (11 foods):** priced with a stated assumption, and the note on each row says which:
  burger buns (only Tesco's label gives a weight per bap, 76 g, assumed for all three shops); beetroot,
  garlic, butternut squash, Gruyere, dried soya beans and peaches (only one shop sells the standard
  product by weight); fenugreek leaves (only sold frozen); dried shiitake and kombu (only sold on
  tesco.com by a marketplace seller); and brewed coffee (instant coffee price x 1.8 g per 200 ml, the
  amount on the Nescafe Original label). Rows marked Estimate were added to the CSV by hand; the
  price workbook does not include them.

What "per kg" means. Prices are per kg of the food as CoFID describes it wherever the data allowed:

- Tinned beans, chickpeas, tuna, sweetcorn and sardines: per kg of drained weight, from the drained
  weight printed on the tin, because CoFID's values are for the drained food.
- Loose items sold "each": the item price over the USDA FoodData Central weight of one item (e.g.
  119 g for a medium pepper; the note names the FDC record). For mango, avocado and orange that USDA
  weight is the flesh, so the price is per kg of flesh. The USDA aubergine (548 g) is a US-sized one,
  so the aubergine price per kg may read low.
- Everything else is per kg as bought. Where CoFID describes the edible part only (banana flesh,
  whole chicken meat, egg without shell), the true cost per kg eaten is a little higher than shown.
- Eggs: the ONS price for 12 free-range eggs over 12 x 58 g, the middle of the UK medium egg band
  (53 g to under 63 g).
- Made-up stock: the average stock-cube price over 460 g (one 10 g cube plus 450 ml water, from the
  Tesco pack).

`ingredient_prices_shop_evidence.csv` has every shop price collected (429 rows): product name, pack
size, price, the shop's own unit price, the search URL and any judgement call, marked DOUBTFUL in
the note. The `Used` column says whether the row went into a price. A test recomputes every shop
average from the used rows.

Checks done:

- 301 shop rows have a pack weight. For 293 of them, pack price / weight matches the shop's own price
  per kg. 2 (spring onions) only show a price per item, so they can't be compared. The other 6
  differ for reasons given in the row: 4 were on offer (the regular price is kept) and 2 have a shop
  unit price that doesn't fit the printed weight (Sainsbury's sweetcorn; Tesco sardines, where
  Sainsbury's unit price for the same tin confirms the 85 g drained weight used).
- Ten shop rows picked at random were read again from the shop pages and all ten matched. The result
  is in `docs/evaluation/price_spot_check_2026-10-02.csv`.

Limits worth stating wherever costs are shown:

- Three shops, which hold about half the GB grocery market (Kantar, 12 weeks to July 2026). Asda and
  Aldi block automated reading of their sites and Lidl shows few prices online.
- ONS and shop prices are not on the same basis. For the ten foods sold "each" that both cover (eight
  ONS items, as the three peppers share one), the ONS price was 4% to 46% higher than the three
  shops, and 137% higher for peppers (ONS £1.66 vs 70p each). The figures are in
  `docs/evaluation/ons_vs_shop_each_items.csv`.
- Small packs cost more per kg than large ones, so costs are on the high side for bulk buyers.
- Prices change every week. Suggested wording for the app: "Estimated cost, from ONS average prices
  (August 2026) and Tesco, Sainsbury's and Morrisons prices (October 2026). Prices vary by shop and
  over time."

Load with `python manage.py load_prices` (after `load_cofid`), or with `load_food_data`.
## Coverage check (October 2026)

`docs/evaluation/ingredient_coverage_2026-10-04.md` measures how many common recipe ingredients the
matcher handles, using the 381 ingredients of the 56,498 recipes in Ahn et al. (2011), ranked by
their average share across 11 world cuisine regions. It led to 69 new aliases, 24 new priced foods
and two matching rules (guesses must name the main food; vague one-word names are not guessed).

## ingredient_swaps.csv

The hand-checked swap list behind "One dish, three ways" (`recipes/swap_service.py`). 47 swaps, each
from one food to another that does the same job in a dish, or to less of the same food:

- `from_code`, `to_code`: CoFID food codes. An empty `to_code` means "use less", with nothing added.
- `share`: how much of the original is replaced or removed (1 = all, 0.5 = half).
- `ratio`: grams of the new food for each gram replaced. Most are 1. Butter to rapeseed oil is 0.8
  (oil is all fat, butter about 80%). Mince to dried red lentils is 0.4, because 40 g of dried lentils
  cooks up to about the weight of 100 g of mince.
- `text`, `note`: what the page shows. `{from}` becomes the recipe's own name for the ingredient.

Every food in the list is in `ingredient_prices.csv`, and a test checks this. Each swap was checked
on the CoFID values before it was added; one was dropped (milk chocolate to plain chocolate) because
plain chocolate in CoFID has more sugar, so it is not clearly healthier.

How the three versions are chosen (all by code, at most three swaps each):

- **Cheapest:** lowest cost per serving. **Greenest:** lowest kg CO2e per serving. Neither may turn
  fat, saturates, sugars or salt to a worse traffic light.
- **Healthiest:** lowest health score: 1 point for each medium and 2 for each high traffic light, plus
  how close fat, saturates, sugars and salt are on average to the high level per 100 g, minus up to
  half a point for fibre (the full half at 6 g per 100 g, the UK "high fibre" level). It may cost more.
- A swap is skipped when the new food clashes with the user's allergies or diet, using the same
  rules as the quality gates, or when it has no price (cheapest) or carbon figure (greenest).
- Where a swap brings in or takes out a food with no figure (butter has no carbon category), the
  page shows the version's figure but no change, because the change can't be worked out.

AI swap ideas (`recipes/swap_suggestion_service.py`). After the final recipe is chosen, one small AI
call suggests up to 8 swaps that suit that dish, beyond this list. The AI only names ingredients.
A suggestion is used only if the original is an ingredient of the recipe found in the food data, the
new ingredient is found in the food data and is a different food, the amount is all, half or "use
less", the weight per 100 g replaced is 25 to 150 g, and the new ingredient is safe for the user's
allergies and diet. Cooking notes with a health claim are dropped. Accepted ideas then compete with
this list under the same rules, and are labelled "AI idea, checked by code" on the page. Each recipe
stores how many ideas were suggested, accepted and rejected (with the reason) in `insights.ai_swaps`.
If the AI call fails, the versions from this list are shown as before.
