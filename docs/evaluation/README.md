# Evaluating CulinaAI

This folder holds the evidence for "does CulinaAI work, and how well?". There are
two parts:

- **A. Automatic measurements.** A fixed benchmark of 30 recipe requests run through
  the real pipeline, and a report built from everything CulinaAI already stores.
- **B. A small user study.** People cook with CulinaAI and fill in a short
  questionnaire, including the System Usability Scale (SUS).

Older files here (`CulinaAI_nutrition_hand_check.xlsx`, `ingredient_coverage_*`,
`price_spot_check_*`) are the earlier checks of the nutrition, cost and carbon data.

## What is measured

| Area | Measure | How |
|---|---|---|
| Recipe quality | Passed the quality gates on the first try; average attempts; which checks failed; how often the safe fallback was needed | Attempt history saved with every recipe |
| Allergy safety | A declared allergen still found in the final ingredients | Allergen keyword lists run on the final ingredient list, separately from the validation engine |
| Diet | Meat, fish or (for vegan) animal ingredients in vegetarian or vegan recipes | Word lists run on the final ingredient list |
| Nutrition | Ingredients matched to the food data; how far the AI's own calorie guess was from the calculated figure | Stored insights |
| Meal style | "Everyday healthy" requests that came out with no red traffic lights | Stored insights |
| Cuisine | Very typical / typical / less typical, and retries | Stored insights; held-out test of the signature lists; 13 classic dishes |
| AI swap ideas | Ideas accepted by the code checks, and why the others were turned down | Stored insights |
| Cooking mode | Sessions, steps done, trouble reported, how dishes turned out; timers adjusted or not | Cooking sessions and step records |
| Usability | SUS score (0 to 100), feature questions, voice commands understood | User study answers |

Every figure in the report says how many recipes or sessions it is based on.

## A1. Run the benchmark

The 30 cases are in `benchmark_cases.json`: six cuisines (Thai, Italian, Indian,
Mexican, Chinese, Moroccan), each as a plain request, "Everyday healthy",
vegetarian, with an allergy, and as a high-protein treat. Don't change the cases
between runs you want to compare.

The benchmark calls the OpenAI API, so it costs money. Images are turned off for it.
With gpt-4.1-mini the whole run should cost well under £1, but check your OpenAI
usage page after a first short run.

Run it on your own computer, from the `backend` folder, with the same `.env` you use
for `runserver` (it needs `OPENAI_API_KEY`):

```bash
python manage.py run_benchmark --yes --limit 2    # a short try first
python manage.py run_benchmark --yes              # all 30 (roughly 15 to 30 minutes)
```

Each recipe is saved to Recipe History under a user called `culinaai-benchmark`
(it can't log in), so you can open any of them in the admin. A list of what ran is
written to `results/benchmark_<date>_<time>.jsonl`.

Then make the report for that run:

```bash
python manage.py evaluate --benchmark docs/evaluation/results/benchmark_<date>_<time>.jsonl
```

The AI gives a slightly different recipe every time, so for the dissertation it's
better to run the benchmark two or three times and report the spread than to trust
one run.

### What the first run found, and what was changed (9 October 2026)

The first full run (`results/benchmark_2026-10-09_1748.jsonl`) found these problems. Each was fixed
and has a test in `backend/recipes/tests/test_benchmark_fixes.py`:

- **A safe recipe failed the allergy check three times** (Indian, tree-nut allergy), so the safe
  fallback recipe was shown. The check treated any mention of a nut as using it, including wording
  like "respects your tree nut allergy" or "it skips cashews". It now accepts a mention only when the
  words around it say the food is left out ("free of", "skips", "instead of", "nut-free", "a tree nut
  allergy"), and still fails "garnish with almonds" or "instead of yoghurt, use cashews". The recipe
  prompt also asks the AI not to name allergens in the match summary.
- **The difficulty check counted "overnight" anywhere**, including "keeps in the fridge overnight" in
  the storage advice. It now reads only the method, and ignores an optional "or overnight".
- **Two "Everyday healthy" mince dishes stayed high in fat after three tries.** The note sent back to
  the AI now gives the amount per serving, the limit, and the ingredients most of it comes from (for
  example "beef mince, 250 g, 8.7 g saturated fat per serving"), and says it may use a lean version
  or less of it.
- **9 of 30 recipes had an ingredient with no food match**, which also left two "Everyday healthy"
  recipes unchecked. Jasmine rice, flour tortillas, chilli powder variants, Chinese egg noodles, rice
  vinegar, fish sauce, oyster sauce, chilli paste, ginger paste and British names for mince now match
  (see `backend/nutrition/data/README.md`).
- **Each failed check now saves what it objected to** (for example the allergy words it found), and
  the report lists them, so a failure can be explained instead of guessed.
- **The report counted a retry request on the last attempt**, which can't be retried. It now counts
  only retries that happened.

### The second run, and what was changed after it

With those fixes (`results/benchmark_2026-10-09_1855.jsonl`): every recipe passed the quality gates
first time, no fallback was needed, 28 of 30 recipes had every ingredient matched (21 before), and
"Everyday healthy" could be checked for all 6 recipes and was met by 4 (2 of 4 before). What was
left, and changed:

- **Thai and Chinese "Everyday healthy" were still not met after three tries.** The note to the AI
  now adds advice for the nutrient that is high (for salt: less soy, fish and oyster sauce, or
  reduced-salt soy sauce). Light coconut milk and reduced-salt soy sauce were added to the food
  data; before, the lighter versions matched nothing or the ordinary versions, so a recipe that used
  them still read as high.
- **The equipment check counted "tomato puree" and "pepper grinder" as needing a blender.** It now
  looks for blending as a step ("puree the", "blend until smooth").
- **The report listed the equipment the user had chosen as objections.** It now lists only what a
  check found, plus the step count when the difficulty check fails on it. The "Everyday healthy"
  column now says which nutrient was high, by how much, and where it came from.

Compare the next runs with these two to see whether the changes worked.

## A2. Report on real use

```bash
python manage.py evaluate
python manage.py evaluate --since 2026-10-01 --exclude-user demo
```

This covers every recipe and cooking session in the database except the benchmark
ones. Use `--exclude-user` to leave out test accounts (for example the demo account
used to try the cooking history).

To report on the live site's data, point your `.env` at the Render database for one
run: in the Render dashboard open the database, then **Connections**, and copy the
values from the **External Database URL**
(`postgresql://USER:PASSWORD@HOST:PORT/NAME`) into `DB_USER`, `DB_PASSWORD`,
`DB_HOST`, `DB_PORT` and `DB_NAME`. Put your local values back afterwards, and never
commit `.env`.

Reports are written to `results/`. Commit the reports and benchmark files you use in
the dissertation, so the figures can be traced back.

## B. User study

Everything for the study is in `user_study/`:

| File | What it is |
|---|---|
| `protocol.md` | Step-by-step plan for one session, and what to record |
| `participant_information_and_consent.md` | The information sheet and consent form |
| `questionnaire.md` | SUS (10 questions), CulinaAI questions, open questions |
| `voice_checklist.md` | The voice commands each participant tries, with a tally |
| `responses_template.csv` | One row per participant; copy it into `user_study/private/` |

**Ethics first.** If the study is part of your degree or any research you'll publish,
get approval through your university's ethics process before you recruit anyone, and
use their consent template if they have one. The forms here are a starting point,
not an approval.

Keep the filled-in answers in `docs/evaluation/user_study/private/`. That folder is
in `.gitignore`, so real answers and consent forms never go to GitHub. Use participant
codes (P1, P2, ...) in the answers, never names.

Then:

```bash
python manage.py evaluate --study docs/evaluation/user_study/private/responses.csv
```

The report gives the mean SUS score with its standard deviation and how it compares
with the usual average of 68 (Bangor, Kortum and Miller, 2009), the mean for each
CulinaAI question, and the share of voice commands that were understood.

## What these numbers can and can't show

- The allergy and diet cross-checks look for named ingredients. They can't see
  cross-contamination or what's in a particular brand's product.
- Nutrition depends on the ingredient weights the AI wrote and on the match to the
  food data.
- The cuisine check compares with one dataset of online recipes (Ahn et al., 2011).
- With a handful of cooking sessions or participants, the figures describe what
  happened. They don't prove that one version is better than another.

## References

- Ahn, Y.-Y., Ahnert, S. E., Bagrow, J. P. and Barabási, A.-L. (2011) Flavor network
  and the principles of food pairing. *Scientific Reports*, 1, 196.
- Bangor, A., Kortum, P. and Miller, J. (2009) Determining what individual SUS scores
  mean: adding an adjective rating scale. *Journal of Usability Studies*, 4(3), 114-123.
- Brooke, J. (1996) SUS: a "quick and dirty" usability scale. In Jordan, P. W. et al.
  (eds) *Usability Evaluation in Industry*. London: Taylor & Francis, 189-194.
