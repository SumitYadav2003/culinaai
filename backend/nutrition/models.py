from django.db import models


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
