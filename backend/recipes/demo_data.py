"""
The recipes, pantry and plan a "Try the demo" account starts with.

The recipe text is written in the same layout the AI uses, and the ingredient
weights are what the AI's structure step would return, so the demo pages show
real nutrition, cost and carbon worked out by the same code as everyone else's.
No AI is called to make a demo account.
"""

NO_CLASSIC = {"is_classic": False, "classic_name": "", "core_ingredients": [], "usual_minutes": None, "missing": []}

DEMO_RECIPES = [
    {
        "key": "curry",
        "title": "Chickpea and Spinach Curry",
        "cuisine": "Indian",
        "meal_type": "Dinner",
        "diets": ["Vegetarian", "Vegan"],
        "difficulty": "easy",
        "minutes": 30,
        "servings": 4,
        "favourite": True,
        "ingredients_text": "chickpeas, spinach, tinned tomatoes, onion, garlic, ginger, coconut milk",
        "ingredients": [
            {"name": "chickpeas", "display": "2 x 400 g tins, drained", "grams": 480},
            {"name": "spinach", "display": "200 g", "grams": 200},
            {"name": "chopped tomatoes", "display": "400 g tin", "grams": 400},
            {"name": "onion", "display": "1 large", "grams": 180},
            {"name": "garlic", "display": "3 cloves", "grams": 12},
            {"name": "ginger", "display": "thumb-sized piece", "grams": 15},
            {"name": "light coconut milk", "display": "200 ml", "grams": 200},
            {"name": "vegetable oil", "display": "1 tbsp", "grams": 14},
            {"name": "garam masala", "display": "2 tsp", "grams": 5},
            {"name": "ground cumin", "display": "1 tsp", "grams": 2},
            {"name": "ground turmeric", "display": "1 tsp", "grams": 3},
            {"name": "salt", "display": "1/2 tsp", "grams": 3},
        ],
        "text": """RECIPE TITLE:
Chickpea and Spinach Curry

SHORT DESCRIPTION:
A mild, creamy curry of chickpeas and spinach in a spiced tomato and coconut sauce. It's made in one pan in half an hour and keeps well for lunches.

MATCH SUMMARY:
Uses your chickpeas, spinach, tinned tomatoes and onion. It is a vegan Indian dinner for 4, ready in 30 minutes, and only needs a hob and one large pan.

INGREDIENTS WITH QUANTITIES:
- 2 x 400 g tins chickpeas, drained and rinsed
- 200 g fresh spinach
- 400 g tin chopped tomatoes
- 1 large onion, finely chopped
- 3 garlic cloves, crushed
- Thumb-sized piece of ginger, grated
- 200 ml light coconut milk
- 1 tbsp vegetable oil
- 2 tsp garam masala
- 1 tsp ground cumin
- 1 tsp ground turmeric
- 1/2 tsp salt

COOKING TIME:
30 minutes

SERVINGS:
4

DIFFICULTY:
Easy

STEPS:
1. Heat the oil in a large pan over a medium heat and cook the onion for 8 minutes, until soft and golden.
2. Stir in the garlic and ginger and cook for 1 minute.
3. Add the garam masala, cumin and turmeric and stir for 30 seconds.
4. Pour in the tomatoes and coconut milk, add the chickpeas and salt, and simmer for 12 minutes, stirring now and then.
5. Stir in the spinach a handful at a time until it wilts, about 2 minutes.
6. Taste, add a little more salt if needed, and serve.

ALLERGY AND DIET NOTES:
The user-provided restricted ingredients have been excluded from this recipe.
It is vegan as written.

ESTIMATED COST:
- Approximate total cost: £4.20
- Approximate cost per serving: £1.05
- Budget level match: Low budget
- Cost-saving tip: frozen spinach works just as well and costs less.

PAIRING SUGGESTIONS:
- Side dish: basmati rice or warm naan
- Drink: a cold glass of mango lassi made with plant yoghurt
- Dessert: sliced mango
- Best occasion: a midweek dinner

CHEF TIPS:
- Let the onion brown properly; it gives the sauce its depth.
- Mash a few chickpeas against the side of the pan to thicken the sauce.

STORAGE ADVICE:
Cool, then keep covered in the fridge for up to 3 days, or freeze for up to 3 months.

SUBSTITUTIONS:
- Kale instead of spinach
- Butter beans instead of chickpeas
""",
    },
    {
        "key": "traybake",
        "title": "Lemon and Herb Chicken Tray Bake",
        "cuisine": "British",
        "meal_type": "Dinner",
        "diets": [],
        "difficulty": "easy",
        "minutes": 45,
        "servings": 4,
        "favourite": True,
        "ingredients_text": "chicken thighs, potatoes, red onion, lemon, garlic, green beans",
        "ingredients": [
            {"name": "chicken thighs", "display": "8 skinless, boneless", "grams": 700},
            {"name": "new potatoes", "display": "750 g, halved", "grams": 750},
            {"name": "red onion", "display": "2, cut into wedges", "grams": 300},
            {"name": "green beans", "display": "200 g", "grams": 200},
            {"name": "lemon", "display": "1", "grams": 100},
            {"name": "garlic", "display": "4 cloves", "grams": 16},
            {"name": "olive oil", "display": "2 tbsp", "grams": 28},
            {"name": "dried oregano", "display": "2 tsp", "grams": 2},
            {"name": "salt", "display": "1/2 tsp", "grams": 3},
        ],
        "text": """RECIPE TITLE:
Lemon and Herb Chicken Tray Bake

SHORT DESCRIPTION:
Chicken thighs roasted with new potatoes, red onion and lemon, with green beans added at the end. Everything cooks in one tin.

MATCH SUMMARY:
Uses your chicken thighs, potatoes, red onion and lemon. It is a British dinner for 4, ready in 45 minutes, and only needs the oven.

INGREDIENTS WITH QUANTITIES:
- 8 skinless, boneless chicken thighs (about 700 g)
- 750 g new potatoes, halved
- 2 red onions, cut into wedges
- 200 g green beans, trimmed
- 1 lemon, zested and cut into wedges
- 4 garlic cloves, left whole
- 2 tbsp olive oil
- 2 tsp dried oregano
- 1/2 tsp salt

COOKING TIME:
45 minutes

SERVINGS:
4

DIFFICULTY:
Easy

STEPS:
1. Heat the oven to 200°C (180°C fan).
2. Toss the potatoes, onion and garlic with half the oil and salt in a large roasting tin and roast for 15 minutes.
3. Rub the chicken with the rest of the oil, the oregano and the lemon zest.
4. Add the chicken and lemon wedges to the tin and roast for 20 minutes.
5. Scatter over the green beans and roast for 10 more minutes, until the chicken is cooked through with no pink meat and the juices run clear.
6. Squeeze the roasted lemon over everything and serve.

ALLERGY AND DIET NOTES:
The user-provided restricted ingredients have been excluded from this recipe.

ESTIMATED COST:
- Approximate total cost: £8.50
- Approximate cost per serving: £2.15
- Budget level match: Moderate
- Cost-saving tip: thighs on the bone are cheaper; add 10 minutes to the roasting time.

PAIRING SUGGESTIONS:
- Side dish: a green salad
- Drink: sparkling water with lemon
- Dessert: Greek yoghurt with honey
- Best occasion: a family dinner

CHEF TIPS:
- Spread everything out in one layer so it roasts rather than steams.
- Use a meat thermometer: chicken is done at 75°C in the thickest part.

STORAGE ADVICE:
Keep leftovers covered in the fridge for up to 2 days and reheat until steaming hot.

SUBSTITUTIONS:
- Broccoli instead of green beans
- Sweet potato instead of new potatoes
""",
    },
    {
        "key": "pasta",
        "title": "Tomato and Basil Pasta",
        "cuisine": "Italian",
        "meal_type": "Lunch",
        "diets": ["Vegetarian"],
        "difficulty": "easy",
        "minutes": 20,
        "servings": 2,
        "favourite": False,
        "ingredients_text": "pasta, cherry tomatoes, garlic, basil, parmesan",
        "ingredients": [
            {"name": "spaghetti", "display": "180 g, dried", "grams": 180},
            {"name": "cherry tomatoes", "display": "300 g, halved", "grams": 300},
            {"name": "garlic", "display": "2 cloves", "grams": 8},
            {"name": "olive oil", "display": "1 1/2 tbsp", "grams": 20},
            {"name": "fresh basil", "display": "small bunch", "grams": 10},
            {"name": "parmesan", "display": "20 g, grated", "grams": 20},
            {"name": "salt", "display": "pinch", "grams": 1},
        ],
        "text": """RECIPE TITLE:
Tomato and Basil Pasta

SHORT DESCRIPTION:
Spaghetti with cherry tomatoes cooked down with garlic and olive oil, finished with fresh basil and a little Parmesan. A quick lunch from things you usually have in.

MATCH SUMMARY:
Uses your pasta, cherry tomatoes, garlic and basil. It is a vegetarian Italian lunch for 2, ready in 20 minutes, and only needs a hob.

INGREDIENTS WITH QUANTITIES:
- 180 g dried spaghetti
- 300 g cherry tomatoes, halved
- 2 garlic cloves, thinly sliced
- 1 1/2 tbsp olive oil
- Small bunch of fresh basil
- 20 g Parmesan (or a vegetarian hard cheese), grated
- Pinch of salt

COOKING TIME:
20 minutes

SERVINGS:
2

DIFFICULTY:
Easy

STEPS:
1. Cook the spaghetti in a large pan of boiling water for 10 minutes, or as the packet says.
2. Meanwhile, warm the oil in a frying pan and cook the garlic for 1 minute without letting it brown.
3. Add the tomatoes and salt and cook for 6 minutes, pressing some of them down to make a sauce.
4. Drain the pasta, keeping a mug of the cooking water.
5. Toss the pasta with the tomatoes and a splash of the water until glossy.
6. Tear in the basil and serve with the cheese on top.

ALLERGY AND DIET NOTES:
The user-provided restricted ingredients have been excluded from this recipe.
Use a vegetarian hard cheese to keep it vegetarian.

ESTIMATED COST:
- Approximate total cost: £2.60
- Approximate cost per serving: £1.30
- Budget level match: Low budget
- Cost-saving tip: a tin of chopped tomatoes works when cherry tomatoes are expensive.

PAIRING SUGGESTIONS:
- Side dish: rocket with a squeeze of lemon
- Drink: still water with cucumber
- Dessert: fresh strawberries
- Best occasion: a quick weekend lunch

CHEF TIPS:
- The starchy pasta water helps the sauce cling to the spaghetti.
- Add the basil at the end so it stays fresh and green.

STORAGE ADVICE:
Best eaten straight away. Leftovers keep in the fridge for a day.

SUBSTITUTIONS:
- Spinach instead of basil
- Wholewheat spaghetti for more fibre
""",
    },
    {
        "key": "oats",
        "title": "Blueberry and Banana Porridge",
        "cuisine": "British",
        "meal_type": "Breakfast",
        "diets": ["Vegetarian"],
        "difficulty": "easy",
        "minutes": 10,
        "servings": 2,
        "favourite": False,
        "ingredients_text": "porridge oats, milk, banana, blueberries, yoghurt, honey",
        "ingredients": [
            {"name": "porridge oats", "display": "100 g", "grams": 100},
            {"name": "semi-skimmed milk", "display": "400 ml", "grams": 412},
            {"name": "banana", "display": "1, sliced", "grams": 100},
            {"name": "blueberries", "display": "80 g", "grams": 80},
            {"name": "natural yoghurt", "display": "2 tbsp", "grams": 60},
            {"name": "honey", "display": "2 tsp", "grams": 14},
        ],
        "text": """RECIPE TITLE:
Blueberry and Banana Porridge

SHORT DESCRIPTION:
Creamy porridge made with milk, topped with banana, blueberries, a spoon of yoghurt and a little honey. A filling breakfast in 10 minutes.

MATCH SUMMARY:
Uses your porridge oats, milk and yoghurt. It is a vegetarian breakfast for 2, ready in 10 minutes, and only needs a hob.

INGREDIENTS WITH QUANTITIES:
- 100 g porridge oats
- 400 ml semi-skimmed milk
- 1 banana, sliced
- 80 g blueberries
- 2 tbsp natural yoghurt
- 2 tsp honey

COOKING TIME:
10 minutes

SERVINGS:
2

DIFFICULTY:
Easy

STEPS:
1. Put the oats and milk in a saucepan over a medium heat.
2. Bring to a gentle simmer and cook for 5 minutes, stirring often, until thick and creamy.
3. Stir in half the banana for the last minute.
4. Spoon into bowls and top with the rest of the banana, the blueberries and the yoghurt.
5. Drizzle with the honey and serve.

ALLERGY AND DIET NOTES:
The user-provided restricted ingredients have been excluded from this recipe.

ESTIMATED COST:
- Approximate total cost: £1.60
- Approximate cost per serving: £0.80
- Budget level match: Low budget
- Cost-saving tip: frozen blueberries cost less than fresh and work just as well.

PAIRING SUGGESTIONS:
- Side dish: a boiled egg
- Drink: a cup of tea
- Dessert: not needed
- Best occasion: a weekday breakfast

CHEF TIPS:
- Stir often so the porridge doesn't catch on the bottom of the pan.
- Add a splash more milk if it gets too thick.

STORAGE ADVICE:
Best eaten fresh. Cooked porridge keeps in the fridge for a day; loosen it with milk when reheating.

SUBSTITUTIONS:
- Any milk, including oat or soya milk
- Raspberries instead of blueberries
""",
    },
]

# Pantry items, with "use by" days from today (None means no date). Some go off soon,
# so the "Use it before it goes off" card has something to show.
DEMO_PANTRY = [
    ("Spinach", 300, "g", "vegetable", 1),
    ("Natural yoghurt", 500, "g", "dairy", 2),
    ("Chicken thighs", 700, "g", "protein", 3),
    ("Semi-skimmed milk", 1, "l", "dairy", 5),
    ("Cherry tomatoes", 250, "g", "vegetable", 6),
    ("Chickpeas", 2, "pack", "protein", None),
    ("Porridge oats", 1, "kg", "grain", None),
    ("Spaghetti", 500, "g", "grain", None),
    ("Onions", 4, "pcs", "vegetable", None),
    ("Olive oil", 500, "ml", "sauce", None),
]

# The meal plan for this week: (day of the week, 0 = Monday, meal, recipe key, servings).
DEMO_PLAN = [
    (0, "dinner", "traybake", 4),
    (1, "breakfast", "oats", 2),
    (2, "dinner", "curry", 4),
    (3, "lunch", "pasta", 2),
    (4, "dinner", "traybake", 2),
    (5, "breakfast", "oats", 2),
    (6, "dinner", "curry", 3),
]
