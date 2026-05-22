"""View-level tests for the workouts app."""

from __future__ import annotations

import pytest
from django.urls import reverse

from gymapp.apps.workouts.models import WorkoutSession, WorkoutStatus
from gymapp.services import workouts as workouts_service
from tests.factories import EquipmentFactory, ExerciseFactory, MuscleGroupFactory, UserFactory


@pytest.fixture
def client_alice(client, db):
    alice = UserFactory(email="alice@example.com")
    client.force_login(alice)
    return client, alice


@pytest.mark.django_db
def test_start_redirects_to_existing_active_session(client_alice):
    """POSTing to /workouts/start/ when an in-progress session already exists
    must redirect to that session, not create a new one."""
    client, alice = client_alice
    existing = workouts_service.start_session(alice)

    response = client.post(reverse("workouts:start"))

    assert response.status_code == 302
    assert response["Location"] == reverse("workouts:session", args=[existing.pk])
    # No new session was created
    assert WorkoutSession.objects.for_user(alice).count() == 1


@pytest.mark.django_db
def test_start_creates_new_session_when_none_active(client_alice):
    """POSTing to /workouts/start/ with no in-progress session creates one and
    redirects to it."""
    client, alice = client_alice

    response = client.post(reverse("workouts:start"))

    assert response.status_code == 302
    sessions = WorkoutSession.objects.for_user(alice)
    assert sessions.count() == 1
    assert sessions.first().status == WorkoutStatus.IN_PROGRESS
    assert response["Location"] == reverse("workouts:session", args=[sessions.first().pk])


@pytest.mark.django_db
def test_start_creates_new_session_after_previous_finished(client_alice):
    """A finished session should not block starting a new one."""
    client, alice = client_alice
    old = workouts_service.start_session(alice)
    workouts_service.finish_session(old)

    response = client.post(reverse("workouts:start"))

    assert response.status_code == 302
    assert WorkoutSession.objects.for_user(alice).count() == 2
    new_session = (
        WorkoutSession.objects.for_user(alice).filter(status=WorkoutStatus.IN_PROGRESS).first()
    )
    assert new_session is not None
    assert new_session.pk != old.pk


@pytest.mark.django_db
def test_session_page_has_no_leaked_template_comments(client_alice):
    """Multi-line {# #} comments render as literal text in Django (they only
    work on a single line). Guard against them leaking onto the session page."""
    client, alice = client_alice
    sess = workouts_service.start_session(alice)
    workouts_service.add_exercise_to_session(sess, exercise=ExerciseFactory(), sets_count=1)

    response = client.get(reverse("workouts:session", args=[sess.pk]))

    assert response.status_code == 200
    assert b"{#" not in response.content


@pytest.mark.django_db
def test_complete_set_coerces_decimal_reps_to_int(client_alice):
    """Reps are whole numbers. A decimal value submitted for reps (e.g. a
    pasted '2.5') must be stored as an int, never as a fraction."""
    client, alice = client_alice
    sess = workouts_service.start_session(alice)
    elog = workouts_service.add_exercise_to_session(
        sess, exercise=ExerciseFactory(), sets_count=1
    )
    set_log = elog.set_logs.first()

    response = client.post(
        reverse("workouts:complete_set", args=[sess.pk, set_log.pk]),
        {"weight_kg": "60", "reps": "2.5"},
    )

    assert response.status_code == 200
    set_log.refresh_from_db()
    assert set_log.reps == 2


@pytest.mark.django_db
def test_session_rows_expose_progress_data_attrs(client_alice):
    """The session page must tag working sets so the live progress counter can
    count them from the DOM without a reload."""
    client, alice = client_alice
    sess = workouts_service.start_session(alice)
    workouts_service.add_exercise_to_session(sess, exercise=ExerciseFactory(), sets_count=1)

    resp = client.get(reverse("workouts:session", args=[sess.pk]))

    assert resp.status_code == 200
    assert b'data-working="1"' in resp.content
    assert b'data-complete="0"' in resp.content


@pytest.mark.django_db
def test_finish_redirects_to_dashboard(client_alice):
    client, alice = client_alice
    sess = workouts_service.start_session(alice)

    resp = client.post(reverse("workouts:finish", args=[sess.pk]))

    assert resp.status_code == 302
    assert resp.url == reverse("dashboard:home")
    sess.refresh_from_db()
    assert sess.status == WorkoutStatus.FINISHED


@pytest.mark.django_db
def test_start_with_set_today_split_updates_weekly_split(client_alice):
    """Starting from the dashboard picker (set_today_split) reschedules today."""
    from django.utils import timezone

    from gymapp.apps.routines.models import Routine, RoutineDay, WeeklySplit

    client, alice = client_alice
    routine = Routine.objects.create(owner=alice, name="R")
    day = RoutineDay.objects.create(routine=routine, label="Push A")

    resp = client.post(
        reverse("workouts:start"),
        data={"routine_day": day.id, "set_today_split": "1"},
    )

    assert resp.status_code == 302
    split = WeeklySplit.objects.get(owner=alice, weekday=timezone.localtime().weekday())
    assert split.routine_day_id == day.id


@pytest.mark.django_db
def test_swap_options_lists_ranked_alternatives(client_alice, clean_catalog):
    client, alice = client_alice
    chest = MuscleGroupFactory(slug="chest")
    bar = EquipmentFactory(slug="barbell")
    bench = ExerciseFactory(slug="bench", name="Bench Press", equipment=bar)
    bench.primary_muscles.set([chest])
    alt = ExerciseFactory(slug="db-bench", name="Dumbbell Bench", equipment=bar)
    alt.primary_muscles.set([chest])
    sess = workouts_service.start_session(alice)
    elog = workouts_service.add_exercise_to_session(sess, exercise=bench, sets_count=1)

    resp = client.get(reverse("workouts:swap_options", args=[sess.pk, elog.pk]))

    assert resp.status_code == 200
    assert b"Dumbbell Bench" in resp.content


@pytest.mark.django_db
def test_swap_options_blocked_after_completed_set(client_alice, clean_catalog):
    client, alice = client_alice
    chest = MuscleGroupFactory(slug="chest")
    bench = ExerciseFactory(slug="bench", name="Bench", equipment=EquipmentFactory(slug="barbell"))
    bench.primary_muscles.set([chest])
    sess = workouts_service.start_session(alice)
    elog = workouts_service.add_exercise_to_session(sess, exercise=bench, sets_count=1)
    workouts_service.complete_set(elog.set_logs.first(), weight_kg=50, reps=8)

    resp = client.get(reverse("workouts:swap_options", args=[sess.pk, elog.pk]))

    assert resp.status_code == 200
    assert b"ya tiene series completadas" in resp.content


@pytest.mark.django_db
def test_delete_set_removes_row_and_renumbers(client_alice):
    """Deleting a middle set removes it and keeps sibling ordering contiguous."""
    client, alice = client_alice
    sess = workouts_service.start_session(alice)
    elog = workouts_service.add_exercise_to_session(
        sess, exercise=ExerciseFactory(), sets_count=3
    )
    middle = elog.set_logs.order_by("ordering")[1]

    response = client.post(reverse("workouts:delete_set", args=[sess.pk, middle.pk]))

    assert response.status_code == 200
    remaining = list(elog.set_logs.order_by("ordering"))
    assert len(remaining) == 2
    assert [s.ordering for s in remaining] == [0, 1]
