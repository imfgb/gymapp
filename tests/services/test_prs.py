"""Tests for PR auto-detection."""
from __future__ import annotations

from decimal import Decimal

import pytest

from gymapp.apps.prs.models import PersonalRecord, PRSource
from gymapp.apps.workouts.models import WorkoutStatus
from gymapp.services import workouts as workouts_service
from gymapp.services.prs import update_prs_from_session

from tests.factories import EquipmentFactory, ExerciseFactory, UserFactory


@pytest.fixture
def alice(db):
    return UserFactory(email="alice@example.com")


@pytest.fixture
def bench(db):
    return ExerciseFactory(slug="bench-press", equipment=EquipmentFactory(slug="barbell"))


def _complete_set(session, exercise, weight, reps, is_warmup=False):
    elog = session.exercise_logs.create(exercise=exercise, ordering=0)
    s = elog.set_logs.create(ordering=0, is_warmup=is_warmup)
    workouts_service.complete_set(s, weight_kg=Decimal(weight), reps=reps)
    return s


@pytest.mark.django_db
def test_finish_session_creates_pr_for_each_completed_rep_count(alice, bench):
    session = workouts_service.start_session(alice)
    _complete_set(session, bench, "100", 5)
    workouts_service.finish_session(session)

    prs = PersonalRecord.objects.for_user(alice)
    assert prs.count() == 1
    pr = prs.first()
    assert pr.weight_kg == Decimal("100")
    assert pr.reps == 5
    assert pr.source == PRSource.AUTO
    assert pr.source_set is not None


@pytest.mark.django_db
def test_pr_improves_when_session_beats_existing(alice, bench):
    # First session: 100 × 5
    s1 = workouts_service.start_session(alice)
    _complete_set(s1, bench, "100", 5)
    workouts_service.finish_session(s1)

    # Second session: 105 × 5 — should overwrite the PR
    s2 = workouts_service.start_session(alice)
    _complete_set(s2, bench, "105", 5)
    workouts_service.finish_session(s2)

    pr = PersonalRecord.objects.for_user(alice).get(exercise=bench, reps=5)
    assert pr.weight_kg == Decimal("105")


@pytest.mark.django_db
def test_pr_unchanged_when_session_is_lighter(alice, bench):
    s1 = workouts_service.start_session(alice)
    _complete_set(s1, bench, "100", 5)
    workouts_service.finish_session(s1)

    s2 = workouts_service.start_session(alice)
    _complete_set(s2, bench, "95", 5)
    workouts_service.finish_session(s2)

    pr = PersonalRecord.objects.for_user(alice).get(exercise=bench, reps=5)
    assert pr.weight_kg == Decimal("100")


@pytest.mark.django_db
def test_warmup_sets_dont_count(alice, bench):
    session = workouts_service.start_session(alice)
    _complete_set(session, bench, "200", 5, is_warmup=True)
    workouts_service.finish_session(session)

    assert PersonalRecord.objects.for_user(alice).count() == 0


@pytest.mark.django_db
def test_incomplete_sets_dont_count(alice, bench):
    session = workouts_service.start_session(alice)
    elog = session.exercise_logs.create(exercise=bench, ordering=0)
    elog.set_logs.create(ordering=0, weight_kg=Decimal("100"), reps=5)  # no completed_at
    workouts_service.finish_session(session)

    assert PersonalRecord.objects.for_user(alice).count() == 0


@pytest.mark.django_db
def test_different_rep_counts_yield_separate_prs(alice, bench):
    session = workouts_service.start_session(alice)
    elog = session.exercise_logs.create(exercise=bench, ordering=0)

    for idx, (w, r) in enumerate([("80", 12), ("100", 5), ("120", 1)]):
        s = elog.set_logs.create(ordering=idx)
        workouts_service.complete_set(s, weight_kg=Decimal(w), reps=r)

    workouts_service.finish_session(session)
    rows = sorted(
        PersonalRecord.objects.for_user(alice).values_list("reps", "weight_kg")
    )
    assert rows == [(1, Decimal("120")), (5, Decimal("100")), (12, Decimal("80"))]


@pytest.mark.django_db
def test_update_prs_is_idempotent(alice, bench):
    session = workouts_service.start_session(alice)
    _complete_set(session, bench, "100", 5)
    session.status = WorkoutStatus.FINISHED
    session.save()

    update_prs_from_session(session)
    update_prs_from_session(session)

    assert PersonalRecord.objects.for_user(alice).count() == 1
