"""Tests for the fatigue service.

Covers `compute_muscle_fatigue`, `current_readiness`, and `daily_advice`.
Test data is built inline with the existing factories + direct `.objects.create`
calls (there's no readiness/fatigue factory yet).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from gymapp.apps.metrics.models import FatigueAdjustment, ReadinessSnapshot
from gymapp.apps.routines.models import (
    Routine,
    RoutineDay,
    RoutineExercise,
    WeeklySplit,
)
from gymapp.apps.workouts.models import ExerciseLog, SetLog, WorkoutSession, WorkoutStatus
from gymapp.services.fatigue import (
    HEAVY_THRESHOLD,
    MODERATE_THRESHOLD,
    compute_muscle_fatigue,
    current_readiness,
    daily_advice,
)
from tests.factories import EquipmentFactory, ExerciseFactory, MuscleGroupFactory, UserFactory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finished_session(user, started_at=None) -> WorkoutSession:
    started_at = started_at or timezone.now()
    return WorkoutSession.objects.create(
        owner=user,
        started_at=started_at,
        finished_at=started_at,
        status=WorkoutStatus.FINISHED,
    )


def _make_set(
    session,
    exercise,
    *,
    completed_at,
    is_warmup: bool = False,
    weight_kg: Decimal = Decimal("60"),
    reps: int = 8,
) -> SetLog:
    log = ExerciseLog.objects.create(session=session, exercise=exercise, ordering=0)
    return SetLog.objects.create(
        exercise_log=log,
        ordering=0,
        weight_kg=weight_kg,
        reps=reps,
        is_warmup=is_warmup,
        completed_at=completed_at,
    )


@pytest.fixture
def alice(db):
    return UserFactory(email="alice@example.com")


@pytest.fixture
def bob(db):
    return UserFactory(email="bob@example.com")


@pytest.fixture
def biceps(db):
    return MuscleGroupFactory(slug="biceps", name="Biceps", region="arms")


@pytest.fixture
def chest(db):
    return MuscleGroupFactory(slug="chest", name="Chest", region="chest")


@pytest.fixture
def lumbar(db):
    return MuscleGroupFactory(slug="lumbar", name="Lumbar", region="back")


@pytest.fixture
def triceps(db):
    return MuscleGroupFactory(slug="triceps", name="Triceps", region="arms")


@pytest.fixture
def bench(db, chest):
    ex = ExerciseFactory(slug="flat-bench", equipment=EquipmentFactory(slug="barbell"))
    ex.primary_muscles.add(chest)
    return ex


@pytest.fixture
def curl(db, biceps):
    ex = ExerciseFactory(slug="db-curl", equipment=EquipmentFactory(slug="dumbbell"))
    ex.primary_muscles.add(biceps)
    return ex


@pytest.fixture
def deadlift(db, lumbar):
    ex = ExerciseFactory(slug="deadlift", equipment=EquipmentFactory(slug="barbell"))
    ex.primary_muscles.add(lumbar)
    return ex


# ---------------------------------------------------------------------------
# compute_muscle_fatigue — decay behavior
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_decay_halves_at_half_life(alice, deadlift):
    """A set N days old on lumbar (half-life=4) where N==half_life is worth
    exactly 0.5 of a set today. The service truncates `completed_at` to a
    date, so we need an integer day-offset that matches the half-life — lumbar
    is the only stock muscle whose half-life is a whole number of days."""
    today = timezone.localdate()

    session_today = _make_finished_session(alice, started_at=timezone.now())
    _make_set(session_today, deadlift, completed_at=timezone.now())

    older = timezone.now() - timedelta(days=4)
    session_old = _make_finished_session(alice, started_at=older)
    _make_set(session_old, deadlift, completed_at=older)

    # 4d old contributes 0.5; today contributes 1.0 -> total = 1.5
    result = compute_muscle_fatigue(alice, today=today)
    assert "lumbar" in result
    assert result["lumbar"].score == pytest.approx(1.5, abs=0.01)
    assert result["lumbar"].raw_sets == 2


@pytest.mark.django_db
def test_lumbar_decays_slower_than_biceps(alice, curl, deadlift):
    """Same age (3 days), but lumbar's half-life (4) > biceps's (1.5)."""
    today = timezone.localdate()
    three_days_ago = timezone.now() - timedelta(days=3)

    s_curl = _make_finished_session(alice, started_at=three_days_ago)
    _make_set(s_curl, curl, completed_at=three_days_ago)

    s_dl = _make_finished_session(alice, started_at=three_days_ago)
    _make_set(s_dl, deadlift, completed_at=three_days_ago)

    result = compute_muscle_fatigue(alice, today=today)
    assert result["lumbar"].score > result["biceps"].score


@pytest.mark.django_db
def test_window_days_cutoff_excludes_old_sets(alice, curl):
    """A set 30 days old is beyond WINDOW_DAYS (=14) and contributes nothing."""
    today = timezone.localdate()
    way_old = timezone.now() - timedelta(days=30)

    session = _make_finished_session(alice, started_at=way_old)
    _make_set(session, curl, completed_at=way_old)

    result = compute_muscle_fatigue(alice, today=today)
    assert "biceps" not in result


@pytest.mark.django_db
def test_warmup_sets_are_excluded(alice, curl):
    today = timezone.localdate()
    session = _make_finished_session(alice)
    _make_set(session, curl, completed_at=timezone.now(), is_warmup=True)

    result = compute_muscle_fatigue(alice, today=today)
    assert "biceps" not in result


@pytest.mark.django_db
def test_incomplete_sets_are_excluded(alice, curl):
    today = timezone.localdate()
    session = _make_finished_session(alice)
    _make_set(session, curl, completed_at=None)

    result = compute_muscle_fatigue(alice, today=today)
    assert "biceps" not in result


@pytest.mark.django_db
def test_non_finished_sessions_are_excluded(alice, curl):
    today = timezone.localdate()
    in_progress = WorkoutSession.objects.create(
        owner=alice,
        started_at=timezone.now(),
        status=WorkoutStatus.IN_PROGRESS,
    )
    _make_set(in_progress, curl, completed_at=timezone.now())

    result = compute_muscle_fatigue(alice, today=today)
    assert "biceps" not in result


@pytest.mark.django_db
def test_multi_primary_muscle_exercise_credits_both(alice, chest, triceps):
    """A set today on a chest+triceps exercise = 1.0 fatigue unit on each muscle."""
    ex = ExerciseFactory(slug="dip", equipment=EquipmentFactory(slug="bodyweight"))
    ex.primary_muscles.add(chest, triceps)

    today = timezone.localdate()
    session = _make_finished_session(alice)
    _make_set(session, ex, completed_at=timezone.now())

    result = compute_muscle_fatigue(alice, today=today)
    assert result["chest"].score == pytest.approx(1.0, abs=0.01)
    assert result["triceps"].score == pytest.approx(1.0, abs=0.01)


@pytest.mark.django_db
def test_fatigue_adjustment_stacks_positive(alice, bench):
    today = timezone.localdate()
    session = _make_finished_session(alice)
    _make_set(session, bench, completed_at=timezone.now())

    FatigueAdjustment.objects.create(owner=alice, date=today, muscle_slug="chest", delta=3.0)

    result = compute_muscle_fatigue(alice, today=today)
    # 1.0 from today's set + 3.0 manual = 4.0
    assert result["chest"].score == pytest.approx(4.0, abs=0.01)


@pytest.mark.django_db
def test_fatigue_adjustment_negative_clamped_at_zero(alice, bench):
    today = timezone.localdate()
    session = _make_finished_session(alice)
    _make_set(session, bench, completed_at=timezone.now())

    FatigueAdjustment.objects.create(owner=alice, date=today, muscle_slug="chest", delta=-5.0)

    result = compute_muscle_fatigue(alice, today=today)
    # 1.0 - 5.0 = -4.0 -> clamped to 0
    assert result["chest"].score == 0.0


@pytest.mark.django_db
def test_owner_scoping_isolates_users(alice, bob, curl):
    """Sets and adjustments from `bob` must not bleed into `alice`'s scores."""
    today = timezone.localdate()

    bob_session = _make_finished_session(bob)
    _make_set(bob_session, curl, completed_at=timezone.now())
    FatigueAdjustment.objects.create(owner=bob, date=today, muscle_slug="chest", delta=99.0)

    result = compute_muscle_fatigue(alice, today=today)
    assert result == {}


# ---------------------------------------------------------------------------
# current_readiness
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_current_readiness_formula_high(alice):
    today = timezone.localdate()
    ReadinessSnapshot.objects.create(
        owner=alice, date=today, sleep_quality=5, stress_level=1, soreness_overall=1
    )
    # (5 + (6-1) + (6-1)) / 3 = 15/3 = 5.0
    assert current_readiness(alice, today=today) == pytest.approx(5.0, abs=0.01)


@pytest.mark.django_db
def test_current_readiness_formula_low(alice):
    today = timezone.localdate()
    ReadinessSnapshot.objects.create(
        owner=alice, date=today, sleep_quality=1, stress_level=5, soreness_overall=5
    )
    # (1 + 1 + 1) / 3 = 1.0
    assert current_readiness(alice, today=today) == pytest.approx(1.0, abs=0.01)


@pytest.mark.django_db
def test_current_readiness_none_when_no_snapshot(alice):
    assert current_readiness(alice, today=timezone.localdate()) is None


# ---------------------------------------------------------------------------
# daily_advice
# ---------------------------------------------------------------------------


# A fixed Monday. Today the user's WeeklySplit row for weekday=0 will be used.
FIXED_TODAY = date(2026, 5, 25)  # Monday (Python weekday=0)


def _attach_split(user, exercises, weekday: int = 0, archived: bool = False) -> WeeklySplit:
    routine = Routine.objects.create(owner=user, name=f"R-{user.email}", is_archived=archived)
    rday = RoutineDay.objects.create(routine=routine, label="Day", ordering=0)
    for i, ex in enumerate(exercises):
        RoutineExercise.objects.create(
            routine_day=rday,
            exercise=ex,
            ordering=i,
            target_sets=3,
            target_reps_low=8,
            target_reps_high=12,
        )
    return WeeklySplit.objects.create(owner=user, weekday=weekday, routine_day=rday)


@pytest.mark.django_db
def test_daily_advice_rest_when_no_split_for_today(alice):
    advice = daily_advice(alice, today=FIXED_TODAY)
    assert advice.level == "rest"
    assert advice.color == "slate"
    assert advice.target_muscles == []


@pytest.mark.django_db
def test_daily_advice_rest_when_routine_is_archived(alice, bench):
    _attach_split(alice, [bench], weekday=FIXED_TODAY.weekday(), archived=True)
    advice = daily_advice(alice, today=FIXED_TODAY)
    assert advice.level == "rest"


@pytest.mark.django_db
def test_daily_advice_rest_when_split_points_at_other_owner_routine(alice, bob, bench):
    """Defensive: a WeeklySplit owned by `alice` whose RoutineDay belongs to
    `bob` (legacy/leaky data) must NOT leak into Alice's advice."""
    bob_routine = Routine.objects.create(owner=bob, name="Bob's")
    bob_day = RoutineDay.objects.create(routine=bob_routine, label="Bob Day", ordering=0)
    RoutineExercise.objects.create(
        routine_day=bob_day,
        exercise=bench,
        ordering=0,
        target_sets=3,
        target_reps_low=8,
        target_reps_high=12,
    )
    WeeklySplit.objects.create(
        owner=alice, weekday=FIXED_TODAY.weekday(), routine_day=bob_day
    )

    advice = daily_advice(alice, today=FIXED_TODAY)
    assert advice.level == "rest"


@pytest.mark.django_db
def test_daily_advice_heavy_when_fresh(alice, bench, chest):
    """No recent sets + no readiness snapshot -> heavy/emerald."""
    _attach_split(alice, [bench], weekday=FIXED_TODAY.weekday())
    advice = daily_advice(alice, today=FIXED_TODAY)
    assert advice.level == "heavy"
    assert advice.color == "emerald"
    assert advice.target_muscles == ["chest"]
    assert advice.avg_fatigue == pytest.approx(0.0, abs=0.01)


@pytest.mark.django_db
def test_daily_advice_light_when_heavy_fatigue_exceeded(alice, bench):
    """Stack enough recent completed sets on chest so its decayed score
    exceeds HEAVY_THRESHOLD (12.0)."""
    _attach_split(alice, [bench], weekday=FIXED_TODAY.weekday())

    # 15 sets done today: each contributes 1.0 -> total 15 > HEAVY_THRESHOLD.
    today_dt = datetime.combine(FIXED_TODAY, datetime.min.time())
    today_aware = timezone.make_aware(today_dt) if timezone.is_naive(today_dt) else today_dt
    session = _make_finished_session(alice, started_at=today_aware)
    for _ in range(15):
        _make_set(session, bench, completed_at=today_aware)

    advice = daily_advice(alice, today=FIXED_TODAY)
    assert advice.avg_fatigue >= HEAVY_THRESHOLD
    assert advice.level == "light"
    assert advice.color == "rose"


@pytest.mark.django_db
def test_daily_advice_moderate_when_between_thresholds(alice, bench):
    """Score for chest between MODERATE (6) and HEAVY (12) -> moderate/amber."""
    _attach_split(alice, [bench], weekday=FIXED_TODAY.weekday())

    today_dt = datetime.combine(FIXED_TODAY, datetime.min.time())
    today_aware = timezone.make_aware(today_dt) if timezone.is_naive(today_dt) else today_dt
    session = _make_finished_session(alice, started_at=today_aware)
    for _ in range(8):  # 8 sets today -> score = 8.0
        _make_set(session, bench, completed_at=today_aware)

    advice = daily_advice(alice, today=FIXED_TODAY)
    assert MODERATE_THRESHOLD <= advice.avg_fatigue < HEAVY_THRESHOLD
    assert advice.level == "moderate"
    assert advice.color == "amber"


@pytest.mark.django_db
def test_daily_advice_low_readiness_overrides_fresh_to_light(alice, bench):
    """Even with zero fatigue, readiness ≤ 2 forces a light day."""
    _attach_split(alice, [bench], weekday=FIXED_TODAY.weekday())
    # readiness = (1 + (6-5) + (6-5))/3 = 1.0  ≤ 2
    ReadinessSnapshot.objects.create(
        owner=alice, date=FIXED_TODAY, sleep_quality=1, stress_level=5, soreness_overall=5
    )

    advice = daily_advice(alice, today=FIXED_TODAY)
    assert advice.readiness == pytest.approx(1.0, abs=0.01)
    assert advice.level == "light"
    assert advice.color == "rose"
