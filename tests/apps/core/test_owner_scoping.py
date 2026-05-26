"""Regression tests for OwnerScopedQuerySet.for_user().

A past bug let `for_user(superuser)` return EVERY user's rows on regular pages
(dashboard, routines, metrics, PRs). Superuser-sees-all belongs in `/admin`
only (via OwnerScopedAdmin), not in the app's data-reading code path.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from gymapp.apps.metrics.models import UserMetricSnapshot
from gymapp.apps.routines.models import Routine
from tests.factories import UserFactory


@pytest.mark.django_db
def test_for_user_does_not_leak_across_users_for_superuser():
    superuser = UserFactory(email="su@example.com", is_superuser=True, is_staff=True)
    bob = UserFactory(email="bob@example.com")
    Routine.objects.create(owner=bob, name="Bob's routine")

    # Even though superuser is_superuser=True, for_user must NOT return bob's row.
    assert list(Routine.objects.for_user(superuser)) == []
    assert Routine.objects.for_user(bob).count() == 1


@pytest.mark.django_db
def test_dashboard_does_not_show_other_users_data_to_superuser(client):
    superuser = UserFactory(email="su@example.com", is_superuser=True, is_staff=True)
    bob = UserFactory(email="bob@example.com")
    Routine.objects.create(owner=bob, name="BobSecretRoutine")
    from django.utils import timezone
    UserMetricSnapshot.objects.create(owner=bob, weight_kg=99, measured_at=timezone.now())

    client.force_login(superuser)
    resp = client.get(reverse("dashboard:home"))
    assert resp.status_code == 200
    # Bob's data must not appear on the superuser's dashboard.
    assert b"BobSecretRoutine" not in resp.content

    resp_routines = client.get(reverse("routines:list"))
    assert b"BobSecretRoutine" not in resp_routines.content

    resp_metrics = client.get(reverse("metrics:list"))
    # Superuser is isolated -> metrics table is empty.
    assert "Aún no has registrado mediciones".encode() in resp_metrics.content
    assert b"99.0 kg" not in resp_metrics.content
    assert b"99 kg" not in resp_metrics.content


@pytest.mark.django_db
def test_for_user_returns_empty_for_anonymous():
    from django.contrib.auth.models import AnonymousUser

    bob = UserFactory(email="bob@example.com")
    Routine.objects.create(owner=bob, name="X")

    assert Routine.objects.for_user(AnonymousUser()).count() == 0
    assert Routine.objects.for_user(None).count() == 0
