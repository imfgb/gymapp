"""Body composition snapshots + monthly goals.

`UserMetricSnapshot` captures point-in-time bodyweight and (optionally) body
fat percentage. Height + DOB live on `users.Profile` because they don't
change. `MonthlyGoal` holds per-month training targets; progress against it is
computed lazily by `gymapp.services.goals`.
"""

from __future__ import annotations

from django.db import models

from gymapp.apps.core.models import OwnedMixin, OwnerScopedQuerySet, TimestampedModel


class UserMetricSnapshot(OwnedMixin, TimestampedModel):
    measured_at = models.DateTimeField(db_index=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2)
    body_fat_pct = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    notes = models.CharField(max_length=200, blank=True)

    objects = OwnerScopedQuerySet.as_manager()

    class Meta:
        ordering = ["-measured_at"]

    def __str__(self) -> str:
        bf = f" @ {self.body_fat_pct}%" if self.body_fat_pct is not None else ""
        return f"{self.weight_kg}kg{bf} ({self.measured_at:%Y-%m-%d})"


class MonthlyGoal(OwnedMixin, TimestampedModel):
    """One row per (user, calendar month) holding optional training targets.

    Every target is nullable so a user can set just the ones they care about.
    Progress is derived from finished sessions / completed sets / bodyweight
    snapshots by `gymapp.services.goals.monthly_goal_progress` — nothing here is
    authoritative beyond the targets themselves.
    """

    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    target_sessions = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Number of finished sessions this month."
    )
    target_volume_kg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total kg lifted (weight × reps) over completed working sets.",
    )
    target_bodyweight_kg = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )

    objects = OwnerScopedQuerySet.as_manager()

    class Meta:
        ordering = ["-year", "-month"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "year", "month"], name="unique_owner_month_goal"
            ),
            models.CheckConstraint(
                condition=models.Q(month__gte=1) & models.Q(month__lte=12),
                name="monthlygoal_month_range",
            ),
        ]

    def __str__(self) -> str:
        return f"Goal {self.year}-{self.month:02d} ({self.owner.email})"
