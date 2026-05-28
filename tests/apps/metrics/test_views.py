"""Tests for the metrics goal editor view."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from gymapp.apps.metrics.models import MonthlyGoal
from tests.factories import UserFactory


@pytest.fixture
def alice(db):
    return UserFactory(email="goalview@example.com")


@pytest.mark.django_db
def test_goals_page_renders(alice, client):
    client.force_login(alice)
    resp = client.get(reverse("metrics:goals"))
    assert resp.status_code == 200
    assert b"Metas del mes" in resp.content


@pytest.mark.django_db
def test_post_upserts_current_month_goal(alice, client):
    client.force_login(alice)
    resp = client.post(
        reverse("metrics:goals"),
        {"target_sessions": "16", "target_bodyweight_kg": "78.5"},
    )
    assert resp.status_code == 302
    today = timezone.localdate()
    goal = MonthlyGoal.objects.get(owner=alice, year=today.year, month=today.month)
    assert goal.target_sessions == 16
    assert goal.target_bodyweight_kg == Decimal("78.5")


@pytest.mark.django_db
def test_post_twice_updates_same_row(alice, client):
    client.force_login(alice)
    url = reverse("metrics:goals")
    client.post(url, {"target_sessions": "10"})
    client.post(url, {"target_sessions": "20"})
    assert MonthlyGoal.objects.filter(owner=alice).count() == 1


# ---------- New body-comp + recovery views ----------


@pytest.mark.django_db
def test_snapshot_create_persists_new_body_comp_fields(alice, client):
    from gymapp.apps.metrics.models import UserMetricSnapshot

    client.force_login(alice)
    resp = client.post(
        reverse("metrics:create"),
        {
            "weight_kg": "80.0",
            "body_fat_pct": "15.5",
            "muscle_pct": "42.1",
            "visceral_fat": "7.5",
            "notes": "después de gym",
        },
    )
    assert resp.status_code == 302
    snap = UserMetricSnapshot.objects.get(owner=alice)
    assert snap.muscle_pct == Decimal("42.1")
    assert snap.visceral_fat == Decimal("7.5")


@pytest.mark.django_db
def test_snapshot_create_rejects_negative_weight(alice, client):
    """A negative bodyweight would corrupt BMI and the nutrition BMR/macro math.
    It's dropped to None → the view's required-weight guard returns 400."""
    from gymapp.apps.metrics.models import UserMetricSnapshot

    client.force_login(alice)
    resp = client.post(reverse("metrics:create"), {"weight_kg": "-80"})
    assert resp.status_code == 400
    assert not UserMetricSnapshot.objects.filter(owner=alice).exists()


@pytest.mark.django_db
def test_snapshot_create_drops_negative_body_comp(alice, client):
    """Negative body-fat / muscle % are invalid; stored as None, not negative."""
    from gymapp.apps.metrics.models import UserMetricSnapshot

    client.force_login(alice)
    resp = client.post(
        reverse("metrics:create"),
        {"weight_kg": "80", "body_fat_pct": "-15", "muscle_pct": "-42"},
    )
    assert resp.status_code == 302
    snap = UserMetricSnapshot.objects.get(owner=alice)
    assert snap.body_fat_pct is None
    assert snap.muscle_pct is None


@pytest.mark.django_db
def test_metrics_list_renders_bmi_when_height_set(alice, client):
    from gymapp.apps.metrics.models import UserMetricSnapshot

    alice.profile.height_cm = 178
    alice.profile.save()
    UserMetricSnapshot.objects.create(owner=alice, weight_kg="80.0", measured_at=timezone.now())
    client.force_login(alice)
    resp = client.get(reverse("metrics:list"))
    # 80 / 1.78^2 ≈ 25.2
    assert b"25.2" in resp.content
    assert b"BMI" in resp.content


@pytest.mark.django_db
def test_snapshot_edit_updates(alice, client):
    from gymapp.apps.metrics.models import UserMetricSnapshot

    snap = UserMetricSnapshot.objects.create(
        owner=alice, weight_kg="80.0", body_fat_pct="15", measured_at=timezone.now(),
    )
    client.force_login(alice)
    resp = client.post(
        reverse("metrics:edit", args=[snap.id]),
        {"weight_kg": "81.5", "body_fat_pct": "14.2", "muscle_pct": "43"},
    )
    assert resp.status_code == 302
    snap.refresh_from_db()
    assert snap.weight_kg == Decimal("81.5")
    assert snap.body_fat_pct == Decimal("14.2")
    assert snap.muscle_pct == Decimal("43")


@pytest.mark.django_db
def test_snapshot_edit_cross_user_404(alice, client):
    from gymapp.apps.metrics.models import UserMetricSnapshot

    bob = UserFactory(email="bob.snap@example.com")
    snap = UserMetricSnapshot.objects.create(
        owner=bob, weight_kg="80.0", measured_at=timezone.now(),
    )
    client.force_login(alice)
    resp = client.get(reverse("metrics:edit", args=[snap.id]))
    assert resp.status_code == 404


@pytest.mark.django_db
def test_progress_page_renders_body_charts_when_data_present(alice, client):
    from gymapp.apps.metrics.models import UserMetricSnapshot

    alice.profile.height_cm = 178
    alice.profile.save()
    UserMetricSnapshot.objects.create(owner=alice, weight_kg="80", measured_at=timezone.now())
    client.force_login(alice)
    resp = client.get(reverse("dashboard:progress"))
    assert resp.status_code == 200
    assert "Composición corporal".encode() in resp.content
    assert b"<polyline" in resp.content  # the SVG line


@pytest.mark.django_db
def test_progress_page_hides_body_charts_when_no_data(alice, client):
    client.force_login(alice)
    resp = client.get(reverse("dashboard:progress"))
    assert "Composición corporal".encode() not in resp.content


@pytest.mark.django_db
def test_metrics_list_warns_when_height_missing(alice, client):
    from gymapp.apps.metrics.models import UserMetricSnapshot

    alice.profile.height_cm = None
    alice.profile.save()
    UserMetricSnapshot.objects.create(owner=alice, weight_kg="80.0", measured_at=timezone.now())
    client.force_login(alice)
    resp = client.get(reverse("metrics:list"))
    assert b"Para calcular tu BMI" in resp.content


@pytest.mark.django_db
def test_recovery_page_renders(alice, client):
    client.force_login(alice)
    resp = client.get(reverse("metrics:recovery"))
    assert resp.status_code == 200
    assert b"Recuperaci" in resp.content
    assert "¿Cómo amaneciste?".encode() in resp.content


@pytest.mark.django_db
def test_readiness_checkin_upserts_today(alice, client):
    from gymapp.apps.metrics.models import ReadinessSnapshot

    client.force_login(alice)
    resp = client.post(
        reverse("metrics:readiness_checkin"),
        {"sleep_quality": "4", "stress_level": "2", "soreness_overall": "3"},
    )
    assert resp.status_code == 302
    snap = ReadinessSnapshot.objects.get(owner=alice, date=timezone.localdate())
    assert snap.sleep_quality == 4
    assert snap.stress_level == 2
    assert snap.soreness_overall == 3

    # Second POST overwrites instead of creating a duplicate row.
    client.post(
        reverse("metrics:readiness_checkin"),
        {"sleep_quality": "5", "stress_level": "1", "soreness_overall": "1"},
    )
    assert ReadinessSnapshot.objects.filter(owner=alice, date=timezone.localdate()).count() == 1
    snap.refresh_from_db()
    assert snap.sleep_quality == 5


@pytest.mark.django_db
def test_readiness_checkin_clamps_out_of_range(alice, client):
    from gymapp.apps.metrics.models import ReadinessSnapshot

    client.force_login(alice)
    client.post(
        reverse("metrics:readiness_checkin"),
        {"sleep_quality": "99", "stress_level": "-5", "soreness_overall": "abc"},
    )
    snap = ReadinessSnapshot.objects.get(owner=alice, date=timezone.localdate())
    assert snap.sleep_quality == 5  # clamped up
    assert snap.stress_level == 1  # clamped down
    assert snap.soreness_overall == 3  # fallback


@pytest.mark.django_db
def test_fatigue_adjust_creates_and_stacks_and_clears(alice, client):
    from gymapp.apps.metrics.models import FatigueAdjustment

    client.force_login(alice)
    url = reverse("metrics:fatigue_adjust", args=["chest"])
    client.post(url, {"delta": "1"})
    client.post(url, {"delta": "2"})
    adj = FatigueAdjustment.objects.get(owner=alice, date=timezone.localdate(), muscle_slug="chest")
    assert adj.delta == 3.0
    # delta=0 removes the row (reset)
    client.post(url, {"delta": "0"})
    assert not FatigueAdjustment.objects.filter(
        owner=alice, date=timezone.localdate(), muscle_slug="chest"
    ).exists()


@pytest.mark.django_db
def test_dashboard_shows_advice_card(alice, client):
    client.force_login(alice)
    resp = client.get(reverse("dashboard:home"))
    assert resp.status_code == 200
    # No split + no readiness -> rest, card hidden. Add a readiness so it shows.
    from gymapp.apps.metrics.models import ReadinessSnapshot

    ReadinessSnapshot.objects.create(
        owner=alice,
        date=timezone.localdate(),
        sleep_quality=5,
        stress_level=1,
        soreness_overall=1,
    )
    resp2 = client.get(reverse("dashboard:home"))
    assert b"Estado de hoy" in resp2.content


@pytest.mark.django_db
def test_post_twice_overwrites_target(alice, client):
    """Restored after the bulk edit: confirms update_or_create keeps one row."""
    client.force_login(alice)
    url = reverse("metrics:goals")
    client.post(url, {"target_sessions": "10"})
    client.post(url, {"target_sessions": "20"})
    assert MonthlyGoal.objects.get(owner=alice).target_sessions == 20


@pytest.mark.django_db
def test_blank_fields_clear_targets(alice, client):
    client.force_login(alice)
    url = reverse("metrics:goals")
    client.post(url, {"target_sessions": "10", "target_bodyweight_kg": "78.5"})
    client.post(url, {"target_sessions": "", "target_bodyweight_kg": ""})
    goal = MonthlyGoal.objects.get(owner=alice)
    assert goal.target_sessions is None
    assert goal.target_bodyweight_kg is None


@pytest.mark.django_db
def test_goals_page_renders_progress_when_target_set(alice, client):
    today = timezone.localdate()
    MonthlyGoal.objects.create(
        owner=alice, year=today.year, month=today.month, target_sessions=8
    )
    client.force_login(alice)
    resp = client.get(reverse("metrics:goals"))
    assert resp.status_code == 200
    assert b"Entrenamientos" in resp.content
    assert b"width:" in resp.content  # progress bar rendered


@pytest.mark.django_db
def test_goals_page_requires_login(client):
    resp = client.get(reverse("metrics:goals"))
    assert resp.status_code == 302
    assert "/auth/login" in resp.url


@pytest.mark.django_db
def test_profile_edit_persists_sex_and_activity(alice, client):
    client.force_login(alice)
    resp = client.post(
        reverse("metrics:profile"),
        {
            "height_cm": "180",
            "date_of_birth": "1996-05-23",
            "sex": "male",
            "activity_level": "active",
            "training_style": "powerbuilding",
            "training_goal": "bulk",
            "default_rest_seconds": "120",
        },
    )
    assert resp.status_code == 302
    alice.profile.refresh_from_db()
    assert alice.profile.sex == "male"
    assert alice.profile.activity_level == "active"
    assert alice.profile.training_goal == "bulk"
