"""Progression service.

Phase 1: `recommend_next` returns the last completed weight*reps verbatim
(no progression — just a placeholder so the workout screen can render).

Phase 2: linear / double progression rules per training style.
Phase 4: optional LLMStrategy that reasons over history.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SetRecommendation:
    weight_kg: float
    reps: int
    rationale: str = ""


class ProgressionStrategy(Protocol):
    def recommend_next(
        self, exercise_slug: str, history: list[SetRecommendation]
    ) -> SetRecommendation:
        ...


class DeterministicProgression:
    """Phase 0 stub. Returns a 0/0 placeholder so views compile."""

    def recommend_next(
        self, exercise_slug: str, history: list[SetRecommendation]
    ) -> SetRecommendation:
        if not history:
            return SetRecommendation(weight_kg=0.0, reps=0, rationale="no_history")
        last = history[-1]
        return SetRecommendation(
            weight_kg=last.weight_kg, reps=last.reps, rationale="repeat_last"
        )
