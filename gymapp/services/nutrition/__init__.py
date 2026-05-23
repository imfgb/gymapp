"""Nutrition service — Phase 3.

Deterministic daily energy + macro targets:

- **BMR** via Mifflin-St Jeor.
- **TDEE** = BMR × activity factor (selectable per user).
- **Calorie target** = TDEE × a goal multiplier (cut / bulk / recomp / …).
- **Macros** protein-first by bodyweight, fat floor by bodyweight, carbs fill
  the remaining calories.

`recommend()` is the AI seam (Protocol): a future `LLMStrategy` can replace the
deterministic implementation without touching `daily_target_for_user` or the
views. No AI in MVP (CLAUDE.md §15).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from django.utils import timezone

# Standard Harris/Mifflin activity multipliers.
ACTIVITY_FACTORS: dict[str, float] = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}
DEFAULT_ACTIVITY_FACTOR = ACTIVITY_FACTORS["moderate"]

# Calorie adjustment relative to maintenance (TDEE), keyed by training goal.
GOAL_CALORIE_MULTIPLIER: dict[str, float] = {
    "cut": 0.80,
    "bulk": 1.10,
    "hypertrophy": 1.10,
    "strength": 1.05,
    "recomposition": 1.00,
    "maintain": 1.00,
}

PROTEIN_G_PER_KG = 2.0
PROTEIN_G_PER_KG_CUT = 2.2  # higher on a deficit to spare lean mass
FAT_G_PER_KG = 0.8


@dataclass(frozen=True)
class MacroTarget:
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int


def bmr_mifflin_st_jeor(weight_kg: float, height_cm: float, age: int, sex: str) -> float:
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + (5 if sex == "male" else -161)


class NutritionStrategy(Protocol):
    def recommend(
        self,
        weight_kg: float,
        height_cm: float,
        age: int,
        sex: str,
        activity_factor: float,
        goal: str,
    ) -> MacroTarget: ...


class DeterministicNutrition:
    """Formula-based targets. No history, no AI."""

    def recommend(
        self,
        weight_kg: float,
        height_cm: float,
        age: int,
        sex: str,
        activity_factor: float,
        goal: str,
    ) -> MacroTarget:
        w = float(weight_kg)
        bmr = bmr_mifflin_st_jeor(w, float(height_cm), int(age), sex)
        tdee = bmr * float(activity_factor)
        calories = tdee * GOAL_CALORIE_MULTIPLIER.get(goal, 1.0)

        protein_per_kg = PROTEIN_G_PER_KG_CUT if goal == "cut" else PROTEIN_G_PER_KG
        protein_g = round(protein_per_kg * w)
        fat_g = round(FAT_G_PER_KG * w)
        remaining_cal = calories - protein_g * 4 - fat_g * 9
        carbs_g = max(0, round(remaining_cal / 4))

        return MacroTarget(
            calories=round(calories),
            protein_g=protein_g,
            carbs_g=carbs_g,
            fat_g=fat_g,
        )


def age_from_dob(dob: date, today: date | None = None) -> int:
    today = today or timezone.localdate()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def daily_target_for_user(user) -> tuple[MacroTarget | None, list[str]]:
    """Resolve a user's inputs into a daily target.

    Bodyweight comes from the latest `UserMetricSnapshot`; height / DOB / sex
    from `Profile`. Returns `(target, [])` when complete, or `(None, missing)`
    where `missing` lists the field keys still needed so the view can prompt.
    """
    from gymapp.apps.metrics.models import UserMetricSnapshot

    profile = user.profile
    latest = (
        UserMetricSnapshot.objects.filter(owner=user).order_by("-measured_at").first()
    )
    weight = latest.weight_kg if latest else None

    missing: list[str] = []
    if weight is None:
        missing.append("weight")
    if profile.height_cm is None:
        missing.append("height")
    if profile.date_of_birth is None:
        missing.append("date_of_birth")
    if not profile.sex:
        missing.append("sex")
    if missing:
        return None, missing

    factor = ACTIVITY_FACTORS.get(profile.activity_level, DEFAULT_ACTIVITY_FACTOR)
    target = DeterministicNutrition().recommend(
        weight_kg=weight,
        height_cm=profile.height_cm,
        age=age_from_dob(profile.date_of_birth),
        sex=profile.sex,
        activity_factor=factor,
        goal=profile.training_goal,
    )
    return target, []
