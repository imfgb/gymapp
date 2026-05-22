"""Tests for the metrics app — owner scoping + ordering."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from gymapp.apps.metrics.models import UserMetricSnapshot
from tests.factories import UserFactory


@pytest.fixture
def alice(db):
    return UserFactory(email="alice@example.com")


@pytest.fixture
def bob(db):
    return UserFactory(email="bob@example.com")


@pytest.mark.django_db
def test_snapshot_for_user_scoping(alice, bob):
    now = timezone.now()
    UserMetricSnapshot.objects.create(owner=alice, measured_at=now, weight_kg=Decimal("75.0"))
    UserMetricSnapshot.objects.create(owner=bob, measured_at=now, weight_kg=Decimal("80.0"))

    assert UserMetricSnapshot.objects.for_user(alice).count() == 1
    assert UserMetricSnapshot.objects.for_user(bob).count() == 1


@pytest.mark.django_db
def test_snapshots_ordered_newest_first(alice):
    now = timezone.now()
    older = UserMetricSnapshot.objects.create(
        owner=alice, measured_at=now - timedelta(days=7), weight_kg=Decimal("76")
    )
    newer = UserMetricSnapshot.objects.create(owner=alice, measured_at=now, weight_kg=Decimal("75"))

    rows = list(UserMetricSnapshot.objects.for_user(alice))
    assert rows[0].pk == newer.pk
    assert rows[1].pk == older.pk


@pytest.mark.django_db
def test_body_fat_pct_optional(alice):
    snap = UserMetricSnapshot.objects.create(
        owner=alice, measured_at=timezone.now(), weight_kg=Decimal("75")
    )
    assert snap.body_fat_pct is None
