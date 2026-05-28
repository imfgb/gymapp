"""Tests for the analytics service (weekly volume + sets per muscle)."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from gymapp.apps.workouts.models import ExerciseLog, SetLog, WorkoutSession, WorkoutStatus
from gymapp.services.analytics import (
    body_comp_series,
    deload_recommendation,
    sets_by_muscle,
    weekly_volume,
)
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


# ---------------------------------------------------------------------------
# deload_recommendation
# ---------------------------------------------------------------------------


def _hard_week(alice, bench, weeks_ago, today, *, sets=5):
    """One session in the completed week `weeks_ago` weeks before today."""
    day = today - timedelta(days=7 * weeks_ago)
    _session(alice, day, [(bench, Decimal("100"), 5, False, True) for _ in range(sets)])


@pytest.mark.django_db
def test_deload_not_recommended_without_training(alice):
    advice = deload_recommendation(alice, today=timezone.localdate())
    assert advice.recommended is False
    assert advice.reason == "no_recent_training"


@pytest.mark.django_db
def test_deload_recommended_after_threshold_hard_weeks(alice, bench):
    today = timezone.localdate()
    for w in range(1, 6):  # 5 completed hard weeks (1..5 weeks ago)
        _hard_week(alice, bench, w, today)
    advice = deload_recommendation(alice, today=today, threshold=5)
    assert advice.recommended is True
    assert advice.weeks_accumulated == 5
    assert advice.reason == "accumulated_fatigue"


@pytest.mark.django_db
def test_deload_not_recommended_below_threshold(alice, bench):
    today = timezone.localdate()
    for w in range(1, 4):  # only 3 hard weeks
        _hard_week(alice, bench, w, today)
    advice = deload_recommendation(alice, today=today, threshold=5)
    assert advice.recommended is False
    assert advice.weeks_accumulated == 3
    assert advice.reason == "accumulating"


@pytest.mark.django_db
def test_recent_light_week_resets_accumulation(alice, bench):
    today = timezone.localdate()
    for w in range(2, 7):  # hard weeks 2..6 ago
        _hard_week(alice, bench, w, today)
    _hard_week(alice, bench, 1, today, sets=1)  # last completed week is light
    advice = deload_recommendation(alice, today=today, threshold=5)
    assert advice.recommended is False
    assert advice.weeks_accumulated == 0


@pytest.mark.django_db
def test_deload_ignores_current_partial_week(alice, bench):
    today = timezone.localdate()
    # 5 hard completed weeks → recommend; a session this week shouldn't change it
    for w in range(1, 6):
        _hard_week(alice, bench, w, today)
    _session(alice, today, [(bench, Decimal("100"), 5, False, True)])
    advice = deload_recommendation(alice, today=today, threshold=5)
    assert advice.recommended is True
    assert advice.weeks_accumulated == 5


# ---------------- body_comp_series ----------------


@pytest.mark.django_db
def test_body_comp_series_empty_when_no_snapshots(alice):
    assert body_comp_series(alice) == []


@pytest.mark.django_db
def test_body_comp_series_chronological_and_computes_bmi(alice):
    from gymapp.apps.metrics.models import UserMetricSnapshot

    alice.profile.height_cm = 180
    alice.profile.save()
    today = timezone.localdate()
    UserMetricSnapshot.objects.create(
        owner=alice, weight_kg=Decimal("82"),
        measured_at=_aware(today - timedelta(days=30)),
    )
    UserMetricSnapshot.objects.create(
        owner=alice, weight_kg=Decimal("80"), body_fat_pct=Decimal("15"),
        muscle_pct=Decimal("42"), measured_at=_aware(today),
    )
    series = body_comp_series(alice, days=180)
    assert [p.weight_kg for p in series] == [82.0, 80.0]  # oldest -> newest
    # 80 / 1.80^2 ≈ 24.7
    assert series[-1].bmi == 24.7
    assert series[-1].body_fat_pct == 15.0
    assert series[-1].muscle_pct == 42.0
    assert series[0].body_fat_pct is None  # older snapshot didn't have it


@pytest.mark.django_db
def test_body_comp_series_dates_use_local_timezone(alice):
    """A snapshot logged in the evening (local) is the next day in UTC. The
    chart x-axis must use the local date, not the raw UTC `.date()`."""
    from datetime import datetime

    from gymapp.apps.metrics.models import UserMetricSnapshot

    local_day = timezone.localdate()
    evening_local = timezone.make_aware(
        datetime(local_day.year, local_day.month, local_day.day, 22, 0)
    )
    UserMetricSnapshot.objects.create(
        owner=alice, weight_kg=Decimal("80"), measured_at=evening_local
    )
    series = body_comp_series(alice, days=180)
    assert len(series) == 1
    assert series[0].date == local_day


@pytest.mark.django_db
def test_body_comp_series_respects_days_window(alice):
    from gymapp.apps.metrics.models import UserMetricSnapshot

    today = timezone.localdate()
    UserMetricSnapshot.objects.create(
        owner=alice, weight_kg=Decimal("80"),
        measured_at=_aware(today - timedelta(days=400)),  # outside 180d window
    )
    UserMetricSnapshot.objects.create(
        owner=alice, weight_kg=Decimal("82"),
        measured_at=_aware(today - timedelta(days=10)),
    )
    series = body_comp_series(alice, days=180)
    assert len(series) == 1
    assert series[0].weight_kg == 82.0


@pytest.mark.django_db
def test_body_comp_series_bmi_none_without_height(alice):
    from gymapp.apps.metrics.models import UserMetricSnapshot

    alice.profile.height_cm = None
    alice.profile.save()
    UserMetricSnapshot.objects.create(
        owner=alice, weight_kg=Decimal("80"), measured_at=_aware(timezone.localdate()),
    )
    series = body_comp_series(alice)
    assert series[0].bmi is None


@pytest.mark.django_db
def test_body_comp_series_owner_scoped(alice):
    from gymapp.apps.metrics.models import UserMetricSnapshot

    bob = UserFactory(email="bob.body@example.com")
    UserMetricSnapshot.objects.create(
        owner=bob, weight_kg=Decimal("80"), measured_at=_aware(timezone.localdate()),
    )
    assert body_comp_series(alice) == []
