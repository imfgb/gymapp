"""Tests for the supplements feature (tracking + daily mark-taken)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from gymapp.apps.nutrition.models import Supplement
from tests.factories import UserFactory


@pytest.fixture
def alice(db):
    return UserFactory(email="supps@example.com")


@pytest.mark.django_db
def test_add_common_supplement(alice, client):
    client.force_login(alice)
    resp = client.post(reverse("nutrition:supplement_add"), {"name": "Creatina"})
    assert resp.status_code == 302
    assert Supplement.objects.for_user(alice).filter(name="Creatina").exists()


@pytest.mark.django_db
def test_add_custom_supplement(alice, client):
    client.force_login(alice)
    client.post(reverse("nutrition:supplement_add"), {"name": "  Tribulus  "})
    supp = Supplement.objects.for_user(alice).get()
    assert supp.name == "Tribulus"  # trimmed


@pytest.mark.django_db
def test_add_is_idempotent(alice, client):
    client.force_login(alice)
    client.post(reverse("nutrition:supplement_add"), {"name": "Omega 3"})
    client.post(reverse("nutrition:supplement_add"), {"name": "Omega 3"})
    assert Supplement.objects.for_user(alice).filter(name="Omega 3").count() == 1


@pytest.mark.django_db
def test_add_empty_name_does_nothing(alice, client):
    client.force_login(alice)
    client.post(reverse("nutrition:supplement_add"), {"name": "   "})
    assert not Supplement.objects.for_user(alice).exists()


@pytest.mark.django_db
def test_take_toggles_and_stamps_time(alice, client):
    supp = Supplement.objects.create(owner=alice, name="Creatina")
    client.force_login(alice)
    client.post(reverse("nutrition:supplement_take", args=[supp.id]))
    supp.refresh_from_db()
    assert supp.last_taken_at is not None
    assert supp.taken_today is True
    # toggle off
    client.post(reverse("nutrition:supplement_take", args=[supp.id]))
    supp.refresh_from_db()
    assert supp.last_taken_at is None
    assert supp.taken_today is False


@pytest.mark.django_db
def test_taken_yesterday_is_not_taken_today(alice):
    supp = Supplement.objects.create(
        owner=alice,
        name="Creatina",
        last_taken_at=timezone.now() - timedelta(days=1),
    )
    assert supp.taken_today is False


@pytest.mark.django_db
def test_delete_supplement(alice, client):
    supp = Supplement.objects.create(owner=alice, name="Zinc")
    client.force_login(alice)
    client.post(reverse("nutrition:supplement_delete", args=[supp.id]))
    assert not Supplement.objects.filter(pk=supp.id).exists()


@pytest.mark.django_db
def test_supplement_actions_are_owner_scoped(alice, client):
    other = UserFactory(email="intruder-supps@example.com")
    supp = Supplement.objects.create(owner=other, name="Creatina")
    client.force_login(alice)
    resp = client.post(reverse("nutrition:supplement_delete", args=[supp.id]))
    assert resp.status_code == 404
    assert Supplement.objects.filter(pk=supp.id).exists()


@pytest.mark.django_db
def test_manage_page_hides_already_added_common(alice, client):
    Supplement.objects.create(owner=alice, name="Creatina")
    client.force_login(alice)
    resp = client.get(reverse("nutrition:supplements"))
    body = resp.content.decode()
    # already-added one shows in "Mis suplementos" but not as a quick-add suggestion
    assert "Creatina" in body
    assert "+ Omega 3" in body  # a still-available suggestion
    assert "+ Creatina" not in body


@pytest.mark.django_db
def test_home_shows_supplement_checklist(alice, client):
    Supplement.objects.create(owner=alice, name="Creatina")
    client.force_login(alice)
    resp = client.get(reverse("nutrition:home"))
    assert b"Suplementos de hoy" in resp.content
    assert b"Creatina" in resp.content
    assert b"Marcar tomado" in resp.content
