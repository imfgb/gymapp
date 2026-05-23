"""Tests for the deterministic meal-plan builder."""

from __future__ import annotations

import pytest

from gymapp.services.nutrition import (
    FOOD_MACROS,
    MEAL_TEMPLATES,
    MacroTarget,
    MealTemplate,
    build_meal_plan,
)

TARGET = MacroTarget(calories=2000, protein_g=160, carbs_g=200, fat_g=60)


def test_four_slots_in_order():
    plan = build_meal_plan(TARGET, [])
    assert [s.label for s in plan] == ["Desayuno", "Comida", "Cena", "Snack"]


def test_every_slot_gets_a_coherent_meal_even_without_prefs():
    # With no preferences we fall back to slot templates (never an empty plate).
    plan = build_meal_plan(TARGET, [])
    assert all(s.foods for s in plan)
    assert all(s.calories > 0 for s in plan)


def test_plan_meals_come_from_real_templates():
    template_food_labels = set()
    for tpl in MEAL_TEMPLATES:
        for slug, _ in tpl.ingredients:
            from gymapp.services.nutrition import food_label

            template_food_labels.add(food_label(slug))
    plan = build_meal_plan(TARGET, [])
    for slot in plan:
        for food in slot.foods:
            assert food in template_food_labels


def test_all_template_ingredients_have_macros():
    # every template ingredient must exist in FOOD_MACROS (no orphan slugs)
    for tpl in MEAL_TEMPLATES:
        for slug, _ in tpl.ingredients:
            assert slug in FOOD_MACROS, f"{slug} missing from FOOD_MACROS"


def test_templates_are_well_formed():
    for tpl in MEAL_TEMPLATES:
        assert isinstance(tpl, MealTemplate)
        assert tpl.slots  # fits at least one slot
        roles = {role for _, role in tpl.ingredients}
        assert roles <= {"protein", "carb", "fat", "veg"}
        # a real meal has a protein anchor
        assert any(role == "protein" for _, role in tpl.ingredients)


def test_preferences_select_a_matching_template():
    # liking exactly the "Pollo, arroz y brócoli" mains makes lunch use it
    prefs = ["chicken", "rice"]  # broccoli is veg → not required
    plan = {s.key: s for s in build_meal_plan(TARGET, prefs)}
    assert "Pollo" in plan["lunch"].foods
    assert "Arroz" in plan["lunch"].foods


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
    assert b"Plan sugerido del d" in resp.content  # "Plan sugerido del día"
    assert b"Desayuno" in resp.content
    assert b"Pollo" in resp.content
