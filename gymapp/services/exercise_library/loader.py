"""Idempotent loader for `seeds/exercises.yaml`.

Used by the `exercises.0002_seed_catalog` data migration and re-runnable any
time the YAML expands (subsequent runs upsert, never duplicate).

Keep this pure-Python: no Django imports at module load time, so the migration
can import it without circular issues.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_PATH = REPO_ROOT / "seeds" / "exercises.yaml"


def load_seed(yaml_path: Path = SEED_PATH) -> dict:
    """Parse the YAML and return a dict with keys `muscle_groups`, `equipment`,
    `exercises`. Pure function — no DB side effects."""
    with yaml_path.open() as f:
        data = yaml.safe_load(f) or {}
    data.setdefault("muscle_groups", [])
    data.setdefault("equipment", [])
    data.setdefault("exercises", [])
    return data


def apply_seed(apps, *, yaml_path: Path = SEED_PATH, mirror_alternatives: bool = True) -> None:
    """Upsert the seed catalogue into the database.

    `apps` is the historical app registry passed by `RunPython`. Using
    `apps.get_model` keeps this safe to run against any future migration state.

    Idempotent: re-running modifies updated rows, never duplicates. New rows are
    inserted; removed rows (no longer in YAML) are left in place so user
    references to them don't break — explicit deletion is a manual operation.
    """
    Exercise = apps.get_model("exercises", "Exercise")
    ExerciseAlternative = apps.get_model("exercises", "ExerciseAlternative")
    MuscleGroup = apps.get_model("exercises", "MuscleGroup")
    Equipment = apps.get_model("exercises", "Equipment")

    data = load_seed(yaml_path)

    # Upsert lookups
    for mg in data["muscle_groups"]:
        MuscleGroup.objects.update_or_create(
            slug=mg["slug"],
            defaults={"name": mg["name"], "region": mg["region"]},
        )
    for eq in data["equipment"]:
        Equipment.objects.update_or_create(
            slug=eq["slug"],
            defaults={"name": eq["name"]},
        )

    muscle_by_slug = {m.slug: m for m in MuscleGroup.objects.all()}
    equipment_by_slug = {e.slug: e for e in Equipment.objects.all()}

    # First pass: upsert exercises (global, owner=NULL)
    for ex in data["exercises"]:
        eq = equipment_by_slug[ex["equipment"]]
        exercise, _ = Exercise.objects.update_or_create(
            owner=None,
            slug=ex["slug"],
            defaults={
                "name": ex["name"],
                "equipment": eq,
                "category": ex.get("category", "compound"),
                "unilateral": ex.get("unilateral", False),
                "is_active": True,
            },
        )
        primary = [muscle_by_slug[s] for s in ex.get("primary_muscles", [])]
        secondary = [muscle_by_slug[s] for s in ex.get("secondary_muscles", [])]
        exercise.primary_muscles.set(primary)
        exercise.secondary_muscles.set(secondary)

    exercise_by_slug = {e.slug: e for e in Exercise.objects.filter(owner__isnull=True)}

    # Second pass: alternatives (need both ends to exist already)
    for ex in data["exercises"]:
        src = exercise_by_slug[ex["slug"]]
        for alt in ex.get("alternatives", []) or []:
            try:
                dst = exercise_by_slug[alt["slug"]]
            except KeyError:
                # Forward reference to an exercise that doesn't exist in the
                # YAML; skip silently so a typo doesn't break the migration.
                continue
            reason = alt.get("reason", "")
            mirror = alt.get("mirror", mirror_alternatives)

            ExerciseAlternative.objects.update_or_create(
                from_exercise=src,
                to_exercise=dst,
                defaults={"reason": reason},
            )
            if mirror:
                ExerciseAlternative.objects.update_or_create(
                    from_exercise=dst,
                    to_exercise=src,
                    defaults={"reason": reason or f"Reciprocal of {src.slug} → {dst.slug}"},
                )


def lookup_alternatives(
    exercise_slug: str, available_equipment: list[str] | None = None
) -> list[str]:
    """Return slugs of substitute exercises for `exercise_slug`, optionally
    filtered to those whose equipment is in `available_equipment`.

    Lazy Django import so this module stays importable during migration setup.
    """
    from gymapp.apps.exercises.models import Exercise

    try:
        source = Exercise.objects.get(owner__isnull=True, slug=exercise_slug)
    except Exercise.DoesNotExist:
        return []

    qs = ExerciseAlternative_for(source).select_related("to_exercise__equipment").order_by("id")
    if available_equipment:
        qs = qs.filter(to_exercise__equipment__slug__in=available_equipment)
    return [link.to_exercise.slug for link in qs]


def ExerciseAlternative_for(source):
    """Helper that lazy-imports the through model — keeps top-level imports
    safe to run during migrations."""
    from gymapp.apps.exercises.models import ExerciseAlternative

    return ExerciseAlternative.objects.filter(from_exercise=source)
