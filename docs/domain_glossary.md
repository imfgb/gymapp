# Domain Glossary

Shared vocabulary. When the team and the code use the same word for the same thing, bugs go down.

## Catalogue

- **Exercise** — a movement, e.g. "Bench Press". Can be global (visible to everyone) or owned (custom, visible only to its `owner`).
- **Muscle Group** — a muscle tagged on an exercise. Slugs are kebab-case English: `chest`, `lats`, `delts-front`, `quads`.
- **Equipment** — what the exercise requires: `barbell`, `dumbbell`, `cable`, `machine`, `smith`, `bodyweight`.
- **Compound vs Isolation** — a category on `Exercise`. Compound moves multiple joints (squat, deadlift); isolation moves one (curl, leg extension).
- **Alternative** — another exercise that targets the same primary muscle with different equipment, used when the preferred station is busy. Tracked via the `ExerciseAlternative` through-model with a `reason` field.

## Planning

- **Routine** — a user-owned workout template. A user has many routines.
- **Routine Day** — one workout within a routine, e.g. "Push A". A routine has many days.
- **Routine Exercise** — one prescribed exercise within a routine day, with target sets / reps / weight / rest.
- **Weekly Split** — the mapping from weekday (Mon..Sun) to `RoutineDay`. A user has one split.
- **Reconstruction** — recomputing the upcoming week's `WeeklySplit` when sessions were missed (Phase 2).

## Execution

- **Workout Session** — an actual training day. Statuses: `in_progress`, `finished`, `abandoned`.
- **Exercise Log** — one exercise within a session.
- **Set Log** — one set within an exercise log: weight × reps (+ optional RPE). `completed_at` powers the tap-to-complete checklist.
- **Warm-up set** — a `SetLog` with `is_warmup=True`. Doesn't count toward PRs or volume rollups.

## Performance

- **PR (Personal Record)** — best (weight × reps) for an exercise at a given rep-count. One row per `(owner, exercise, reps)`. Auto-detected from finished `SetLog`s; manually overridable.
- **RPE (Rate of Perceived Exertion)** — subjective intensity, 5.0–10.0. Used in Phase 2 progression.
- **Tonnage** — total kg lifted in a window (sum of `weight_kg × reps` across working sets).
- **Volume** — usually means tonnage; sometimes "number of working sets per muscle group per week" (we clarify in context).

## Body

- **User Metric Snapshot** — point-in-time body data: weight, body-fat %. Height and DOB live on `Profile` because they don't really change.
- **TDEE (Total Daily Energy Expenditure)** — BMR × activity factor (Phase 3).
- **BMR (Basal Metabolic Rate)** — energy at rest. We use Mifflin-St Jeor.
- **Bulk / Cut / Recomp** — caloric direction. Bulk = surplus, Cut = deficit, Recomp = maintenance ± small. Recommended by Phase 3 service from body-fat trend + goal.

## Programming

- **Training Style** — `bodybuilding` / `powerlifting` / `powerbuilding`. Drives default rep ranges and progression rules.
- **Training Goal** — `hypertrophy` / `strength` / `recomposition` / `cut` / `bulk` / `maintain`.
- **Linear Progression** — add weight every successful session (typical for beginners).
- **Double Progression** — add reps until top of range, then add weight and reset reps.
- **Deload** — a planned light week to recover from accumulated fatigue.
- **6-week Block** — a programmed training block (Phase 5).

## Architecture

- **Service** — a Python module in `gymapp/services/` that owns cross-context logic. Exposes a `Strategy` Protocol and a `Deterministic*` implementation.
- **Strategy / DeterministicStrategy / LLMStrategy** — the interface and its implementations. Selection driven by settings (`PROGRESSION_STRATEGY`, etc.).
- **Facade** — `gymapp/services/coaching/__init__.py`. Views import from here, not from individual services.
- **OwnerScoping** — the privacy mechanism: `Model.objects.for_user(user)`. A missing call is a security bug.
- **Bounded Context** — a Django app under `gymapp/apps/`. Crosses are mediated by services, not by direct model imports.

## Build-time agents

- **Leader / Implementer / Reviewer** — the three core roles in the `.claude/` harness.
- **Migration Writer / Test Writer** — specialized Implementers.
- **`progress/`** — disk-based per-feature work logs (gitignored).
- **`feature_list.json`** — single source of truth for backlog status. Exactly one feature `in_progress` at a time.
