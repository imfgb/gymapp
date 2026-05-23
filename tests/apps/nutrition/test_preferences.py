"""Tests for food preferences (catalog helpers + editor view)."""

from __future__ import annotations

import pytest
from django.urls import reverse

from gymapp.services.nutrition import (
    all_food_slugs,
    clean_food_preferences,
    food_label,
    grouped_catalog,
)
from tests.factories import UserFactory


@pytest.fixture
def alice(db):
    return UserFactory(email="prefs@example.com")


# ---------------------------------------------------------------------------
# Catalog helpers
# ---------------------------------------------------------------------------


def test_catalog_has_expected_categories():
    keys = [g["key"] for g in grouped_catalog()]
    assert keys == ["protein", "carb", "vegetable", "fat"]


def test_food_label_maps_known_slug_and_falls_back():
    assert food_label("chicken") == "Pollo"
    assert food_label("unknown-thing") == "unknown-thing"


def test_clean_food_preferences_drops_unknown_and_dedupes():
    cleaned = clean_food_preferences(["chicken", "chicken", "not_a_food", "rice"])
    assert "not_a_food" not in cleaned
    assert sorted(cleaned) == ["chicken", "rice"]  # deduped


def test_clean_food_preferences_follows_catalog_order():
    # eggs comes before tuna in the catalog regardless of input order
    cleaned = clean_food_preferences(["tuna", "eggs"])
    assert cleaned.index("eggs") < cleaned.index("tuna")


def test_grouped_catalog_marks_selected():
    groups = {g["key"]: g for g in grouped_catalog(["chicken"])}
    chicken = next(i for i in groups["protein"]["items"] if i["slug"] == "chicken")
    assert chicken["selected"] is True


# ---------------------------------------------------------------------------
# Editor view
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_preferences_page_renders(alice, client):
    client.force_login(alice)
    resp = client.get(reverse("nutrition:preferences"))
    assert resp.status_code == 200
    assert "Proteínas".encode() in resp.content
    assert b"Pollo" in resp.content


@pytest.mark.django_db
def test_preferences_post_saves_valid_only(alice, client):
    client.force_login(alice)
    resp = client.post(
        reverse("nutrition:preferences"),
        {"food": ["chicken", "rice", "broccoli", "bogus_food"]},
    )
    assert resp.status_code == 302
    alice.profile.refresh_from_db()
    assert set(alice.profile.food_preferences) == {"chicken", "rice", "broccoli"}


@pytest.mark.django_db
def test_preferences_post_empty_clears(alice, client):
    alice.profile.food_preferences = ["chicken"]
    alice.profile.save()
    client.force_login(alice)
    client.post(reverse("nutrition:preferences"), {})
    alice.profile.refresh_from_db()
    assert alice.profile.food_preferences == []


@pytest.mark.django_db
def test_preferences_requires_login(client):
    resp = client.get(reverse("nutrition:preferences"))
    assert resp.status_code == 302
    assert "/auth/login" in resp.url


@pytest.mark.django_db
def test_preference_count_shown_on_nutrition_home(alice, client):
    alice.profile.food_preferences = ["chicken", "rice"]
    alice.profile.save()
    client.force_login(alice)
    resp = client.get(reverse("nutrition:home"))
    assert resp.status_code == 200
    assert b"2 alimentos seleccionados" in resp.content


def test_all_food_slugs_nonempty():
    assert "chicken" in all_food_slugs()
    assert len(all_food_slugs()) > 20
