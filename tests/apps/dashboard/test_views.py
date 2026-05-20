"""Dashboard view smoke tests — confirms the page renders for the empty,
in-progress, and rest-day states without crashing."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from gymapp.apps.metrics.models import UserMetricSnapshot
from gymapp.apps.routines.models import Routine, RoutineDay, WeeklySplit
from gymapp.services import workouts as workouts_service

from tests.factories import EquipmentFactory, ExerciseFactory, UserFactory


@pytest.fixture
def alice(db):
    return UserFactory(email="alice@example.com")


@pytest.mark.django_db
def test_dashboard_renders_for_empty_user(alice, client):
    client.force_login(alice)
    resp = client.get(reverse("dashboard:home"))
    assert resp.status_code == 200
    assert b"Hola" in resp.content


@pytest.mark.django_db
def test_dashboard_shows_in_progress_session(alice, client):
    session = workouts_service.start_session(alice)
    client.force_login(alice)
    resp = client.get(reverse("dashboard:home"))
    assert resp.status_code == 200
    assert b"Continuar entrenamiento" in resp.content
    assert str(session.id).encode() in resp.content


@pytest.mark.django_db
def test_dashboard_shows_todays_routine_day(alice, client):
    routine = Routine.objects.create(owner=alice, name="PPL")
    day = RoutineDay.objects.create(routine=routine, label="Push A")
    today_weekday = timezone.localtime().weekday()
    WeeklySplit.objects.create(owner=alice, weekday=today_weekday, routine_day=day)

    client.force_login(alice)
    resp = client.get(reverse("dashboard:home"))
    assert resp.status_code == 200
    assert b"Push A" in resp.content
    assert b"Iniciar entrenamiento" in resp.content


@pytest.mark.django_db
def test_dashboard_shows_latest_metric(alice, client):
    UserMetricSnapshot.objects.create(
        owner=alice,
        measured_at=timezone.now() - timedelta(days=1),
        weight_kg=Decimal("78.5"),
        body_fat_pct=Decimal("15.0"),
    )
    client.force_login(alice)
    resp = client.get(reverse("dashboard:home"))
    assert resp.status_code == 200
    assert b"78.5" in resp.content


@pytest.mark.django_db
def test_dashboard_redirects_anon_to_login(client):
    resp = client.get(reverse("dashboard:home"))
    assert resp.status_code == 302
    assert "/auth/login/" in resp.url


@pytest.mark.django_db
def test_dashboard_isolated_per_user(alice, client):
    # Alice gets her own data; bob's PR doesn't leak.
    bob = UserFactory(email="bob@example.com")
    bench = ExerciseFactory(slug="bench-press", equipment=EquipmentFactory(slug="barbell"))

    # bob's session + PR
    bob_session = workouts_service.start_session(bob)
    elog = bob_session.exercise_logs.create(exercise=bench, ordering=0)
    s = elog.set_logs.create(ordering=0)
    workouts_service.complete_set(s, weight_kg=Decimal("100"), reps=5)
    workouts_service.finish_session(bob_session)

    client.force_login(alice)
    resp = client.get(reverse("dashboard:home"))
    assert resp.status_code == 200
    assert b"Bench Press" not in resp.content
    assert b"Sin PRs" in resp.content
