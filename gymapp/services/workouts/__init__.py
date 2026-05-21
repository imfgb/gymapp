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
    """Mark a session finished and trigger PR auto-detection."""
    from gymapp.services.prs import update_prs_from_session

    session.status = WorkoutStatus.FINISHED
    session.finished_at = finished_at or timezone.now()
    session.save()
    update_prs_from_session(session)
    return session


def session_progress(session: WorkoutSession) -> dict[str, int]:
    """Return {completed, total} counts of working (non-warmup) sets. Used by
    the session view to render a progress bar."""
    sets = SetLog.objects.filter(exercise_log__session=session, is_warmup=False)
    total = sets.count()
    completed = sets.filter(completed_at__isnull=False).count()
    return {"completed": completed, "total": total}


DEFAULT_SETS_ON_ADD = 3


@transaction.atomic
def add_exercise_to_session(
    session: WorkoutSession,
    *,
    exercise: Exercise,
    sets_count: int = DEFAULT_SETS_ON_ADD,
) -> ExerciseLog:
    """Append an ExerciseLog (with N empty SetLogs) to an in-progress session."""
    next_order = session.exercise_logs.count()
    elog = ExerciseLog.objects.create(
        session=session, exercise=exercise, ordering=next_order
    )
    for i in range(sets_count):
        SetLog.objects.create(exercise_log=elog, ordering=i)
    return elog


@transaction.atomic
def add_custom_exercise_and_use(
    session: WorkoutSession,
    *,
    name: str,
    equipment_slug: str,
    primary_muscle_slugs: list[str] | None = None,
    sets_count: int = DEFAULT_SETS_ON_ADD,
) -> tuple[Exercise, ExerciseLog]:
    """Create a per-user custom Exercise (owner=session.owner) and immediately
    add it to the session. Useful when the user types a name we don't have.

    Raises `ValueError` if the user already owns an exercise with the same
    generated slug.
    """
    from django.utils.text import slugify

    from gymapp.apps.exercises.models import Equipment, MuscleGroup

    name = name.strip()
    if not name:
        raise ValueError("Exercise name is required.")
    equipment = Equipment.objects.get(slug=equipment_slug)

    slug = slugify(name)[:80]
    if not slug:
        raise ValueError("Name did not produce a valid slug.")

    if Exercise.objects.filter(owner=session.owner, slug=slug).exists():
        raise ValueError(f"You already have a custom exercise with slug '{slug}'.")

    exercise = Exercise.objects.create(
        owner=session.owner,
        slug=slug,
        name=name,
        equipment=equipment,
        category="compound",
    )
    if primary_muscle_slugs:
        muscles = MuscleGroup.objects.filter(slug__in=primary_muscle_slugs)
        exercise.primary_muscles.set(muscles)

    elog = add_exercise_to_session(session, exercise=exercise, sets_count=sets_count)
    return exercise, elog


@transaction.atomic
def add_set_to_exercise(exercise_log: ExerciseLog) -> SetLog:
    """Append one empty SetLog to an ExerciseLog."""
    next_order = exercise_log.set_logs.count()
    return SetLog.objects.create(exercise_log=exercise_log, ordering=next_order)


@transaction.atomic
def delete_set(set_log: SetLog) -> None:
    """Remove a SetLog. Allowed in any state (including completed) — useful for
    correcting mistakes mid-workout."""
    set_log.delete()


@transaction.atomic
def delete_exercise_log(exercise_log: ExerciseLog) -> None:
    """Remove an ExerciseLog and all its SetLogs from the session."""
    exercise_log.delete()
