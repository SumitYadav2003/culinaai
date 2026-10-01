from django.db import models


class CofidFood(models.Model):
    """
    One food from the UK government's CoFID 2021 dataset
    (McCance and Widdowson's Composition of Foods Integrated Dataset).

    All nutrient values are per 100 g of the food as described by its name
    (e.g. "Chicken, breast, raw"). A value is empty (None) when CoFID marks it
    as not measured, so missing data is never mistaken for zero.
    """

    food_code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=255)
    food_group = models.CharField(max_length=20, blank=True)

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
