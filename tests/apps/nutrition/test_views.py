"""Tests for the nutrition page."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from gymapp.apps.metrics.models import UserMetricSnapshot
from gymapp.apps.users.models import ActivityLevel, Sex, TrainingGoal
from tests.factories import UserFactory


@pytest.fixture
def alice(db):
    return UserFactory(email="nutriview@example.com")


@pytest.mark.django_db
def test_nutrition_page_shows_target_when_profile_complete(alice, client):
    p = alice.profile
    p.height_cm = 180
    p.date_of_birth = date(1996, 5, 23)
    p.sex = Sex.MALE
    p.activity_level = ActivityLevel.MODERATE
    p.training_goal = TrainingGoal.MAINTAIN
    p.save()
    UserMetricSnapshot.objects.create(
        owner=alice, measured_at=timezone.now(), weight_kg=Decimal("80")
    )
    client.force_login(alice)
    resp = client.get(reverse("nutrition:home"))
    assert resp.status_code == 200
    assert b"kcal" in resp.content
    assert b"2759" in resp.content
    assert b"160" in resp.content  # protein


@pytest.mark.django_db
def test_nutrition_page_prompts_when_incomplete(alice, client):
    client.force_login(alice)
    resp = client.get(reverse("nutrition:home"))
    assert resp.status_code == 200
    assert b"Faltan algunos datos" in resp.content


@pytest.mark.django_db
def test_nutrition_page_requires_login(client):
    resp = client.get(reverse("nutrition:home"))
    assert resp.status_code == 302
    assert "/auth/login" in resp.url
