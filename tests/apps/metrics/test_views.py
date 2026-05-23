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
        {"target_sessions": "16", "target_volume_kg": "50000", "target_bodyweight_kg": "78.5"},
    )
    assert resp.status_code == 302
    today = timezone.localdate()
    goal = MonthlyGoal.objects.get(owner=alice, year=today.year, month=today.month)
    assert goal.target_sessions == 16
    assert goal.target_volume_kg == Decimal("50000")
    assert goal.target_bodyweight_kg == Decimal("78.5")


@pytest.mark.django_db
def test_post_twice_updates_same_row(alice, client):
    client.force_login(alice)
    url = reverse("metrics:goals")
    client.post(url, {"target_sessions": "10"})
    client.post(url, {"target_sessions": "20"})
    assert MonthlyGoal.objects.filter(owner=alice).count() == 1
    assert MonthlyGoal.objects.get(owner=alice).target_sessions == 20


@pytest.mark.django_db
def test_blank_fields_clear_targets(alice, client):
    client.force_login(alice)
    url = reverse("metrics:goals")
    client.post(url, {"target_sessions": "10", "target_volume_kg": "1000"})
    client.post(url, {"target_sessions": "", "target_volume_kg": ""})
    goal = MonthlyGoal.objects.get(owner=alice)
    assert goal.target_sessions is None
    assert goal.target_volume_kg is None


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
