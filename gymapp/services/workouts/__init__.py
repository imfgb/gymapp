"""Workouts orchestration service.

Encapsulates the multi-model writes (start a session from a routine day,
complete a set, swap an exercise, finish a session) so views stay thin and
the logic is testable without HTTP.

These are plain functions for now — no Strategy/Protocol yet because there's
no AI-driven variant on the horizon. Phase 4 may extract a Protocol if
LLM-driven session orchestration ever materialises.
"""
from __future__ import annotations

from datetime import datetime

from django.db import transaction
from django.utils import timezone

from gymapp.apps.exercises.models import Exercise
from gymapp.apps.routines.models import RoutineDay
from gymapp.apps.workouts.models import (
    ExerciseLog,
    SetLog,
    WorkoutSession,
    WorkoutStatus,
)


@transaction.atomic
def start_session(
    owner,
    *,
    routine_day: RoutineDay | None = None,
    started_at: datetime | None = None,
) -> WorkoutSession:
    """Create an in-progress session.

    If `routine_day` is given, pre-populates ExerciseLogs + empty SetLogs from
    the routine plan. Otherwise creates a bare session the user can add
    exercises to ad-hoc.
    """
    if routine_day is not None and routine_day.routine.owner_id != owner.id:
        raise PermissionError("Routine day does not belong to this user.")

    session = WorkoutSession.objects.create(
        owner=owner,
        started_at=started_at or timezone.now(),
        status=WorkoutStatus.IN_PROGRESS,
        source_routine_day=routine_day,
    )

    if routine_day is not None:
        for idx, rex in enumerate(
            routine_day.exercises.select_related("exercise").order_by("ordering", "id")
        ):
            elog = ExerciseLog.objects.create(
                session=session, exercise=rex.exercise, ordering=idx
            )
            for set_idx in range(rex.target_sets):
                SetLog.objects.create(
                    exercise_log=elog,
                    ordering=set_idx,
                    weight_kg=rex.target_weight_kg,
                    reps=rex.target_reps_low,  # prescribed target; user edits before completing
                )

    return session


@transaction.atomic
def complete_set(
    set_log: SetLog,
    *,
    weight_kg=None,
    reps: int | None = None,
    rpe=None,
    completed_at: datetime | None = None,
) -> SetLog:
    """Mark a set complete. Optionally overwrite the prescribed values with
    what was actually performed. Idempotent: re-calling on an already-complete
    set updates the values but leaves `completed_at` unchanged."""
    if weight_kg is not None:
        set_log.weight_kg = weight_kg
    if reps is not None:
        set_log.reps = reps
    if rpe is not None:
        set_log.rpe = rpe
    if set_log.completed_at is None:
        set_log.completed_at = completed_at or timezone.now()
    set_log.save()
    return set_log


@transaction.atomic
def update_set_values(
    set_log: SetLog, *, weight_kg=None, reps: int | None = None, rpe=None
) -> SetLog:
    """Edit a set's values without changing its completion state."""
    if weight_kg is not None:
        set_log.weight_kg = weight_kg
    if reps is not None:
        set_log.reps = reps
    if rpe is not None:
        set_log.rpe = rpe
    set_log.save()
    return set_log


@transaction.atomic
def swap_exercise(exercise_log: ExerciseLog, *, new_exercise: Exercise) -> ExerciseLog:
    """Replace the exercise on an in-progress ExerciseLog. Refuses if any set
    is already completed (those reps were performed on the old exercise)."""
    if exercise_log.set_logs.filter(completed_at__isnull=False).exists():
        raise ValueError("Cannot swap an exercise that already has completed sets.")
    exercise_log.exercise = new_exercise
    exercise_log.save()
    return exercise_log


@transaction.atomic
def finish_session(
    session: WorkoutSession, *, finished_at: datetime | None = None
) -> WorkoutSession:
    """Mark a session finished. PR detection will hook in here once `prs` lands."""
    session.status = WorkoutStatus.FINISHED
    session.finished_at = finished_at or timezone.now()
    session.save()
    return session


def session_progress(session: WorkoutSession) -> dict[str, int]:
    """Return {completed, total} counts of working (non-warmup) sets. Used by
    the session view to render a progress bar."""
    sets = SetLog.objects.filter(exercise_log__session=session, is_warmup=False)
    total = sets.count()
    completed = sets.filter(completed_at__isnull=False).count()
    return {"completed": completed, "total": total}
