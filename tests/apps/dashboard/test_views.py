"""Dashboard view smoke tests — confirms the page renders for the empty,
in-progress, and rest-day states without crashing."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from gymapp.apps.dashboard.views import build_week_view
from gymapp.apps.metrics.models import MonthlyGoal, UserMetricSnapshot
from gymapp.apps.routines.models import Routine, RoutineDay, SkippedDay, WeeklySplit
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


def test_build_week_view_slides_workouts_past_skipped_day():
    """Skipping a planned day pushes its workout to the next open day; the rest
    of the week's sequence slides forward and nothing is lost."""
    week = [date(2026, 5, 18) + timedelta(days=i) for i in range(7)]  # Mon..Sun
    base = ["Push", "Pull", "Legs", None, None, None, None]
    skipped = {week[0]}  # skip Monday

    view = build_week_view(base, week, skipped, today=week[0])

    assert view[0]["is_skipped"] is True
    assert [d["routine_day"] for d in view] == [None, "Push", "Pull", "Legs", None, None, None]


def test_build_week_view_unchanged_without_skips():
    week = [date(2026, 5, 18) + timedelta(days=i) for i in range(7)]
    base = ["Push", "Pull", "Legs", None, None, None, None]

    view = build_week_view(base, week, skipped_dates=set(), today=week[2])

    assert [d["routine_day"] for d in view] == base
    assert view[2]["is_today"] is True


@pytest.mark.django_db
def test_skip_today_toggle_creates_and_removes(alice, client):
    client.force_login(alice)
    today = timezone.localdate()

    resp = client.post(reverse("routines:skip_today"))
    assert resp.status_code == 302
    assert resp.url == reverse("dashboard:home")
    assert SkippedDay.objects.filter(owner=alice, date=today).exists()

    # Toggling again removes it.
    client.post(reverse("routines:skip_today"))
    assert not SkippedDay.objects.filter(owner=alice, date=today).exists()


@pytest.mark.django_db
def test_dashboard_today_skipped_shows_message_and_shifts_week(alice, client):
    routine = Routine.objects.create(owner=alice, name="PPL")
    today_day = RoutineDay.objects.create(routine=routine, label="Push A")
    today_weekday = timezone.localtime().weekday()
    WeeklySplit.objects.create(owner=alice, weekday=today_weekday, routine_day=today_day)
    SkippedDay.objects.create(owner=alice, date=timezone.localdate())

    client.force_login(alice)
    resp = client.get(reverse("dashboard:home"))

    assert resp.status_code == 200
    assert "no irás al gym".encode() in resp.content


@pytest.mark.django_db
def test_dashboard_offers_skip_button_when_workout_today(alice, client):
    routine = Routine.objects.create(owner=alice, name="PPL")
    day = RoutineDay.objects.create(routine=routine, label="Push A")
    WeeklySplit.objects.create(
        owner=alice, weekday=timezone.localtime().weekday(), routine_day=day
    )

    client.force_login(alice)
    resp = client.get(reverse("dashboard:home"))

    assert resp.status_code == 200
    assert "Hoy no iré al gym".encode() in resp.content


@pytest.mark.django_db
def test_dashboard_ignores_archived_routine_and_offers_active_ones(alice, client):
    """An archived routine scheduled today must not drive the card; active
    routines must be offered in the start picker."""
    archived = Routine.objects.create(owner=alice, name="Old PPL", is_archived=True)
    archived_day = RoutineDay.objects.create(routine=archived, label="Legs A")
    WeeklySplit.objects.create(
        owner=alice, weekday=timezone.localtime().weekday(), routine_day=archived_day
    )
    active = Routine.objects.create(owner=alice, name="Anatoly")
    active_day = RoutineDay.objects.create(routine=active, label="Full Body")

    client.force_login(alice)
    resp = client.get(reverse("dashboard:home"))
    content = resp.content.decode()

    assert resp.status_code == 200
    assert "Legs A" not in content  # archived day not surfaced anywhere
    assert "Anatoly" in content  # active routine offered
    assert f'value="{active_day.id}"' in content


@pytest.mark.django_db
def test_dashboard_has_no_leaked_template_comments(alice, client):
    """Multi-line {# #} comments render as literal text; guard the home page."""
    client.force_login(alice)
    resp = client.get(reverse("dashboard:home"))
    assert resp.status_code == 200
    assert b"{#" not in resp.content


@pytest.mark.django_db
def test_dashboard_redirects_anon_to_login(client):
    resp = client.get(reverse("dashboard:home"))
    assert resp.status_code == 302
    assert "/auth/login/" in resp.url


@pytest.mark.django_db
def test_dashboard_shows_monthly_goal_progress(alice, client):
    today = timezone.localdate()
    MonthlyGoal.objects.create(
        owner=alice, year=today.year, month=today.month, target_sessions=12
    )
    client.force_login(alice)
    resp = client.get(reverse("dashboard:home"))
    assert resp.status_code == 200
    assert b"Metas del mes" in resp.content
    assert b"Entrenamientos" in resp.content


@pytest.mark.django_db
def test_dashboard_goal_card_prompts_when_unset(alice, client):
    client.force_login(alice)
    resp = client.get(reverse("dashboard:home"))
    assert resp.status_code == 200
    assert b"Fija tus metas de este mes" in resp.content


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
