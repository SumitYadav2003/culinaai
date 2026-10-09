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
