"""Routines & WeeklySplit.

`Routine` is a user-owned workout template (e.g. "PPL 6-day").
A `Routine` has many `RoutineDay`s (e.g. "Push A", "Pull A", "Legs A",
"Push B", "Pull B", "Legs B"). Each `RoutineDay` has many `RoutineExercise`s
prescribing target sets/reps/weight/rest.

`WeeklySplit` is the (owner, weekday) → RoutineDay map. One row per weekday;
NULL `routine_day` means rest day. A user has one weekly split (the rule is
enforced by the unique `(owner, weekday)` constraint and the fact that we
upsert on weekday).

Weekday integer: 0=Mon … 6=Sun (Python `datetime.weekday()` convention).
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from gymapp.apps.core.models import OwnedMixin, OwnerScopedQuerySet, TimestampedModel
from gymapp.apps.exercises.models import Exercise


class Weekday(models.IntegerChoices):
    MONDAY = 0, "Monday"
    TUESDAY = 1, "Tuesday"
    WEDNESDAY = 2, "Wednesday"
    THURSDAY = 3, "Thursday"
    FRIDAY = 4, "Friday"
    SATURDAY = 5, "Saturday"
    SUNDAY = 6, "Sunday"


class Routine(OwnedMixin, TimestampedModel):
    name = models.CharField(max_length=120)
    training_style = models.CharField(
        max_length=20,
        blank=True,
        help_text=(
            "Snapshot of the user's training_style at routine creation. "
            "Updates to the user's profile don't backfill here."
        ),
    )
    notes = models.TextField(blank=True)
    is_archived = models.BooleanField(default=False)

    objects = OwnerScopedQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "name"], name="routines_unique_name_per_owner"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class RoutineDay(TimestampedModel):
    routine = models.ForeignKey(Routine, on_delete=models.CASCADE, related_name="days")
    label = models.CharField(max_length=60, help_text="e.g. 'Push A', 'Lower'")
    ordering = models.PositiveSmallIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["routine", "ordering", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["routine", "label"], name="routines_unique_day_label_per_routine"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.routine.name} :: {self.label}"


class RoutineExercise(models.Model):
    routine_day = models.ForeignKey(RoutineDay, on_delete=models.CASCADE, related_name="exercises")
    exercise = models.ForeignKey(Exercise, on_delete=models.PROTECT, related_name="routine_uses")
    ordering = models.PositiveSmallIntegerField(default=0)

    target_sets = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(50)]
    )
    target_reps_low = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    target_reps_high = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    target_weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    rest_seconds = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Override; falls back to Profile.default_rest_seconds when NULL.",
    )
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["routine_day", "ordering", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(target_reps_low__lte=models.F("target_reps_high")),
                name="routines_reps_low_lte_high",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.routine_day.label} :: {self.exercise.name} ({self.target_sets}×)"


class SkippedDay(OwnedMixin, TimestampedModel):
    """A specific calendar date the user marked as 'no gym'.

    The recurring `WeeklySplit` is the user's intent; a `SkippedDay` is a one-off
    override. The dashboard uses it to slide the week's planned workouts forward
    so a skipped day's session isn't lost — it moves to the next open day.
    """

    date = models.DateField(db_index=True)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "date"], name="routines_unique_skipped_day_per_owner"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.owner.email} skipped {self.date}"


class WeeklySplit(TimestampedModel):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="weekly_splits"
    )
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    routine_day = models.ForeignKey(
        RoutineDay,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduled_in",
        help_text="NULL = rest day.",
    )

    objects = OwnerScopedQuerySet.as_manager()

    class Meta:
        ordering = ["owner", "weekday"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "weekday"], name="routines_unique_weekday_per_owner"
            ),
        ]

    def __str__(self) -> str:
        label = self.routine_day.label if self.routine_day_id else "Rest"
        return f"{self.get_weekday_display()}: {label}"
