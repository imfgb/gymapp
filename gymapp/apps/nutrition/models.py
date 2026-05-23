"""Nutrition models.

`SavedMeal` is a meal the user generated from their food preferences and kept:
a concrete list of foods + the macro split for its slot. It can be marked eaten
(stamping `eaten_at`) so the user has a running log of what they actually had.
Targets themselves stay computed on the fly (`services.nutrition`); only these
kept meals are persisted.
"""

from __future__ import annotations

from django.db import models

from gymapp.apps.core.models import OwnedMixin, OwnerScopedQuerySet, TimestampedModel


class SavedMeal(OwnedMixin, TimestampedModel):
    class Slot(models.TextChoices):
        BREAKFAST = "breakfast", "Desayuno"
        LUNCH = "lunch", "Comida"
        DINNER = "dinner", "Cena"
        SNACK = "snack", "Snack"

    slot = models.CharField(max_length=12, choices=Slot.choices)
    # List of {slug, grams, protein_g, carbs_g, fat_g, calories} (raw grams).
    foods = models.JSONField(default=list)
    calories = models.PositiveIntegerField(default=0)
    protein_g = models.PositiveIntegerField(default=0)
    carbs_g = models.PositiveIntegerField(default=0)
    fat_g = models.PositiveIntegerField(default=0)
    eaten_at = models.DateTimeField(null=True, blank=True)

    objects = OwnerScopedQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_slot_display()} ({self.owner.email})"

    @property
    def items(self) -> list[dict]:
        """Foods with their Spanish label attached, for templates."""
        from gymapp.services.nutrition import food_label

        out = []
        for it in self.foods:
            if isinstance(it, str):  # legacy rows stored bare slugs
                out.append({"slug": it, "label": food_label(it), "grams": None})
            else:
                out.append({**it, "label": food_label(it.get("slug", ""))})
        return out
