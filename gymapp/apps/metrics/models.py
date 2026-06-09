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
    # Body-composition extras from smart scales — all optional (many users don't
    # have a scale that reports these).
    muscle_pct = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    visceral_fat = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Tanita/Omron visceral-fat rating (~1–30).",
    )
    # Circumference measurements (cm) — all optional. Tape-measure tracking of how
    # each body part changes over time (feedback #2).
    chest_cm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    waist_cm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    hip_cm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    arm_cm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    thigh_cm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    calf_cm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    notes = models.CharField(max_length=200, blank=True)

    objects = OwnerScopedQuerySet.as_manager()

    # (Spanish label, field name) for the circumference inputs/columns, in order.
    MEASUREMENT_FIELDS = (
        ("Pecho", "chest_cm"),
        ("Cintura", "waist_cm"),
        ("Cadera", "hip_cm"),
        ("Brazo", "arm_cm"),
        ("Muslo", "thigh_cm"),
        ("Pantorrilla", "calf_cm"),
    )

    class Meta:
        ordering = ["-measured_at"]

    def __str__(self) -> str:
        bf = f" @ {self.body_fat_pct}%" if self.body_fat_pct is not None else ""
        return f"{self.weight_kg}kg{bf} ({self.measured_at:%Y-%m-%d})"

    def measurements(self):
        """(label, value) pairs for the circumferences that are set."""
        return [
            (label, getattr(self, field))
            for label, field in self.MEASUREMENT_FIELDS
            if getattr(self, field) is not None
        ]

    def bmi_for(self, height_cm: int | None) -> float | None:
        """BMI = weight / height^2 (m). None if height isn't set."""
        if not height_cm or height_cm <= 0:
            return None
        h_m = float(height_cm) / 100.0
        return round(float(self.weight_kg) / (h_m * h_m), 1)


class ReadinessSnapshot(OwnedMixin, TimestampedModel):
    """One per (user, day): daily 1–5 self-report for sleep / stress / soreness.

    Drives the day's training advice together with computed muscle fatigue.
    Higher sleep_quality = better. Higher stress / soreness = worse.
    """

    date = models.DateField(db_index=True)
    sleep_quality = models.PositiveSmallIntegerField(help_text="1 (terrible) – 5 (great)")
    stress_level = models.PositiveSmallIntegerField(help_text="1 (low) – 5 (high)")
    soreness_overall = models.PositiveSmallIntegerField(help_text="1 (none) – 5 (very sore)")
    notes = models.CharField(max_length=200, blank=True, default="")

    objects = OwnerScopedQuerySet.as_manager()

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "date"], name="readiness_unique_owner_date"),
            models.CheckConstraint(
                condition=(
                    models.Q(sleep_quality__gte=1, sleep_quality__lte=5)
                    & models.Q(stress_level__gte=1, stress_level__lte=5)
                    & models.Q(soreness_overall__gte=1, soreness_overall__lte=5)
                ),
                name="readiness_1_to_5",
            ),
        ]

    def __str__(self) -> str:
        return f"Readiness {self.date} ({self.owner.email})"

    @property
    def readiness_score(self) -> float:
        """Combined 1–5: sleep is good, stress + soreness are bad, average."""
        return (self.sleep_quality + (6 - self.stress_level) + (6 - self.soreness_overall)) / 3.0


class FatigueAdjustment(OwnedMixin, TimestampedModel):
    """Manual +/- override stacked on top of the computed fatigue for one muscle
    on one day. Lets the user say 'no, my chest is more cooked than the math
    thinks' (positive delta) or 'I'm fresh, ignore yesterday' (negative)."""

    date = models.DateField(db_index=True)
    muscle_slug = models.CharField(max_length=40)
    delta = models.FloatField(help_text="Sets-equivalent units; can be negative.")

    objects = OwnerScopedQuerySet.as_manager()

    class Meta:
        ordering = ["-date", "muscle_slug"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "date", "muscle_slug"],
                name="fatigue_adjust_unique_owner_date_muscle",
            )
        ]

    def __str__(self) -> str:
        sign = "+" if self.delta >= 0 else ""
        return f"{self.muscle_slug} {sign}{self.delta:g} on {self.date} ({self.owner.email})"


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
