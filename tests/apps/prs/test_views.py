"""PR views — weight unit conversion + display (feedback #8)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from gymapp.apps.exercises.models import Equipment
from gymapp.apps.prs.models import PersonalRecord
from tests.factories import ExerciseFactory, UserFactory


@pytest.fixture
def alice(db):
    return UserFactory(email="alice.prs@example.com")


@pytest.mark.django_db
def test_pr_create_converts_lb_to_kg(client, alice):
    cable = Equipment.objects.get(slug="cable")
    ex = ExerciseFactory(slug="cable-fly", equipment=cable)  # auto lb
    client.force_login(alice)

    client.post(reverse("prs:create"), {"exercise": ex.slug, "weight_kg": "100", "reps": "10"})

    pr = PersonalRecord.objects.get(owner=alice, exercise=ex, reps=10)
    assert pr.weight_kg == Decimal("45.36")  # 100 lb stored as kg


@pytest.mark.django_db
def test_pr_list_displays_weight_in_lb(client, alice):
    cable = Equipment.objects.get(slug="cable")
    ex = ExerciseFactory(slug="cable-fly", equipment=cable)
    PersonalRecord.objects.create(
        owner=alice, exercise=ex, reps=10, weight_kg=Decimal("45.36"), achieved_at=timezone.now()
    )
    client.force_login(alice)

    content = client.get(reverse("prs:list")).content.decode()
    assert "100.0 lb" in content
