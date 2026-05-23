"""Tests for the training-block page."""

from __future__ import annotations

import pytest
from django.urls import reverse
from django.utils import timezone

from gymapp.apps.routines.models import TrainingBlock
from tests.factories import UserFactory


@pytest.fixture
def alice(db):
    return UserFactory(email="block@example.com")


@pytest.mark.django_db
def test_block_page_prompts_when_none(alice, client):
    client.force_login(alice)
    resp = client.get(reverse("routines:block"))
    assert resp.status_code == 200
    assert b"No tienes un bloque activo" in resp.content


@pytest.mark.django_db
def test_post_starts_block_today(alice, client):
    client.force_login(alice)
    resp = client.post(reverse("routines:block"), {"training_style": "powerlifting"})
    assert resp.status_code == 302
    block = TrainingBlock.objects.get(owner=alice)
    assert block.training_style == "powerlifting"
    assert block.started_on == timezone.localdate()
    assert block.length_weeks == 6


@pytest.mark.django_db
def test_block_page_shows_current_week(alice, client):
    TrainingBlock.objects.create(
        owner=alice, training_style="bodybuilding", started_on=timezone.localdate()
    )
    client.force_login(alice)
    resp = client.get(reverse("routines:block"))
    assert resp.status_code == 200
    assert b"Semana 1" in resp.content
    assert b"Plan del bloque" in resp.content


@pytest.mark.django_db
def test_invalid_style_rejected(alice, client):
    client.force_login(alice)
    resp = client.post(reverse("routines:block"), {"training_style": "bogus"})
    assert resp.status_code == 400
    assert not TrainingBlock.objects.filter(owner=alice).exists()


@pytest.mark.django_db
def test_block_requires_login(client):
    resp = client.get(reverse("routines:block"))
    assert resp.status_code == 302
    assert "/auth/login" in resp.url


@pytest.mark.django_db
def test_latest_block_is_shown(alice, client):
    from datetime import timedelta

    old = timezone.localdate() - timedelta(days=60)
    TrainingBlock.objects.create(owner=alice, training_style="powerlifting", started_on=old)
    TrainingBlock.objects.create(
        owner=alice, training_style="bodybuilding", started_on=timezone.localdate()
    )
    client.force_login(alice)
    resp = client.get(reverse("routines:block"))
    # newest block (bodybuilding, started today) drives the current-week card
    assert b"Semana 1" in resp.content
