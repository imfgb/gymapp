"""Tests for the deterministic nutrition service."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from gymapp.apps.metrics.models import UserMetricSnapshot
from gymapp.apps.users.models import ActivityLevel, Sex, TrainingGoal
from gymapp.services.nutrition import (
    DeterministicNutrition,
    age_from_dob,
    bmr_mifflin_st_jeor,
    daily_target_for_user,
)
from tests.factories import UserFactory

STRAT = DeterministicNutrition()


# ---------------------------------------------------------------------------
# BMR / age helpers
# ---------------------------------------------------------------------------


def test_bmr_male():
    # 10*80 + 6.25*180 - 5*30 + 5
    assert bmr_mifflin_st_jeor(80, 180, 30, "male") == 1780.0


def test_bmr_female():
    # 10*80 + 6.25*180 - 5*30 - 161
    assert bmr_mifflin_st_jeor(80, 180, 30, "female") == 1614.0


def test_age_from_dob_before_and_on_birthday():
    dob = date(1996, 5, 23)
    assert age_from_dob(dob, today=date(2026, 5, 22)) == 29
    assert age_from_dob(dob, today=date(2026, 5, 23)) == 30


# ---------------------------------------------------------------------------
# recommend()
# ---------------------------------------------------------------------------


def test_maintain_target():
    t = STRAT.recommend(
        weight_kg=80, height_cm=180, age=30, sex="male",
        activity_factor=1.55, goal="maintain",
    )
    # TDEE = 1780 * 1.55 = 2759
    assert t.calories == 2759
    assert t.protein_g == 160  # 2.0 g/kg
    assert t.fat_g == 64       # 0.8 g/kg
    assert t.carbs_g == 386    # (2759 - 640 - 576) / 4


def test_cut_uses_deficit_and_higher_protein():
    t = STRAT.recommend(
        weight_kg=80, height_cm=180, age=30, sex="male",
        activity_factor=1.55, goal="cut",
    )
    assert t.calories == 2207  # 2759 * 0.80
    assert t.protein_g == 176  # 2.2 g/kg on a cut
    assert t.fat_g == 64
    assert t.carbs_g == 232


def test_bulk_uses_surplus():
    t = STRAT.recommend(
        weight_kg=80, height_cm=180, age=30, sex="male",
        activity_factor=1.55, goal="bulk",
    )
    assert t.calories == 3035  # round(2759 * 1.10)
    assert t.protein_g == 160
    assert t.carbs_g == 455


def test_carbs_clamped_to_zero_when_protein_fat_exceed_calories():
    t = STRAT.recommend(
        weight_kg=120, height_cm=150, age=60, sex="female",
        activity_factor=1.2, goal="cut",
    )
    # protein(264)*4 + fat(96)*9 = 1920 > ~1609 kcal target → carbs floor at 0
    assert t.carbs_g == 0
    assert t.protein_g == 264
    assert t.fat_g == 96


# ---------------------------------------------------------------------------
# daily_target_for_user (DB)
# ---------------------------------------------------------------------------


@pytest.fixture
def alice(db):
    return UserFactory(email="nutri@example.com")


def _complete_profile(user, *, weight="80"):
    p = user.profile
    p.height_cm = 180
    p.date_of_birth = date(1996, 5, 23)
    p.sex = Sex.MALE
    p.activity_level = ActivityLevel.MODERATE
    p.training_goal = TrainingGoal.MAINTAIN
    p.save()
    UserMetricSnapshot.objects.create(
        owner=user, measured_at=timezone.now(), weight_kg=Decimal(weight)
    )


@pytest.mark.django_db
def test_daily_target_complete_profile(alice):
    _complete_profile(alice)
    target, missing = daily_target_for_user(alice)
    assert missing == []
    assert target is not None
    assert target.protein_g == 160


@pytest.mark.django_db
def test_daily_target_missing_weight(alice):
    p = alice.profile
    p.height_cm = 180
    p.date_of_birth = date(1996, 5, 23)
    p.sex = Sex.MALE
    p.save()
    target, missing = daily_target_for_user(alice)
    assert target is None
    assert "weight" in missing


@pytest.mark.django_db
def test_daily_target_missing_sex(alice):
    p = alice.profile
    p.height_cm = 180
    p.date_of_birth = date(1996, 5, 23)
    p.sex = ""
    p.save()
    UserMetricSnapshot.objects.create(
        owner=alice, measured_at=timezone.now(), weight_kg=Decimal("80")
    )
    target, missing = daily_target_for_user(alice)
    assert target is None
    assert "sex" in missing
