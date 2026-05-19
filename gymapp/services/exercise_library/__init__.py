"""Exercise library service.

In Phase 1 this loads `seeds/exercises.yaml` via a data migration and exposes
`lookup_alternatives(exercise, available_equipment)` — a pure dict query
against the curated graph. Phase 4 may add an AI-ranked variant.
"""
from __future__ import annotations

from typing import Protocol


class ExerciseLibraryStrategy(Protocol):
    def lookup_alternatives(self, exercise_slug: str, available_equipment: list[str]) -> list[str]:
        """Return slugs of substitute exercises, ranked best-first."""
        ...


class DeterministicExerciseLibrary:
    """Phase 0 stub. Phase 1 implements seed-driven lookup."""

    def lookup_alternatives(self, exercise_slug: str, available_equipment: list[str]) -> list[str]:
        return []
