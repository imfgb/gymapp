"""Exercise library service.

The deterministic implementation backs onto `seeds/exercises.yaml` (loaded by
the `exercises.0002_seed_catalog` data migration) and queries the
`ExerciseAlternative` graph for substitutes.

Phase 4 may add an AI-ranked variant; the Protocol is the swap point.
"""

from __future__ import annotations

from typing import Protocol

from django.db import transaction
from django.utils.text import slugify

from .loader import apply_seed, load_seed, lookup_alternatives  # noqa: F401


@transaction.atomic
def create_custom_exercise(
    owner, *, name, equipment_slug, primary_muscle_slugs=None, weight_unit=""
):
    """Create a per-user custom Exercise (owner-scoped, so it becomes searchable
    in that user's pickers). Raises ValueError on bad input or a duplicate.

    `weight_unit` is "" (auto by equipment), "kg" or "lb" (#8); anything else is
    treated as auto."""
    from gymapp.apps.exercises.models import Equipment, Exercise, MuscleGroup, WeightUnit

    name = (name or "").strip()
    if not name:
        raise ValueError("El nombre del ejercicio es obligatorio.")
    slug = slugify(name)[:80]
    if not slug:
        raise ValueError("El nombre no produjo un identificador válido.")
    try:
        equipment = Equipment.objects.get(slug=equipment_slug)
    except Equipment.DoesNotExist as exc:
        raise ValueError("Equipo inválido.") from exc
    if Exercise.objects.filter(owner=owner, slug=slug).exists():
        raise ValueError(f"Ya tienes un ejercicio personalizado llamado '{name}'.")

    unit = weight_unit if weight_unit in WeightUnit.values else ""
    exercise = Exercise.objects.create(
        owner=owner, slug=slug, name=name, equipment=equipment, category="compound",
        weight_unit=unit,
    )
    if primary_muscle_slugs:
        exercise.primary_muscles.set(MuscleGroup.objects.filter(slug__in=primary_muscle_slugs))
    return exercise


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
    "create_custom_exercise",
    "load_seed",
    "lookup_alternatives",
]
