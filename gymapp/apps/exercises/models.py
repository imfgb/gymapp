"""Exercises catalogue — models to land in Phase 1.

Planned entities (see plan §5 and DATABASE.md):

    MuscleGroup  (chest, back-lats, back-traps, quads, hamstrings, ...)
    Equipment    (barbell, dumbbell, cable, machine, bodyweight, ...)
    Exercise     (name, slug, equipment FK, owner nullable for custom)
        primary_muscles  M2M -> MuscleGroup
        secondary_muscles M2M -> MuscleGroup
    ExerciseAlternative (through-table for self-referencing M2M, with `reason`)

Intentionally empty in Phase 0 — only the app shell exists.
"""
