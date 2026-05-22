"""Nutrition service — Phase 3.

Will compute BMR (Mifflin-St Jeor), TDEE, bulk/cut/recomp recommendation, and
macro split. Interface stub only in Phase 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class MacroTarget:
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int


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
    """Phase 0 stub — returns zeroes so callers don't crash."""

    def recommend(
        self,
        weight_kg: float,
        height_cm: float,
        age: int,
        sex: str,
        activity_factor: float,
        goal: str,
    ) -> MacroTarget:
        return MacroTarget(calories=0, protein_g=0, carbs_g=0, fat_g=0)
