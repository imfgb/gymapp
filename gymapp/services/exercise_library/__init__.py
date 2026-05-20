"""Exercise library service.

The deterministic implementation backs onto `seeds/exercises.yaml` (loaded by
the `exercises.0002_seed_catalog` data migration) and queries the
`ExerciseAlternative` graph for substitutes.

Phase 4 may add an AI-ranked variant; the Protocol is the swap point.
"""
from __future__ import annotations

from typing import Protocol

from .loader import apply_seed, load_seed, lookup_alternatives  # noqa: F401


class ExerciseLibraryStrategy(Protocol):
    def lookup_alternatives(self, exercise_slug: str, available_equipment: list[str]) -> list[str]:
        """Return slugs of substitute exercises, ranked best-first."""
        ...


class DeterministicExerciseLibrary:
    def lookup_alternatives(self, exercise_slug: str, available_equipment: list[str]) -> list[str]:
        return lookup_alternatives(exercise_slug, available_equipment)


__all__ = [
    "ExerciseLibraryStrategy",
    "DeterministicExerciseLibrary",
    "apply_seed",
    "load_seed",
    "lookup_alternatives",
]
