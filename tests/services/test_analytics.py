"""Tests for the analytics service (weekly volume + sets per muscle)."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from gymapp.apps.workouts.models import ExerciseLog, SetLog, WorkoutSession, WorkoutStatus
from gymapp.services.analytics import sets_by_muscle, weekly_volume
from tests.factories import EquipmentFactory, ExerciseFactory, MuscleGroupFactory, UserFactory


def _aware(d):
    return timezone.make_aware(datetime(d.year, d.month, d.day, 12, 0))


def _session(owner, day, sets, *, status=WorkoutStatus.FINISHED):
    """sets: list of (exercise, weight, reps, is_warmup, completed)."""
    s = WorkoutSession.objects.create(
        owner=owner, started_at=_aware(day), finished_at=_aware(day), status=status
    )
    by_ex = {}
    for ex, weight, reps, warmup, completed in sets:
        el = by_ex.get(ex.id)
        if el is None:
            el = ExerciseLog.objects.create(session=s, exercise=ex, ordering=len(by_ex))
            by_ex[ex.id] = el
        SetLog.objects.create(
            exercise_log=el,
            ordering=el.set_logs.count(),
            weight_kg=weight,
            reps=reps,
            is_warmup=warmup,
            completed_at=_aware(day) if completed else None,
        )
    return s


@pytest.fixture
def alice(db):
    return UserFactory(email="analytics@example.com")


@pytest.fixture
def chest(clean_catalog):
    return MuscleGroupFactory(slug="chest", name="Pecho")


@pytest.fixture
def back(clean_catalog):
    return MuscleGroupFactory(slug="back", name="Espalda")


@pytest.fixture
def bench(chest):
    ex = ExerciseFactory(slug="bench", equipment=EquipmentFactory(slug="barbell"))
    ex.primary_muscles.add(chest)
    return ex


@pytest.fixture
def row(back):
    ex = ExerciseFactory(slug="row", equipment=EquipmentFactory(slug="barbell"))
    ex.primary_muscles.add(back)
    return ex


# ---------------------------------------------------------------------------
# weekly_volume
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_weekly_volume_returns_n_weeks_oldest_first(alice):
    out = weekly_volume(alice, weeks=8, today=timezone.localdate())
    assert len(out) == 8
    assert out[0].week_start < out[-1].week_start


@pytest.mark.django_db
def test_weekly_volume_sums_completed_working_sets(alice, bench):
    today = timezone.localdate()
    _session(
        alice,
        today,
        [
            (bench, Decimal("100"), 5, False, True),   # 500
            (bench, Decimal("100"), 5, False, True),   # 500
            (bench, Decimal("40"), 10, True, True),    # warmup excluded
            (bench, Decimal("100"), 5, False, False),  # incomplete excluded
        ],
    )
    out = weekly_volume(alice, weeks=4, today=today)
    assert out[-1].volume_kg == 1000
    assert out[-1].sets == 2


@pytest.mark.django_db
def test_weekly_volume_buckets_into_correct_week(alice, bench):
    today = timezone.localdate()
    last_week = today - timedelta(days=7)
    _session(alice, today, [(bench, Decimal("50"), 10, False, True)])       # 500 this wk
    _session(alice, last_week, [(bench, Decimal("60"), 10, False, True)])   # 600 last wk
    out = {p.week_start: p for p in weekly_volume(alice, weeks=4, today=today)}
    from gymapp.services.analytics import _monday

    assert out[_monday(today)].volume_kg == 500
    assert out[_monday(last_week)].volume_kg == 600


@pytest.mark.django_db
def test_weekly_volume_ignores_unfinished_sessions(alice, bench):
    today = timezone.localdate()
    _session(
        alice, today,
        [(bench, Decimal("100"), 5, False, True)],
        status=WorkoutStatus.IN_PROGRESS,
    )
    out = weekly_volume(alice, weeks=2, today=today)
    assert all(p.volume_kg == 0 for p in out)


# ---------------------------------------------------------------------------
# sets_by_muscle
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_sets_by_muscle_attributes_to_primary(alice, bench, row):
    today = timezone.localdate()
    _session(
        alice, today,
        [
            (bench, Decimal("100"), 5, False, True),
            (bench, Decimal("100"), 5, False, True),
            (row, Decimal("80"), 8, False, True),
        ],
    )
    out = {m.muscle: m for m in sets_by_muscle(alice, today=today)}
    assert out["Pecho"].sets == 2
    assert out["Pecho"].volume_kg == 1000
    assert out["Espalda"].sets == 1
    # busiest muscle first
    assert sets_by_muscle(alice, today=today)[0].muscle == "Pecho"


@pytest.mark.django_db
def test_sets_by_muscle_only_current_week(alice, bench):
    today = timezone.localdate()
    _session(alice, today - timedelta(days=8), [(bench, Decimal("100"), 5, False, True)])
    assert sets_by_muscle(alice, today=today) == []
