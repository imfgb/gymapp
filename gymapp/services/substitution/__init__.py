"""Exercise substitution service.

Phase 1: delegates to `exercise_library.lookup_alternatives`.
Phase 2: multi-factor scoring (muscle overlap, fatigue, equipment, prefs).
"""

from __future__ import annotations

from typing import Protocol

from gymapp.services.exercise_library import (
    DeterministicExerciseLibrary,
    ExerciseLibraryStrategy,
)


class SubstitutionStrategy(Protocol):
    def alternatives_for(self, exercise_slug: str, available_equipment: list[str]) -> list[str]: ...


class DeterministicSubstitution:
    def __init__(self, library: ExerciseLibraryStrategy | None = None) -> None:
        self._library = library or DeterministicExerciseLibrary()

    def alternatives_for(self, exercise_slug: str, available_equipment: list[str]) -> list[str]:
        return self._library.lookup_alternatives(exercise_slug, available_equipment)
