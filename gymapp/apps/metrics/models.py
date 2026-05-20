"""Body composition snapshots.

`UserMetricSnapshot` captures point-in-time bodyweight and (optionally) body
fat percentage. Height + DOB live on `users.Profile` because they don't
change. Phase 2 will add `MonthlyGoal`.
"""
from __future__ import annotations

from django.db import models

from gymapp.apps.core.models import OwnedMixin, OwnerScopedQuerySet, TimestampedModel


class UserMetricSnapshot(OwnedMixin, TimestampedModel):
    measured_at = models.DateTimeField(db_index=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2)
    body_fat_pct = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True
    )
    notes = models.CharField(max_length=200, blank=True)

    objects = OwnerScopedQuerySet.as_manager()

    class Meta:
        ordering = ["-measured_at"]

    def __str__(self) -> str:
        bf = f" @ {self.body_fat_pct}%" if self.body_fat_pct is not None else ""
        return f"{self.weight_kg}kg{bf} ({self.measured_at:%Y-%m-%d})"
