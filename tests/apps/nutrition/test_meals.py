"""Tests for meal generation + saved-meal views."""

from __future__ import annotations

import random
from datetime import date, timedelta
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


def test_catalog_keeps_kept_foods_and_drops_removed():
    slugs = all_food_slugs()
    for kept in ("whey_isolate", "whey_concentrate", "casein", "salmon", "brown_rice", "banana"):
        assert kept in slugs
    for removed in ("pea_protein", "whey", "cottage_cheese", "seitan", "edamame",
                    "soy_protein", "tempeh", "fruit", "kale", "egg_yolk", "chia",
                    "flax", "walnuts"):
        assert removed not in slugs


# ---------------------------------------------------------------------------
# generate_meal service
# ---------------------------------------------------------------------------


def test_generate_meal_uses_a_coherent_template_with_grams():
    # liking the mains of "Avena con whey y plátano" → that breakfast template
    prefs = ["whey_isolate", "oats", "banana", "peanut_butter"]
    meal = generate_meal("breakfast", TARGET, prefs, rng=random.Random(0))  # noqa: S311
    assert {i.slug for i in meal.items}.issubset(set(prefs))
    assert all(i.grams > 0 for i in meal.items)
    assert meal.protein_g > 0
    # totals equal the sum of the items (grams explain the macros)
    assert meal.calories == sum(i.calories for i in meal.items)


def test_generate_meal_falls_back_to_a_template_without_prefs():
    # No prefs → still a coherent meal (never an empty/odd plate).
    meal = generate_meal("lunch", TARGET, [], rng=random.Random(1))  # noqa: S311
    assert meal.items  # non-empty
    assert meal.calories > 0


def test_generate_meal_only_uses_liked_items():
    # prefs cover two lunch templates fully (incl. their veg)
    prefs = ["chicken", "rice", "broccoli", "lean_beef", "potato", "asparagus"]
    for seed in range(6):
        meal = generate_meal("lunch", TARGET, prefs, rng=random.Random(seed))  # noqa: S311
        assert {i.slug for i in meal.items}.issubset(set(prefs))


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
    p.food_preferences = [
        "chicken", "rice", "broccoli",  # lunch/dinner template
        "whey_isolate", "oats", "banana", "peanut_butter",  # breakfast template
    ]
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
    assert isinstance(meal.foods[0], dict)
    assert meal.foods[0]["grams"] > 0
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
def test_saved_meals_show_grams_and_per_food_calories(alice, client):
    SavedMeal.objects.create(
        owner=alice,
        slot="breakfast",
        foods=[
            {"slug": "chicken", "grams": 150, "protein_g": 47, "carbs_g": 0, "fat_g": 5, "calories": 233},
            {"slug": "rice", "grams": 80, "protein_g": 6, "carbs_g": 64, "fat_g": 1, "calories": 289},
        ],
        calories=522,
        protein_g=53,
    )
    client.force_login(alice)
    resp = client.get(reverse("nutrition:home"))
    assert resp.status_code == 200
    assert b"Mis comidas" in resp.content
    assert b"Generar comida" in resp.content
    assert b"150 g" in resp.content
    assert b"Pollo" in resp.content
    # per-food calories shown
    assert b"233 kcal" in resp.content
    assert b"289 kcal" in resp.content
    # final sum shown
    assert b"522 kcal" in resp.content


@pytest.mark.django_db
def test_saved_meals_ordered_breakfast_lunch_dinner(alice, client):
    # created out of order; the page lists them by slot order
    SavedMeal.objects.create(owner=alice, slot="dinner", foods=[], calories=700)
    SavedMeal.objects.create(owner=alice, slot="breakfast", foods=[], calories=500)
    SavedMeal.objects.create(owner=alice, slot="lunch", foods=[], calories=600)
    client.force_login(alice)
    resp = client.get(reverse("nutrition:home"))
    body = resp.content.decode()
    section = body[body.index("Mis comidas"):]
    assert section.index("Desayuno") < section.index("Comida") < section.index("Cena")


@pytest.mark.django_db
def test_suggested_plan_removed_from_page(alice, client):
    client.force_login(alice)
    resp = client.get(reverse("nutrition:home"))
    assert b"Plan sugerido" not in resp.content


@pytest.mark.django_db
def test_only_todays_meals_are_shown(alice, client):
    # Yesterday's meal must not appear today (daily reset, no job).
    old = SavedMeal.objects.create(owner=alice, slot="lunch", foods=[], calories=999)
    SavedMeal.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=1)
    )
    today_meal = SavedMeal.objects.create(owner=alice, slot="breakfast", foods=[], calories=111)
    client.force_login(alice)
    resp = client.get(reverse("nutrition:home"))
    body = resp.content.decode()
    assert "111 kcal" in body  # today's
    assert "999 kcal" not in body  # yesterday's gone
    assert str(today_meal.calories) in body
