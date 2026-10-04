"""
End-to-end check on the real CoFID 2021 data and the real ingredient aliases.

These ten recipes were also calculated by hand with spreadsheet formulas
(CulinaAI_nutrition_hand_check.xlsx). The expected values below come from that
spreadsheet. If a change to the engine or the data moves any of them, this fails.
"""

from django.core.management import call_command
from django.test import TestCase

from nutrition.services import IngredientInput, calculate_nutrition

# (recipe, servings, [(ingredient as a recipe would write it, grams, expected CoFID code)], kcal per serving)
HAND_CHECKED_RECIPES = [
    ("Garlic chicken and spinach rice bowl", 2, [("chicken breast", 300, "18-290"), ("basmati rice", 200, "11-857"), ("spinach", 100, "13-572"), ("garlic", 15, "13-244"), ("olive oil", 15, "17-038"), ("garam masala", 5, "13-829"), ("salt", 2, "17-367")], 606.75),
    ("Spaghetti bolognese", 4, [("beef mince", 500, "18-469"), ("spaghetti", 400, "11-716"), ("chopped tomatoes", 400, "13-530"), ("onion", 150, "13-499"), ("carrot", 100, "13-496"), ("garlic", 10, "13-244"), ("olive oil", 15, "17-038"), ("parmesan", 30, "12-526"), ("tomato puree", 30, "13-531")], 737.19),
    ("Chickpea and coconut curry with rice", 4, [("chickpeas", 480, "13-670"), ("coconut milk", 400, "14-889"), ("onion", 150, "13-499"), ("chopped tomatoes", 400, "13-530"), ("garlic", 10, "13-244"), ("ginger", 15, "13-890"), ("curry powder", 10, "13-876"), ("vegetable oil", 15, "17-686"), ("rice", 300, "11-861")], 665.81),
    ("Salmon, new potatoes and broccoli", 2, [("salmon fillet", 260, "16-356"), ("new potatoes", 400, "13-618"), ("broccoli", 200, "13-502"), ("butter", 15, "17-685"), ("lemon juice", 20, "14-277")], 508.6),
    ("Red lentil dal", 4, [("red lentils", 250, "13-657"), ("onion", 150, "13-499"), ("chopped tomatoes", 200, "13-530"), ("garlic", 10, "13-244"), ("ginger", 10, "13-890"), ("turmeric", 5, "13-861"), ("cumin", 5, "13-889"), ("ghee", 20, "17-640"), ("water", 900, "17-377")], 264.45),
    ("Cheese and vegetable omelette", 1, [("eggs", 150, "12-937"), ("milk", 30, "12-313"), ("cheddar", 30, "12-346"), ("mushrooms", 50, "13-505"), ("red pepper", 50, "13-524"), ("butter", 10, "17-685")], 423.5),
    ("Porridge with banana and honey", 2, [("porridge oats", 100, "11-788"), ("milk", 500, "12-313"), ("banana", 120, "14-318"), ("honey", 20, "17-050")], 382.9),
    ("Paneer tikka wraps", 2, [("paneer", 200, "12-495"), ("tortilla", 120, "11-925"), ("natural yogurt", 100, "12-184"), ("red onion", 80, "13-499"), ("green pepper", 80, "13-318"), ("garam masala", 5, "13-829"), ("vegetable oil", 10, "17-686"), ("lettuce", 50, "13-520")], 615.68),
    ("Tuna pasta bake", 4, [("pasta", 400, "11-716"), ("tuna", 320, "16-416"), ("sweetcorn", 200, "13-622"), ("cheddar cheese", 100, "12-346"), ("milk", 500, "12-313"), ("butter", 40, "17-685"), ("plain flour", 40, "11-886")], 731.3),
    ("Banana and chocolate pancakes (treat)", 2, [("plain flour", 120, "11-886"), ("eggs", 100, "12-937"), ("milk", 250, "12-313"), ("sugar", 30, "17-063"), ("banana", 120, "14-318"), ("dark chocolate", 40, "17-491"), ("butter", 20, "17-685")], 618.3),
]


class RealDataRecipeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with open("/dev/null", "w") as quiet:
            call_command("load_food_data", stdout=quiet)

    def test_every_alias_points_at_a_real_food(self):
        from nutrition.models import IngredientAlias
        self.assertGreater(IngredientAlias.objects.count(), 200)

    def test_hand_checked_recipes(self):
        for name, servings, items, expected_kcal in HAND_CHECKED_RECIPES:
            with self.subTest(recipe=name):
                result = calculate_nutrition([IngredientInput(i, g) for i, g, _ in items], servings)
                self.assertEqual(result.unmatched, [])
                self.assertEqual([m.food_code for m in result.matched], [code for _, _, code in items])
                self.assertEqual(result.coverage_pct, 100.0)
                self.assertAlmostEqual(result.per_serving["energy_kcal"], expected_kcal, places=1)

    def test_lentil_dal_is_all_green(self):
        name, servings, items, _ = HAND_CHECKED_RECIPES[4]
        result = calculate_nutrition([IngredientInput(i, g) for i, g, _ in items], servings)
        self.assertEqual(set(result.traffic_lights.values()), {"green"})

    def test_unknown_ingredient_is_reported(self):
        result = calculate_nutrition([IngredientInput("dragon fruit", 20), IngredientInput("rice", 80)], 1)
        self.assertEqual(result.unmatched, ["dragon fruit"])
        self.assertEqual(result.coverage_pct, 80.0)
        self.assertFalse(result.is_complete)

    def test_usda_foods_fill_cofid_gaps_and_say_so(self):
        items = ["cornflour", "breadcrumbs", "black beans", "maple syrup", "chia seeds", "oat milk", "rice noodles"]
        result = calculate_nutrition([IngredientInput(name, 50) for name in items], 1)
        self.assertEqual(result.unmatched, [])
        self.assertEqual({m.source for m in result.matched}, {"USDA FoodData Central"})

    def test_usda_carbohydrate_is_converted_to_uk_basis(self):
        # USDA counts fibre inside carbohydrate; CoFID doesn't. Chia: 42.1 - 34.4 = 7.7 g.
        from nutrition.models import CofidFood
        chia = CofidFood.objects.get(food_code="USDA-170554")
        self.assertAlmostEqual(chia.carbohydrate_g, 7.7)
        self.assertEqual(chia.source, "USDA FoodData Central")


class RealCarbonDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with open("/dev/null", "w") as quiet:
            call_command("load_food_data", stdout=quiet)

    def test_every_category_total_is_the_sum_of_its_stages(self):
        from nutrition.models import CarbonCategory

        stages = ["land_use_change", "farm", "animal_feed", "processing", "transport", "retail", "packaging", "losses"]
        categories = CarbonCategory.objects.all()
        self.assertEqual(categories.count(), 43)
        for category in categories:
            with self.subTest(category=category.name):
                stage_sum = sum(getattr(category, s) for s in stages)
                self.assertAlmostEqual(category.kg_co2e_per_kg, stage_sum, delta=0.01)

    def test_every_row_of_the_food_map_is_linked(self):
        import csv
        from nutrition.management.commands.load_cofid import DATA_DIR
        from nutrition.models import CofidFood

        with (DATA_DIR / "carbon_food_map.csv").open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(CofidFood.objects.filter(carbon_category__isnull=False).count(), len(rows))

    def test_red_lentil_dal_by_hand(self):
        # lentils 0.25 kg x 1.79 + onion 0.15 x 0.50 + tomatoes 0.20 x 2.09 + garlic 0.01 x 0.50
        # = 0.9455 kg; water counts as zero; spices and ghee have no figure. 4 servings -> 0.236 kg
        name, servings, items, _ = HAND_CHECKED_RECIPES[4]
        result = calculate_nutrition([IngredientInput(i, g) for i, g, _ in items], servings)
        self.assertAlmostEqual(result.carbon_kg_per_serving, 0.236, places=3)
        self.assertEqual(result.carbon_unmatched, ["ginger", "turmeric", "cumin", "ghee"])

    def test_beef_bolognese_is_far_higher_than_dal(self):
        bolognese = HAND_CHECKED_RECIPES[1]
        dal = HAND_CHECKED_RECIPES[4]
        results = [
            calculate_nutrition([IngredientInput(i, g) for i, g, _ in items], servings)
            for _, servings, items, _ in (bolognese, dal)
        ]
        self.assertGreater(results[0].carbon_kg_per_serving, 10 * results[1].carbon_kg_per_serving)


class RealPriceDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with open("/dev/null", "w") as quiet:
            call_command("load_food_data", stdout=quiet)

    def read_csv(self, filename):
        import csv
        from nutrition.management.commands.load_cofid import DATA_DIR

        with (DATA_DIR / filename).open(encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def test_every_food_an_alias_uses_is_listed(self):
        from nutrition.models import IngredientAlias

        listed = {row["food_code"] for row in self.read_csv("ingredient_prices.csv")}
        used = set(IngredientAlias.objects.values_list("food__food_code", flat=True))
        self.assertEqual(used - listed, set())

    def test_every_food_has_a_price(self):
        from nutrition.models import CofidFood

        listed = [row["food_code"] for row in self.read_csv("ingredient_prices.csv")]
        foods = CofidFood.objects.filter(food_code__in=listed)
        self.assertEqual(foods.count(), 216)
        unpriced = set(foods.filter(price_per_kg_gbp__isnull=True).values_list("food_code", flat=True))
        self.assertEqual(unpriced, set())
        # Priced with a stated assumption (one shop, a marketplace seller, or an assumed weight);
        # the note on each row says which.
        estimates = {row["food_code"] for row in self.read_csv("ingredient_prices.csv") if row["status"] == "Estimate"}
        self.assertEqual(estimates, {
            "11-985", "13-164", "13-244", "13-355",  # buns, beetroot, garlic, butternut squash
            "12-164", "13-115", "14-299", "13-243", "13-294", "13-339",  # gruyere, soya beans, peaches,
            "17-153",  # fenugreek leaves, dried shiitake, kombu, brewed coffee
        })
        for food in foods.exclude(price_per_kg_gbp__isnull=True):
            with self.subTest(food=food.food_code):
                self.assertTrue(food.price_source)
                self.assertGreaterEqual(food.price_per_kg_gbp, 0)

    def test_every_shop_average_matches_its_shop_prices(self):
        # Recompute each average from the raw shop rows and compare with the loaded price.
        import re
        from collections import defaultdict
        from statistics import mean

        shop_prices = defaultdict(list)
        for row in self.read_csv("ingredient_prices_shop_evidence.csv"):
            if row["Used"] == "yes":
                shop_prices[row["Food code"]].append(float(row["Price per kg (£)"]))

        averages = [row for row in self.read_csv("ingredient_prices.csv") if row["status"].startswith("Shop")]
        self.assertEqual(len(averages), 134)
        for row in averages:
            if row["food_code"] == "17-774":  # stock made up from cubes, checked below
                continue
            # A stand-in borrows another food's prices and names it: "Uses the prices of 13-529 (...)".
            borrowed = re.search(r"Uses the prices of (\S+)", row["note"])
            if row["status"] == "Shop stand-in, check":
                self.assertIsNotNone(borrowed, row["food_code"])
            source_code = borrowed.group(1) if borrowed else row["food_code"]
            with self.subTest(food=row["food_code"]):
                prices = shop_prices[source_code]
                self.assertGreaterEqual(len(prices), 2)
                self.assertAlmostEqual(float(row["price_per_kg_gbp"]), mean(prices), delta=0.01)

    def test_used_shop_rows_belong_to_a_shop_priced_food(self):
        # "Used = yes" must mean the row went into a price: the food's own shop average, the food a
        # stand-in borrows from, or the chicken stock cubes behind made-up stock (17-774).
        import re

        prices = {row["food_code"]: row for row in self.read_csv("ingredient_prices.csv")}
        own = {code for code, row in prices.items() if row["status"] == "Shop average"}
        borrowed = {re.search(r"Uses the prices of (\S+)", row["note"]).group(1)
                    for row in prices.values() if row["status"] == "Shop stand-in, check"}
        allowed = own | borrowed | {"17-726"}
        for row in self.read_csv("ingredient_prices_shop_evidence.csv"):
            if row["Used"] == "yes":
                with self.subTest(food=row["Food code"], shop=row["Shop"]):
                    self.assertIn(row["Food code"], allowed)
        self.assertNotIn("17-041", own)  # rapeseed oil borrows vegetable oil; its branded rows are not used

    def test_made_up_stock_is_cube_price_over_stock_weight(self):
        # One 10 g cube + 450 ml water = 460 g. Cubes: Tesco 10 for £1.00, Sainsbury's 10 for £1.10,
        # Morrisons 12 for £1.30 -> average £0.10611 a cube -> £0.231 per kg of stock.
        from nutrition.models import CofidFood

        self.assertAlmostEqual(CofidFood.objects.get(food_code="17-774").price_per_kg_gbp, 0.231, places=3)

    def test_red_lentil_dal_by_hand(self):
        # lentils 0.25 kg x £4.20 + onion 0.15 x £1.15 + canned tomatoes 0.20 x £1.625
        # + ginger 0.01 x £12.47 + turmeric 0.005 x £23.47 + cumin 0.005 x £28.92 + ghee 0.02 x £15.00
        # + garlic 0.01 x £5.00 = £2.284; water is free. 4 servings -> £0.57
        name, servings, items, _ = HAND_CHECKED_RECIPES[4]
        result = calculate_nutrition([IngredientInput(i, g) for i, g, _ in items], servings)
        self.assertAlmostEqual(result.cost_gbp_per_serving, 0.57)
        self.assertEqual(result.cost_unmatched, [])
        self.assertEqual(result.cost_coverage_pct, 100.0)

    def test_tinned_chickpeas_are_priced_per_drained_kg(self):
        # Shop prices for a 400 g tin with 240 g drained: Tesco £0.41, Sainsbury's £0.41, Morrisons £0.37
        # -> £1.708, £1.708, £1.542 per drained kg -> average £1.65
        from nutrition.models import CofidFood

        self.assertAlmostEqual(CofidFood.objects.get(food_code="13-670").price_per_kg_gbp, 1.65, places=2)

    def test_porridge_by_hand(self):
        # oats 0.1 kg x £3.16 + milk 0.5 x £1.012 + banana 0.12 x £1.14 + honey 0.02 x £5.65
        # = £1.072 (all ONS prices, Aug 2026). 2 servings -> £0.54
        name, servings, items, _ = HAND_CHECKED_RECIPES[6]
        result = calculate_nutrition([IngredientInput(i, g) for i, g, _ in items], servings)
        self.assertAlmostEqual(result.cost_gbp_per_serving, 0.54)
        self.assertEqual(result.cost_coverage_pct, 100.0)

class DescribedNameTests(TestCase):
    """Names as recipes write them: cut, prepared, or offering a choice."""

    @classmethod
    def setUpTestData(cls):
        with open("/dev/null", "w") as quiet:
            call_command("load_food_data", stdout=quiet)

    def test_described_names_find_the_plain_food(self):
        from nutrition.services import resolve_ingredients

        expected = {
            "boneless skinless chicken breast": "18-290",
            "chicken breast, diced": "18-290",
            "chicken breast fillets": "18-290",
            "boneless chicken thighs": "18-289",
            "chicken pieces": "18-488",  # not "Chicken pieces, coated, takeaway"
            "chili flakes": "13-873",
            "crushed red pepper flakes": "13-873",
            "low-sodium chicken broth": "17-681",
            "water or low-sodium chicken broth": "17-377",  # the first choice
            "fresh parsley or coriander": "13-844",
            "finely chopped onion": "13-499",
        }
        for name, code in expected.items():
            with self.subTest(name=name):
                food = resolve_ingredients([IngredientInput(name, 100)])[0].food
                self.assertIsNotNone(food)
                self.assertEqual(food.food_code, code)

    def test_own_aliases_still_win_over_simplified_names(self):
        from nutrition.services import resolve_ingredients

        # "chopped tomatoes" means tinned; "fresh coriander" is the leaf, not the seed.
        for name, code in {"chopped tomatoes": "13-530", "fresh coriander": "13-888", "ground ginger": "13-832"}.items():
            with self.subTest(name=name):
                self.assertEqual(resolve_ingredients([IngredientInput(name, 100)])[0].food.food_code, code)

    def test_a_chicken_skillet_from_the_live_site_is_complete(self):
        # The recipe from the screenshot of 4 October 2026: 'water or low-sodium chicken broth',
        # 'chili flakes' and 'fresh parsley or coriander' were not found, so coverage fell below
        # 85% and protein showed no level. Now everything is found and it is High protein.
        items = [("boneless chicken breast", 300), ("basmati rice", 150), ("tomato", 150), ("spinach", 100),
                 ("onion", 100), ("olive oil", 15), ("chili flakes", 1), ("salt", 4),
                 ("water or low-sodium chicken broth", 400), ("fresh parsley or coriander", 5)]
        result = calculate_nutrition([IngredientInput(n, g) for n, g in items], 2)
        self.assertEqual(result.unmatched, [])
        self.assertIn("High protein", result.claims)
