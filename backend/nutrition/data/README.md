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

Load it with `python manage.py load_cofid`.

## ingredient_aliases.csv

Hand-checked links from everyday ingredient names ("chicken breast") to the CoFID food that
represents them ("Chicken, light meat, raw"), with a note where a choice needed explaining.
Load with `python manage.py load_ingredient_aliases` (after `load_cofid`).

Not in CoFID, so these ingredients show as "not found" rather than being matched to the wrong food:
cornflour, breadcrumbs, black beans, maple syrup, chia seeds, oat milk, dried rice noodles.
