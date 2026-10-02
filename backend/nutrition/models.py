from django.db import models


class CarbonCategory(models.Model):
    """
    Greenhouse gas emissions for one food category, in kg CO2-equivalent per kg
    of food, from Poore & Nemecek (2018), Science 360:987-992, as published by
    Our World in Data (CC BY 4.0).

    These are global averages across farms and countries, split into the eight
    supply-chain stages the study reports. The total is the sum of the stages.
    """

    name = models.CharField(max_length=60, unique=True)
    kg_co2e_per_kg = models.FloatField()

    land_use_change = models.FloatField(default=0)
    farm = models.FloatField(default=0)
    animal_feed = models.FloatField(default=0)
    processing = models.FloatField(default=0)
    transport = models.FloatField(default=0)
    retail = models.FloatField(default=0)
    packaging = models.FloatField(default=0)
    losses = models.FloatField(default=0)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "carbon categories"

    def __str__(self):
        return f"{self.name} ({self.kg_co2e_per_kg} kg CO2e/kg)"


class CofidFood(models.Model):
    """
    One food with its nutrients per 100 g.

    Almost all foods come from the UK government's CoFID 2021 dataset
    (McCance and Widdowson's Composition of Foods Integrated Dataset).
    A handful of common ingredients that CoFID doesn't cover (e.g. cornflour,
    chia seeds) come from USDA FoodData Central instead; `source` says which,
    so the app can always show where a number came from.

    A value is empty (None) when the source has no figure, so missing data is
    never mistaken for zero.
    """

    SOURCE_COFID = "CoFID 2021"
    SOURCE_USDA = "USDA FoodData Central"

    food_code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=255)
    food_group = models.CharField(max_length=20, blank=True)
    source = models.CharField(max_length=40, default=SOURCE_COFID)

    energy_kcal = models.FloatField(null=True, blank=True)
    energy_kj = models.FloatField(null=True, blank=True)
    protein_g = models.FloatField(null=True, blank=True)
    fat_g = models.FloatField(null=True, blank=True)
    saturates_g = models.FloatField(null=True, blank=True)
    carbohydrate_g = models.FloatField(null=True, blank=True)
    sugars_g = models.FloatField(null=True, blank=True)
    fibre_g = models.FloatField(null=True, blank=True)
    salt_g = models.FloatField(null=True, blank=True)

    # Which carbon category this food counts as. Empty when no category fits
    # well enough (e.g. butter, wild fish), so the app reports "no figure"
    # instead of borrowing a misleading one.
    carbon_category = models.ForeignKey(
        CarbonCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name="foods"
    )
    carbon_note = models.CharField(max_length=255, blank=True)

    # Price per kg in pounds. Empty when there is no price yet, so the app reports
    # "no price" instead of counting the food as free. data/README.md explains the
    # basis (e.g. tinned foods are per kg of drained weight).
    price_per_kg_gbp = models.FloatField(null=True, blank=True)
    price_source = models.CharField(max_length=120, blank=True)
    price_note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "CoFID food"

    def __str__(self):
        return f"{self.name} ({self.food_code})"


class IngredientAlias(models.Model):
    """
    A hand-checked link from an everyday ingredient name ("chicken breast")
    to the CoFID food that represents it ("Chicken, breast, raw").

    Aliases are tried before fuzzy matching, so the most common ingredients
    always match the same, checked food.
    """

    alias = models.CharField(max_length=120, unique=True, help_text="Lowercase everyday name, e.g. 'chicken breast'.")
    food = models.ForeignKey(CofidFood, on_delete=models.PROTECT, related_name="aliases")
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["alias"]
        verbose_name_plural = "ingredient aliases"

    def save(self, *args, **kwargs):
        self.alias = self.alias.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.alias} -> {self.food.name}"
