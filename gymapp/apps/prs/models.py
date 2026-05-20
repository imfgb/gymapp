"""Personal records.

One row per (owner, exercise, reps) holds the user's best weight at that
rep count. Auto-detected from finished SetLogs by the PR service; manually
overridable via the admin and the user-facing edit view.

Warm-up sets are ignored (`SetLog.is_warmup=True`).
"""
from __future__ import annotations

from django.db import models

from gymapp.apps.core.models import OwnedMixin, OwnerScopedQuerySet, TimestampedModel
from gymapp.apps.exercises.models import Exercise


class PRSource(models.TextChoices):
    AUTO = "auto", "Auto-detected"
    MANUAL = "manual", "Manually entered"


class PersonalRecord(OwnedMixin, TimestampedModel):
    exercise = models.ForeignKey(
        Exercise, on_delete=models.PROTECT, related_name="personal_records"
    )
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2)
    reps = models.PositiveSmallIntegerField()
    achieved_at = models.DateTimeField(db_index=True)
    source = models.CharField(
        max_length=8, choices=PRSource.choices, default=PRSource.AUTO
    )
    source_set = models.ForeignKey(
        "workouts.SetLog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="became_prs",
        help_text="The SetLog that created/last-updated this PR. NULL for manual entries.",
    )

    objects = OwnerScopedQuerySet.as_manager()

    class Meta:
        ordering = ["exercise", "reps"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "exercise", "reps"],
                name="prs_unique_per_owner_exercise_reps",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.exercise.name}: {self.weight_kg}kg × {self.reps}"
