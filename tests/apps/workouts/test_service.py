"""Tests for the workouts orchestration service."""
from __future__ import annotations

from decimal import Decimal

import pytest

from gymapp.apps.routines.models import Routine, RoutineDay, RoutineExercise
from gymapp.apps.workouts.models import SetLog, WorkoutSession, WorkoutStatus
from gymapp.services import workouts as workouts_service

from tests.factories import EquipmentFactory, ExerciseFactory, UserFactory


@pytest.fixture
def alice(db):
    return UserFactory(email="alice@example.com")


@pytest.fixture
def bench(db):
    return ExerciseFactory(slug="bench-press", equipment=EquipmentFactory(slug="barbell"))


@pytest.mark.django_db
def test_start_session_without_routine_day(alice):
    session = workouts_service.start_session(alice)
    assert session.owner_id == alice.id
    assert session.status == WorkoutStatus.IN_PROGRESS
    assert session.source_routine_day_id is None
    assert session.exercise_logs.count() == 0


@pytest.mark.django_db
def test_start_session_from_routine_day_populates_logs(alice, bench):
    routine = Routine.objects.create(owner=alice, name="PPL")
    day = RoutineDay.objects.create(routine=routine, label="Push A")
    RoutineExercise.objects.create(
        routine_day=day,
        exercise=bench,
        target_sets=3,
        target_reps_low=6,
        target_reps_high=8,
        target_weight_kg=Decimal("100.00"),
    )

    session = workouts_service.start_session(alice, routine_day=day)

    assert session.exercise_logs.count() == 1
    elog = session.exercise_logs.first()
    assert elog.exercise_id == bench.id
    assert elog.set_logs.count() == 3
    for s in elog.set_logs.all():
        assert s.weight_kg == Decimal("100.00")
        assert s.reps == 6
        assert s.completed_at is None


@pytest.mark.django_db
def test_start_session_rejects_other_users_routine_day(alice, bench):
    bob = UserFactory(email="bob@example.com")
    routine = Routine.objects.create(owner=bob, name="Upper/Lower")
    day = RoutineDay.objects.create(routine=routine, label="Upper")

    with pytest.raises(PermissionError):
        workouts_service.start_session(alice, routine_day=day)


@pytest.mark.django_db
def test_complete_set_marks_completed_at_and_records_values(alice, bench):
    session = workouts_service.start_session(alice)
    elog = session.exercise_logs.create(exercise=bench, ordering=0)
    s = elog.set_logs.create(ordering=0)

    workouts_service.complete_set(s, weight_kg=Decimal("80"), reps=8)
    s.refresh_from_db()
    assert s.is_complete
    assert s.weight_kg == Decimal("80")
    assert s.reps == 8


@pytest.mark.django_db
def test_complete_set_is_idempotent_for_completed_at(alice, bench):
    session = workouts_service.start_session(alice)
    elog = session.exercise_logs.create(exercise=bench, ordering=0)
    s = elog.set_logs.create(ordering=0)

    workouts_service.complete_set(s, weight_kg=Decimal("80"), reps=8)
    first = s.completed_at
    workouts_service.complete_set(s, weight_kg=Decimal("85"), reps=10)
    s.refresh_from_db()
    assert s.completed_at == first  # unchanged
    assert s.weight_kg == Decimal("85")
    assert s.reps == 10


@pytest.mark.django_db
def test_update_set_values_does_not_complete(alice, bench):
    session = workouts_service.start_session(alice)
    elog = session.exercise_logs.create(exercise=bench, ordering=0)
    s = elog.set_logs.create(ordering=0)

    workouts_service.update_set_values(s, weight_kg=Decimal("60"), reps=12)
    s.refresh_from_db()
    assert s.weight_kg == Decimal("60")
    assert s.is_complete is False


@pytest.mark.django_db
def test_swap_exercise_replaces_when_no_sets_completed(alice, bench):
    other = ExerciseFactory(slug="dumbbell-bench-press", equipment=bench.equipment)
    session = workouts_service.start_session(alice)
    elog = session.exercise_logs.create(exercise=bench, ordering=0)
    elog.set_logs.create(ordering=0)

    workouts_service.swap_exercise(elog, new_exercise=other)
    elog.refresh_from_db()
    assert elog.exercise_id == other.id


@pytest.mark.django_db
def test_swap_exercise_refuses_when_a_set_is_complete(alice, bench):
    other = ExerciseFactory(slug="dumbbell-bench-press", equipment=bench.equipment)
    session = workouts_service.start_session(alice)
    elog = session.exercise_logs.create(exercise=bench, ordering=0)
    s = elog.set_logs.create(ordering=0)
    workouts_service.complete_set(s, weight_kg=Decimal("80"), reps=8)

    with pytest.raises(ValueError):
        workouts_service.swap_exercise(elog, new_exercise=other)


@pytest.mark.django_db
def test_finish_session_sets_finished_status_and_timestamp(alice):
    session = workouts_service.start_session(alice)
    workouts_service.finish_session(session)
    session.refresh_from_db()
    assert session.status == WorkoutStatus.FINISHED
    assert session.finished_at is not None


@pytest.mark.django_db
def test_session_progress_counts_working_sets_only(alice, bench):
    session = workouts_service.start_session(alice)
    elog = session.exercise_logs.create(exercise=bench, ordering=0)
    elog.set_logs.create(ordering=0, is_warmup=True)
    s1 = elog.set_logs.create(ordering=1)
    s2 = elog.set_logs.create(ordering=2)
    workouts_service.complete_set(s1, weight_kg=Decimal("80"), reps=8)

    progress = workouts_service.session_progress(session)
    assert progress == {"completed": 1, "total": 2}


@pytest.mark.django_db
def test_workout_session_owner_scoping(alice):
    bob = UserFactory(email="bob@example.com")
    workouts_service.start_session(alice)
    workouts_service.start_session(bob)

    assert WorkoutSession.objects.for_user(alice).count() == 1
    assert WorkoutSession.objects.for_user(bob).count() == 1
