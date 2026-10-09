"""
Builds the "signature ingredients" for each cuisine region from published data,
for the cuisine check (backend/recipes/cuisine_service.py).

Data: Ahn, Ahnert, Bagrow & Barabási (2011), "Flavor network and the principles
of food pairing", Scientific Reports 1:196. Supplementary file srep00196-s3.csv:
56,498 recipes from allrecipes.com, epicurious.com and menupan.com, grouped into
11 regions. Licence CC BY 4.0. Download "flavor_network_data.zip" from
https://doi.org/10.5281/zenodo.11449657 and unzip it (it contains srep00196-s3.csv).

Run from the project root:
    python scripts/build_cuisine_signatures.py path/to/srep00196-s3.csv

Method (the paper's "relative prevalence", Ahn et al. 2011):
    prevalence  P(i, c) = share of region c's recipes that use ingredient i
    relative    p(i, c) = P(i, c) - average of P(i, other regions)
A region's signature ingredients are its 12 highest relative-prevalence
ingredients, keeping only those at least 5 points above the other regions.
A few words in the data are too vague to identify a cuisine (vegetable,
vegetable_oil, seed, pepper, chicken) and are skipped.

How well the lists work is tested on recipes they were not built from: the
lists are rebuilt from a random 80% of the recipes, then counted on the other
20%. A region is "checked" in CulinaAI only if its own held-out recipes reach
2 or more signature ingredients at least 30 points more often than other
regions' recipes do (other regions averaged equally, so North America's 41,000
recipes don't drown out the rest).

How many signature ingredients real recipes use is recorded too (the middle
half, and the typical number), so a recipe can be compared with real ones
rather than with "12 out of 12", which no real dish reaches.

Output (committed, so the app never needs the raw file):
    backend/recipes/data/cuisine_signatures.csv
    backend/recipes/data/cuisine_regions.csv
"""

import csv
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / "backend" / "recipes" / "data"

TOP_N = 12
MIN_RELATIVE = 0.05
TOO_VAGUE = {"vegetable", "vegetable_oil", "seed", "pepper", "chicken"}
MIN_GAP = 0.30
MATCHES_FOR_TEST = 2
HOLDOUT_SEED = 42


def read_recipes(path):
    recipes = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(",")
            recipes.append((parts[0], set(parts[1:])))
    return recipes


def prevalence(recipes):
    by_region = defaultdict(list)
    for region, ingredients in recipes:
        by_region[region].append(ingredients)
    shares = {}
    for region, lists in by_region.items():
        counts = Counter()
        for ingredients in lists:
            counts.update(ingredients)
        shares[region] = {name: count / len(lists) for name, count in counts.items()}
    return by_region, shares


def signatures(recipes):
    by_region, shares = prevalence(recipes)
    result = {}
    for region in by_region:
        others = [other for other in by_region if other != region]
        rows = []
        for name, share in shares[region].items():
            if name in TOO_VAGUE:
                continue
            other_average = sum(shares[o].get(name, 0) for o in others) / len(others)
            relative = share - other_average
            if relative >= MIN_RELATIVE:
                rows.append((name, share, other_average, relative))
        rows.sort(key=lambda row: -row[3])
        result[region] = rows[:TOP_N]
    return by_region, result


def holdout_check(recipes):
    shuffled = recipes[:]
    random.Random(HOLDOUT_SEED).shuffle(shuffled)
    cut = int(len(shuffled) * 0.8)
    _, built = signatures(shuffled[:cut])
    test = defaultdict(list)
    for region, ingredients in shuffled[cut:]:
        test[region].append(ingredients)

    def share_reaching(lists, names):
        return sum(len(ingredients & names) >= MATCHES_FOR_TEST for ingredients in lists) / len(lists)

    stats = {}
    for region, rows in built.items():
        names = {row[0] for row in rows}
        own = share_reaching(test[region], names)
        others = [share_reaching(test[o], names) for o in test if o != region]
        other_average = sum(others) / len(others)
        stats[region] = (len(test[region]), own, other_average)
    return stats


def real_recipe_counts(by_region, built):
    """For each region: (lower quartile, median, upper quartile) of signature ingredients per real recipe."""
    result = {}
    for region, lists in by_region.items():
        names = {row[0] for row in built[region]}
        counts = sorted(len(ingredients & names) for ingredients in lists)
        pick = lambda share: counts[int(share * (len(counts) - 1))]  # noqa: E731
        result[region] = (pick(0.25), pick(0.5), pick(0.75))
    return result


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    recipes = read_recipes(sys.argv[1])
    by_region, built = signatures(recipes)
    stats = holdout_check(recipes)
    real = real_recipe_counts(by_region, built)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "cuisine_signatures.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["region", "rank", "ingredient", "prevalence", "other_regions", "relative"])
        for region in sorted(built):
            for rank, (name, share, other_average, relative) in enumerate(built[region], start=1):
                writer.writerow([region, rank, name, f"{share:.3f}", f"{other_average:.3f}", f"{relative:.3f}"])

    with open(OUT_DIR / "cuisine_regions.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["region", "recipes", "heldout_recipes", "heldout_own_2plus", "heldout_others_2plus", "gap", "checked",
                         "real_low", "real_typical", "real_high"])
        for region in sorted(built):
            tested, own, others = stats[region]
            gap = own - others
            writer.writerow([region, len(by_region[region]), tested, f"{own:.3f}", f"{others:.3f}", f"{gap:.3f}",
                             "yes" if gap >= MIN_GAP else "no", *real[region]])
            print(f"{region:17} {len(by_region[region]):6} recipes  held-out 2+: own {own:5.1%}  others {others:5.1%}"
                  f"  gap {gap:+.1%}  {'checked' if gap >= MIN_GAP else 'not checked'}"
                  f"  real recipes use {real[region][0]}-{real[region][2]} (typically {real[region][1]})")
    print(f"\nWrote {OUT_DIR / 'cuisine_signatures.csv'} and cuisine_regions.csv")


if __name__ == "__main__":
    main()
