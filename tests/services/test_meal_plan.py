"""Tests for the deterministic meal-plan builder."""

from __future__ import annotations

import pytest

from gymapp.services.nutrition import MacroTarget, build_meal_plan

TARGET = MacroTarget(calories=2000, protein_g=160, carbs_g=200, fat_g=60)


def test_four_slots_in_order():
    plan = build_meal_plan(TARGET, [])
    assert [s.label for s in plan] == ["Desayuno", "Comida", "Cena", "Snack"]


def test_calorie_split_sums_to_target():
    plan = build_meal_plan(TARGET, [])
    total = sum(s.calories for s in plan)
    assert abs(total - TARGET.calories) <= 4  # rounding tolerance


def test_breakfast_macro_share():
    breakfast = build_meal_plan(TARGET, [])[0]
    assert breakfast.calories == 500   # 25%
    assert breakfast.protein_g == 40
    assert breakfast.carbs_g == 50
    assert breakfast.fat_g == 15


def test_no_preferences_means_empty_food_lists():
    plan = build_meal_plan(TARGET, [])
    assert all(s.foods == [] for s in plan)


def test_foods_drawn_from_preferences_and_rotate():
    prefs = ["chicken", "beef", "rice", "oats", "broccoli", "avocado"]
    plan = {s.key: s for s in build_meal_plan(TARGET, prefs)}
    # breakfast = protein/carb/fat → chicken, rice, avocado
    assert plan["breakfast"].foods == ["Pollo", "Arroz", "Aguacate"]
    # lunch = protein/carb/vegetable, rotated by slot index → beef, oats, broccoli
    assert plan["lunch"].foods == ["Res", "Avena", "Brócoli"]
    # rotation actually differs between slots
    assert plan["breakfast"].foods != plan["lunch"].foods


def test_slot_skips_categories_without_liked_items():
    # only a protein liked → snack (protein, carb) lists just the protein
    plan = {s.key: s for s in build_meal_plan(TARGET, ["chicken"])}
    assert plan["snack"].foods == ["Pollo"]
    assert plan["lunch"].foods == ["Pollo"]  # carb + vegetable skipped


@pytest.mark.django_db
def test_meal_plan_shown_on_nutrition_home(client):
    from datetime import date
    from decimal import Decimal

    from django.urls import reverse
    from django.utils import timezone

    from gymapp.apps.metrics.models import UserMetricSnapshot
    from gymapp.apps.users.models import ActivityLevel, Sex, TrainingGoal
    from tests.factories import UserFactory

    user = UserFactory(email="mealplan@example.com")
    p = user.profile
    p.height_cm = 180
    p.date_of_birth = date(1996, 5, 23)
    p.sex = Sex.MALE
    p.activity_level = ActivityLevel.MODERATE
    p.training_goal = TrainingGoal.MAINTAIN
    p.food_preferences = ["chicken", "rice"]
    p.save()
    UserMetricSnapshot.objects.create(
        owner=user, measured_at=timezone.now(), weight_kg=Decimal("80")
    )
    client.force_login(user)
    resp = client.get(reverse("nutrition:home"))
    assert resp.status_code == 200
    assert b"Tu plan de comidas" in resp.content
    assert b"Desayuno" in resp.content
    assert b"Pollo" in resp.content
