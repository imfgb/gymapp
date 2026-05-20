"""Tests for routines models.

Cover owner scoping, name uniqueness per owner, weekday uniqueness per owner,
and the reps_low <= reps_high CHECK constraint.
"""
from __future__ import annotations

import pytest
from django.db import IntegrityError
from django.db.utils import IntegrityError as DBIntegrityError

from gymapp.apps.routines.models import Routine, RoutineDay, RoutineExercise, WeeklySplit

from tests.factories import EquipmentFactory, ExerciseFactory, UserFactory


@pytest.fixture
def alice(db):
    return UserFactory(email="alice@example.com")


@pytest.fixture
def bob(db):
    return UserFactory(email="bob@example.com")


@pytest.mark.django_db
def test_routine_for_user_returns_only_user_rows(alice, bob):
    Routine.objects.create(owner=alice, name="PPL")
    Routine.objects.create(owner=bob, name="Upper/Lower")

    alice_rows = list(Routine.objects.for_user(alice).values_list("name", flat=True))
    bob_rows = list(Routine.objects.for_user(bob).values_list("name", flat=True))

    assert alice_rows == ["PPL"]
    assert bob_rows == ["Upper/Lower"]


@pytest.mark.django_db
def test_routine_name_unique_per_owner(alice, bob):
    Routine.objects.create(owner=alice, name="PPL")
    Routine.objects.create(owner=bob, name="PPL")  # different owner, OK

    with pytest.raises((IntegrityError, DBIntegrityError)):
        Routine.objects.create(owner=alice, name="PPL")


@pytest.mark.django_db
def test_weekly_split_unique_per_weekday(alice):
    routine = Routine.objects.create(owner=alice, name="PPL")
    day = RoutineDay.objects.create(routine=routine, label="Push A")

    WeeklySplit.objects.create(owner=alice, weekday=0, routine_day=day)
    with pytest.raises((IntegrityError, DBIntegrityError)):
        WeeklySplit.objects.create(owner=alice, weekday=0, routine_day=day)


@pytest.mark.django_db
def test_weekly_split_rest_day_allowed(alice):
    # NULL routine_day means rest day; multiple weekdays with no routine is fine.
    WeeklySplit.objects.create(owner=alice, weekday=5, routine_day=None)
    WeeklySplit.objects.create(owner=alice, weekday=6, routine_day=None)
    assert WeeklySplit.objects.for_user(alice).count() == 2


@pytest.mark.django_db
def test_routine_exercise_reps_low_must_be_lte_high(alice):
    routine = Routine.objects.create(owner=alice, name="PPL")
    day = RoutineDay.objects.create(routine=routine, label="Push A")
    eq = EquipmentFactory()
    bench = ExerciseFactory(slug="bench-press", equipment=eq)

    # Valid
    RoutineExercise.objects.create(
        routine_day=day,
        exercise=bench,
        target_sets=4,
        target_reps_low=6,
        target_reps_high=10,
    )

    # low > high -> CHECK constraint violation
    with pytest.raises((IntegrityError, DBIntegrityError)):
        RoutineExercise.objects.create(
            routine_day=day,
            exercise=bench,
            target_sets=4,
            target_reps_low=12,
            target_reps_high=8,
        )


@pytest.mark.django_db
def test_routine_cascade_deletes_days_and_exercises(alice):
    routine = Routine.objects.create(owner=alice, name="PPL")
    day = RoutineDay.objects.create(routine=routine, label="Push A")
    eq = EquipmentFactory()
    bench = ExerciseFactory(slug="bench-press", equipment=eq)
    RoutineExercise.objects.create(
        routine_day=day,
        exercise=bench,
        target_sets=4,
        target_reps_low=6,
        target_reps_high=10,
    )

    routine.delete()
    assert RoutineDay.objects.count() == 0
    assert RoutineExercise.objects.count() == 0


@pytest.mark.django_db
def test_weekly_split_clears_when_routine_day_deleted(alice):
    routine = Routine.objects.create(owner=alice, name="PPL")
    day = RoutineDay.objects.create(routine=routine, label="Push A")
    split = WeeklySplit.objects.create(owner=alice, weekday=0, routine_day=day)

    day.delete()
    split.refresh_from_db()
    assert split.routine_day_id is None  # SET_NULL preserves the split row
