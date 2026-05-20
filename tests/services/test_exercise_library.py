"""Tests for the exercise_library service.

Cover: YAML loader parses correctly, idempotent upsert, alternative mirroring,
lookup_alternatives equipment filter.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from gymapp.apps.exercises.models import Equipment, Exercise, ExerciseAlternative, MuscleGroup
from gymapp.services.exercise_library import (
    DeterministicExerciseLibrary,
    apply_seed,
    load_seed,
)


SAMPLE_YAML = """
muscle_groups:
  - {slug: chest, name: Chest, region: chest}
  - {slug: triceps, name: Triceps, region: arms}
equipment:
  - {slug: barbell, name: Barbell}
  - {slug: dumbbell, name: Dumbbell}
exercises:
  - slug: bench-press
    name: Bench Press
    equipment: barbell
    primary_muscles: [chest]
    secondary_muscles: [triceps]
    category: compound
    unilateral: false
    alternatives:
      - {slug: dumbbell-bench-press, reason: Free-weight alternative.}
  - slug: dumbbell-bench-press
    name: Dumbbell Bench Press
    equipment: dumbbell
    primary_muscles: [chest]
    secondary_muscles: [triceps]
    category: compound
    unilateral: false
    alternatives: []
"""


@pytest.fixture
def yaml_file(tmp_path: Path) -> Path:
    p = tmp_path / "exercises.yaml"
    p.write_text(SAMPLE_YAML)
    return p


def test_load_seed_parses_yaml(yaml_file):
    data = load_seed(yaml_file)
    assert {m["slug"] for m in data["muscle_groups"]} == {"chest", "triceps"}
    assert {e["slug"] for e in data["equipment"]} == {"barbell", "dumbbell"}
    assert len(data["exercises"]) == 2


@pytest.mark.django_db
def test_apply_seed_inserts_rows(yaml_file):
    from django.apps import apps as django_apps

    apply_seed(django_apps, yaml_path=yaml_file)

    assert MuscleGroup.objects.count() == 2
    assert Equipment.objects.count() == 2
    assert Exercise.objects.filter(owner__isnull=True).count() == 2


@pytest.mark.django_db
def test_apply_seed_is_idempotent(yaml_file):
    from django.apps import apps as django_apps

    apply_seed(django_apps, yaml_path=yaml_file)
    apply_seed(django_apps, yaml_path=yaml_file)

    assert MuscleGroup.objects.count() == 2
    assert Equipment.objects.count() == 2
    assert Exercise.objects.filter(owner__isnull=True).count() == 2
    # Alternative count: one declared pair × 2 (mirrored) = 2 rows.
    assert ExerciseAlternative.objects.count() == 2


@pytest.mark.django_db
def test_apply_seed_mirrors_alternatives(yaml_file):
    from django.apps import apps as django_apps

    apply_seed(django_apps, yaml_path=yaml_file)

    bench = Exercise.objects.get(slug="bench-press", owner__isnull=True)
    dumb = Exercise.objects.get(slug="dumbbell-bench-press", owner__isnull=True)

    forward = ExerciseAlternative.objects.filter(from_exercise=bench, to_exercise=dumb)
    backward = ExerciseAlternative.objects.filter(from_exercise=dumb, to_exercise=bench)
    assert forward.exists()
    assert backward.exists()


@pytest.mark.django_db
def test_apply_seed_handles_dangling_alternative_reference(tmp_path: Path):
    # Reference an exercise that doesn't exist in the YAML — must not crash.
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text(
        yaml.safe_dump(
            {
                "muscle_groups": [{"slug": "chest", "name": "Chest", "region": "chest"}],
                "equipment": [{"slug": "barbell", "name": "Barbell"}],
                "exercises": [
                    {
                        "slug": "bench-press",
                        "name": "Bench Press",
                        "equipment": "barbell",
                        "primary_muscles": ["chest"],
                        "alternatives": [
                            {"slug": "does-not-exist", "reason": "Typo"}
                        ],
                    }
                ],
            }
        )
    )
    from django.apps import apps as django_apps

    apply_seed(django_apps, yaml_path=bad_yaml)
    # Survived; no alternative row created.
    assert ExerciseAlternative.objects.count() == 0


@pytest.mark.django_db
def test_lookup_alternatives_returns_mirrored_pair(yaml_file):
    from django.apps import apps as django_apps

    apply_seed(django_apps, yaml_path=yaml_file)

    library = DeterministicExerciseLibrary()
    assert library.lookup_alternatives("bench-press", []) == ["dumbbell-bench-press"]
    assert library.lookup_alternatives("dumbbell-bench-press", []) == ["bench-press"]


@pytest.mark.django_db
def test_lookup_alternatives_filters_by_equipment(yaml_file):
    from django.apps import apps as django_apps

    apply_seed(django_apps, yaml_path=yaml_file)

    library = DeterministicExerciseLibrary()
    # Bench press's alternative is dumbbell-bench-press (equipment=dumbbell).
    assert library.lookup_alternatives("bench-press", ["dumbbell"]) == ["dumbbell-bench-press"]
    # Filtering to barbell-only leaves no alternatives.
    assert library.lookup_alternatives("bench-press", ["barbell"]) == []


@pytest.mark.django_db
def test_lookup_alternatives_unknown_exercise_returns_empty():
    library = DeterministicExerciseLibrary()
    assert library.lookup_alternatives("does-not-exist", []) == []
