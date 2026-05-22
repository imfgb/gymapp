"""Workout sessions.

A `WorkoutSession` is an actual training day. It can be **planned** (created
from today's `WeeklySplit` row) or **ad-hoc** (`source_routine_day` is NULL).
Each session has many `ExerciseLog`s, each with many `SetLog`s.

`SetLog.completed_at` is the heart of the tap-to-complete checklist UX
(decision #18): NULL = pending; not-NULL = done. Editing a set's
weight/reps after completion is allowed; uncompleting is not (delete instead).

Warm-up sets carry `is_warmup=True` and never count toward PRs or volume
rollups.
"""

from __future__ import annotations

from django.db import models

from gymapp.apps.core.models import OwnedMixin, OwnerScopedQuerySet, TimestampedModel
from gymapp.apps.exercises.models import Exercise
from gymapp.apps.routines.models import RoutineDay


class WorkoutStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", "In progress"
    FINISHED = "finished", "Finished"
    ABANDONED = "abandoned", "Abandoned"


class WorkoutSession(OwnedMixin, TimestampedModel):
    started_at = models.DateTimeField(db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=12, choices=WorkoutStatus.choices, default=WorkoutStatus.IN_PROGRESS
    )
    source_routine_day = models.ForeignKey(
        RoutineDay,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
        help_text="NULL = ad-hoc session not tied to a planned routine day.",
    )
    notes = models.TextField(blank=True)

    objects = OwnerScopedQuerySet.as_manager()

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"Session {self.id} :: {self.owner.email} :: {self.started_at:%Y-%m-%d}"

    @property
    def is_active(self) -> bool:
        return self.status == WorkoutStatus.IN_PROGRESS


class ExerciseLog(models.Model):
    session = models.ForeignKey(
        WorkoutSession, on_delete=models.CASCADE, related_name="exercise_logs"
    )
    exercise = models.ForeignKey(Exercise, on_delete=models.PROTECT, related_name="session_logs")
    ordering = models.PositiveSmallIntegerField(default=0)
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["session", "ordering", "id"]

    def __str__(self) -> str:
        return f"{self.exercise.name} in session #{self.session_id}"


class SetLog(models.Model):
    exercise_log = models.ForeignKey(
        ExerciseLog, on_delete=models.CASCADE, related_name="set_logs", db_index=True
    )
    ordering = models.PositiveSmallIntegerField(default=0)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    reps = models.PositiveSmallIntegerField(null=True, blank=True)
    rpe = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    is_warmup = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["exercise_log", "ordering", "id"]

    def __str__(self) -> str:
        marker = "✓" if self.completed_at else " "
        return f"[{marker}] {self.weight_kg}kg × {self.reps}"

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None
