"""Personal records — Phase 1.

Planned entity:

    PersonalRecord  (owner, exercise FK, weight_kg, reps, achieved_at, source)
        source: 'auto' (detected from finished SetLog) or 'manual'

A user's "best at N reps" surfaces from PersonalRecord queries; we don't
duplicate it. Intentionally empty in Phase 0.
"""
