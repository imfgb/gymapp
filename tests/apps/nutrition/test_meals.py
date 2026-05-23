"""Tests for meal generation + saved-meal views."""

from __future__ import annotations

import random
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from gymapp.apps.metrics.models import UserMetricSnapshot
from gymapp.apps.nutrition.models import SavedMeal
from gymapp.apps.users.models import ActivityLevel, Sex, TrainingGoal
from gymapp.services.nutrition import (
    MacroTarget,
    all_food_slugs,
    generate_meal,
)
from tests.factories import UserFactory

TARGET = MacroTarget(calories=2000, protein_g=160, carbs_g=200, fat_g=60)


# ---------------------------------------------------------------------------
# catalogue expansion
# ---------------------------------------------------------------------------


def test_catalog_has_new_proteins_and_carbs():
    slugs = all_food_slugs()
    for slug in ("whey_isolate", "whey_concentrate", "salmon", "seitan", "brown_rice", "chia"):
        assert slug in slugs


# ---------------------------------------------------------------------------
# generate_meal service
# ---------------------------------------------------------------------------


def test_generate_meal_picks_from_preferences_within_categories():
    foods, macros = generate_meal(
        "breakfast", TARGET, ["chicken", "rice", "avocado"], rng=random.Random(0)  # noqa: S311
    )
    # breakfast = protein/carb/fat → one from each
    assert set(foods) == {"chicken", "rice", "avocado"}
    assert macros.calories == 500  # 2000 * 0.25
    assert macros.protein_g == 40


def test_generate_meal_empty_preferences_gives_no_foods():
    foods, macros = generate_meal("lunch", TARGET, [], rng=random.Random(1))  # noqa: S311
    assert foods == []
    assert macros.calories == 700  # 2000 * 0.35


def test_generate_meal_only_uses_liked_items():
    prefs = ["chicken", "beef", "salmon", "rice", "broccoli"]
    for seed in range(5):
        foods, _ = generate_meal("lunch", TARGET, prefs, rng=random.Random(seed))  # noqa: S311
        assert set(foods).issubset(set(prefs))


# ---------------------------------------------------------------------------
# views
# ---------------------------------------------------------------------------


@pytest.fixture
def alice(db):
    u = UserFactory(email="meals@example.com")
    p = u.profile
    p.height_cm = 180
    p.date_of_birth = date(1996, 5, 23)
    p.sex = Sex.MALE
    p.activity_level = ActivityLevel.MODERATE
    p.training_goal = TrainingGoal.MAINTAIN
    p.food_preferences = ["chicken", "rice", "avocado"]
    p.save()
    UserMetricSnapshot.objects.create(
        owner=u, measured_at=timezone.now(), weight_kg=Decimal("80")
    )
    return u


@pytest.mark.django_db
def test_generate_meal_view_creates_saved_meal(alice, client):
    client.force_login(alice)
    resp = client.post(reverse("nutrition:generate_meal"), {"slot": "breakfast"})
    assert resp.status_code == 302
    meal = SavedMeal.objects.get(owner=alice)
    assert meal.slot == "breakfast"
    assert meal.foods  # non-empty
    assert meal.calories > 0


@pytest.mark.django_db
def test_generate_meal_view_rejects_bad_slot(alice, client):
    client.force_login(alice)
    resp = client.post(reverse("nutrition:generate_meal"), {"slot": "brunch"})
    assert resp.status_code == 400
    assert not SavedMeal.objects.filter(owner=alice).exists()


@pytest.mark.django_db
def test_generate_meal_view_requires_complete_profile(client):
    bare = UserFactory(email="bare@example.com")
    client.force_login(bare)
    resp = client.post(reverse("nutrition:generate_meal"), {"slot": "lunch"})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_mark_done_toggles_eaten_at(alice, client):
    meal = SavedMeal.objects.create(owner=alice, slot="lunch", foods=["chicken"], calories=500)
    client.force_login(alice)
    client.post(reverse("nutrition:meal_done", args=[meal.id]))
    meal.refresh_from_db()
    assert meal.eaten_at is not None
    # toggle back off
    client.post(reverse("nutrition:meal_done", args=[meal.id]))
    meal.refresh_from_db()
    assert meal.eaten_at is None


@pytest.mark.django_db
def test_delete_meal(alice, client):
    meal = SavedMeal.objects.create(owner=alice, slot="snack", foods=["rice"], calories=200)
    client.force_login(alice)
    client.post(reverse("nutrition:meal_delete", args=[meal.id]))
    assert not SavedMeal.objects.filter(pk=meal.id).exists()


@pytest.mark.django_db
def test_meal_actions_are_owner_scoped(alice, client):
    other = UserFactory(email="intruder@example.com")
    meal = SavedMeal.objects.create(owner=other, slot="lunch", foods=["rice"], calories=300)
    client.force_login(alice)
    resp = client.post(reverse("nutrition:meal_delete", args=[meal.id]))
    assert resp.status_code == 404
    assert SavedMeal.objects.filter(pk=meal.id).exists()


@pytest.mark.django_db
def test_saved_meals_shown_on_nutrition_home(alice, client):
    SavedMeal.objects.create(owner=alice, slot="breakfast", foods=["chicken", "rice"], calories=600)
    client.force_login(alice)
    resp = client.get(reverse("nutrition:home"))
    assert resp.status_code == 200
    assert b"Mis comidas" in resp.content
    assert b"Generar comida" in resp.content
