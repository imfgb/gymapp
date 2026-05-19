"""Workout sessions — Phase 1.

Planned entities:

    WorkoutSession  (owner, started_at, finished_at, status, source_routine_day FK)
    ExerciseLog     (session FK, exercise FK, ordering)
    SetLog          (exercise_log FK, ordering, weight_kg, reps, rpe optional,
                     is_warmup, completed_at)

`completed_at` powers the tap-to-complete interactive checklist (plan §2 #18).

Intentionally empty in Phase 0.
"""
