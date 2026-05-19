"""Routines & WeeklySplit — Phase 1.

Planned entities:

    Routine          (owner, name, training_style snapshot, notes)
    RoutineDay       (routine FK, label e.g. "Push A")
    RoutineExercise  (routine_day FK, exercise FK, ordering, target_sets,
                      target_reps_low, target_reps_high, target_weight_kg,
                      rest_seconds, notes)
    WeeklySplit      (owner, weekday 0-6, routine_day FK)

Intentionally empty in Phase 0.
"""
