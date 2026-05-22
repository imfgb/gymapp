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

# Equipment whose exercises get warm-ups auto-generated on session start.
# Plate-loaded compound bars; accessory/isolation work is left to the manual
# "Calentamiento" button.
AUTO_WARMUP_EQUIPMENT = frozenset({"barbell", "smith"})


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
        from gymapp.services.progression import recommend_next

        for idx, rex in enumerate(
            routine_day.exercises.select_related("exercise__equipment").order_by("ordering", "id")
        ):
            elog = ExerciseLog.objects.create(session=session, exercise=rex.exercise, ordering=idx)
            rec = recommend_next(
                user=owner,
                exercise=rex.exercise,
                target_reps_low=rex.target_reps_low,
                target_reps_high=rex.target_reps_high,
                current_weight=rex.target_weight_kg,
            )
            for set_idx in range(rex.target_sets):
                SetLog.objects.create(
                    exercise_log=elog,
                    ordering=set_idx,
                    weight_kg=rec.weight_kg,
                    reps=rec.reps,
                )
            # Auto-generate warm-ups for barbell lifts that have a known working
            # weight; lighter accessory work stays warm-up-free unless the user
            # taps "Calentamiento" manually.
            if rec.weight_kg is not None and rex.exercise.equipment.slug in AUTO_WARMUP_EQUIPMENT:
                add_warmups_to_exercise(elog)

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
    elog = ExerciseLog.objects.create(session=session, exercise=exercise, ordering=next_order)
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
    from gymapp.services.exercise_library import create_custom_exercise

    exercise = create_custom_exercise(
        session.owner,
        name=name,
        equipment_slug=equipment_slug,
        primary_muscle_slugs=primary_muscle_slugs,
    )
    elog = add_exercise_to_session(session, exercise=exercise, sets_count=sets_count)
    return exercise, elog


@transaction.atomic
def add_set_to_exercise(exercise_log: ExerciseLog) -> SetLog:
    """Append one empty SetLog to an ExerciseLog."""
    next_order = exercise_log.set_logs.count()
    return SetLog.objects.create(exercise_log=exercise_log, ordering=next_order)


@transaction.atomic
def add_warmups_to_exercise(exercise_log: ExerciseLog) -> list[SetLog]:
    """(Re)generate warm-up sets for an exercise from its heaviest working set.

    Idempotent: existing warm-ups are dropped and rebuilt, so re-running after
    changing the working weight refreshes them. Warm-ups are inserted before the
    working sets and the whole list is renumbered contiguously. Returns the new
    warm-up SetLogs (empty if the working weight is unknown / too light).
    """
    from decimal import Decimal

    from gymapp.services.warmup import warmup_scheme

    exercise_log.set_logs.filter(is_warmup=True).delete()
    working = list(exercise_log.set_logs.filter(is_warmup=False).order_by("ordering", "id"))
    top_weight = max((s.weight_kg for s in working if s.weight_kg is not None), default=None)

    # A plate-loaded bar only moves in 2× the smallest plate (the user's smallest
    # plate is 2.5 kg → 5 kg total steps), so warm-up weights must snap to that to
    # be loadable. Non-bar equipment (dumbbell/machine/cable) uses 2.5 kg targets.
    plate_loaded = {
        "barbell": (Decimal("5"), Decimal("20")),
        "smith": (Decimal("5"), Decimal("20")),
        "ez-bar": (Decimal("5"), Decimal("10")),
    }
    increment, bar = plate_loaded.get(
        exercise_log.exercise.equipment.slug, (Decimal("2.5"), Decimal("0"))
    )
    scheme = warmup_scheme(top_weight, bar_weight=bar, increment=increment)
    created: list[SetLog] = []
    for idx, (weight, reps) in enumerate(scheme):
        created.append(
            SetLog.objects.create(
                exercise_log=exercise_log,
                ordering=idx,
                weight_kg=weight,
                reps=reps,
                is_warmup=True,
            )
        )
    offset = len(created)
    for j, set_log in enumerate(working):
        new_order = offset + j
        if set_log.ordering != new_order:
            set_log.ordering = new_order
            set_log.save(update_fields=["ordering"])
    return created


@transaction.atomic
def delete_set(set_log: SetLog) -> None:
    """Remove a SetLog and renumber siblings so ordering stays contiguous."""
    elog = set_log.exercise_log
    set_log.delete()
    for new_idx, sibling in enumerate(elog.set_logs.order_by("ordering", "id")):
        if sibling.ordering != new_idx:
            sibling.ordering = new_idx
            sibling.save(update_fields=["ordering"])


@transaction.atomic
def delete_exercise_log(exercise_log: ExerciseLog) -> None:
    """Remove an ExerciseLog and all its SetLogs from the session."""
    exercise_log.delete()
