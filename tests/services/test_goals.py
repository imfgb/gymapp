"""Tests for the monthly goal progress service."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from gymapp.apps.metrics.models import MonthlyGoal, UserMetricSnapshot
from gymapp.apps.workouts.models import ExerciseLog, SetLog, WorkoutSession, WorkoutStatus
from gymapp.services.goals import (
    current_goal,
    get_or_create_current,
    month_bounds,
    monthly_goal_progress,
)
from tests.factories import ExerciseFactory, UserFactory


def _aware(y, m, d, hour=12):
    return timezone.make_aware(datetime(y, m, d, hour, 0))


def _finished_session(owner, started_at, sets):
    """Build a FINISHED session with one exercise and the given set specs.

    Each spec: (weight_kg|None, reps|None, is_warmup, completed).
    """
    session = WorkoutSession.objects.create(
        owner=owner,
        started_at=started_at,
        finished_at=started_at,
        status=WorkoutStatus.FINISHED,
    )
    elog = ExerciseLog.objects.create(session=session, exercise=ExerciseFactory(), ordering=0)
    for i, (weight, reps, warmup, completed) in enumerate(sets):
        SetLog.objects.create(
            exercise_log=elog,
            ordering=i,
            weight_kg=weight,
            reps=reps,
            is_warmup=warmup,
            completed_at=started_at if completed else None,
        )
    return session


@pytest.fixture
def alice(db):
    return UserFactory(email="goalsa@example.com")


# ---------------------------------------------------------------------------
# month_bounds
# ---------------------------------------------------------------------------


def test_month_bounds_mid_year():
    start, end = month_bounds(2026, 3)
    assert start.isoformat() == "2026-03-01"
    assert end.isoformat() == "2026-04-01"


def test_month_bounds_december_rolls_to_next_year():
    start, end = month_bounds(2026, 12)
    assert start.isoformat() == "2026-12-01"
    assert end.isoformat() == "2027-01-01"


# ---------------------------------------------------------------------------
# monthly_goal_progress
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_no_targets_yields_no_rows(alice):
    goal = MonthlyGoal.objects.create(owner=alice, year=2026, month=3)
    assert monthly_goal_progress(goal) == []


@pytest.mark.django_db
def test_session_target_counts_finished_sessions_in_month(alice):
    goal = MonthlyGoal.objects.create(owner=alice, year=2026, month=3, target_sessions=4)
    for d in (3, 10, 17):
        _finished_session(alice, _aware(2026, 3, d), [(Decimal("50"), 10, False, True)])
    # A session in another month must not count.
    _finished_session(alice, _aware(2026, 2, 20), [(Decimal("50"), 10, False, True)])

    rows = {m.key: m for m in monthly_goal_progress(goal)}
    assert rows["sessions"].actual == 3
    assert rows["sessions"].target == 4
    assert rows["sessions"].pct == 75
    assert rows["sessions"].reached is False


@pytest.mark.django_db
def test_session_target_reached_caps_at_100(alice):
    goal = MonthlyGoal.objects.create(owner=alice, year=2026, month=3, target_sessions=2)
    for d in (1, 8, 15):
        _finished_session(alice, _aware(2026, 3, d), [(Decimal("50"), 10, False, True)])
    row = monthly_goal_progress(goal)[0]
    assert row.actual == 3
    assert row.reached is True
    assert row.pct == 100


@pytest.mark.django_db
def test_volume_target_sums_completed_working_sets_only(alice):
    goal = MonthlyGoal.objects.create(
        owner=alice, year=2026, month=3, target_volume_kg=Decimal("2000")
    )
    _finished_session(
        alice,
        _aware(2026, 3, 5),
        [
            (Decimal("100"), 5, False, True),   # 500 — counts
            (Decimal("100"), 5, False, True),   # 500 — counts
            (Decimal("40"), 10, True, True),    # warmup — excluded
            (Decimal("100"), 5, False, False),  # not completed — excluded
        ],
    )
    row = monthly_goal_progress(goal)[0]
    assert row.actual == Decimal("1000")
    assert row.target == Decimal("2000")
    assert row.pct == 50
    assert row.reached is False


@pytest.mark.django_db
def test_only_set_targets_produce_rows(alice):
    goal = MonthlyGoal.objects.create(owner=alice, year=2026, month=3, target_sessions=5)
    rows = monthly_goal_progress(goal)
    assert [m.key for m in rows] == ["sessions"]


@pytest.mark.django_db
def test_bodyweight_progress_from_baseline_toward_target(alice):
    goal = MonthlyGoal.objects.create(
        owner=alice, year=2026, month=3, target_bodyweight_kg=Decimal("75")
    )
    # Started the month at 80, now at 77.5 → halfway through a 5 kg cut.
    UserMetricSnapshot.objects.create(
        owner=alice, measured_at=_aware(2026, 2, 15), weight_kg=Decimal("80")
    )
    UserMetricSnapshot.objects.create(
        owner=alice, measured_at=_aware(2026, 3, 10), weight_kg=Decimal("77.5")
    )
    row = monthly_goal_progress(goal)[0]
    assert row.key == "bodyweight"
    assert row.actual == Decimal("77.5")
    assert row.pct == 50
    assert row.reached is False


@pytest.mark.django_db
def test_bodyweight_reached_within_half_kg(alice):
    goal = MonthlyGoal.objects.create(
        owner=alice, year=2026, month=3, target_bodyweight_kg=Decimal("75")
    )
    UserMetricSnapshot.objects.create(
        owner=alice, measured_at=_aware(2026, 3, 10), weight_kg=Decimal("75.2")
    )
    row = monthly_goal_progress(goal)[0]
    assert row.reached is True
    assert row.pct == 100


@pytest.mark.django_db
def test_bodyweight_wrong_direction_is_zero(alice):
    goal = MonthlyGoal.objects.create(
        owner=alice, year=2026, month=3, target_bodyweight_kg=Decimal("75")
    )
    UserMetricSnapshot.objects.create(
        owner=alice, measured_at=_aware(2026, 2, 15), weight_kg=Decimal("80")
    )
    # Moved away from the target (gained instead of cut).
    UserMetricSnapshot.objects.create(
        owner=alice, measured_at=_aware(2026, 3, 10), weight_kg=Decimal("82")
    )
    row = monthly_goal_progress(goal)[0]
    assert row.pct == 0
    assert row.reached is False


# ---------------------------------------------------------------------------
# current_goal / get_or_create_current
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_current_goal_returns_none_when_unset(alice):
    assert current_goal(alice, _aware(2026, 3, 1).date()) is None


@pytest.mark.django_db
def test_get_or_create_current_is_idempotent(alice):
    today = _aware(2026, 3, 1).date()
    g1 = get_or_create_current(alice, today)
    g2 = get_or_create_current(alice, today)
    assert g1.pk == g2.pk
    assert MonthlyGoal.objects.filter(owner=alice).count() == 1
