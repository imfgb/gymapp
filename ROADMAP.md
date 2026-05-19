# Roadmap

Phased delivery. Each phase has a single, testable exit criterion. We don't start the next phase until the current one ships.

The `.claude/feature_list.json` backlog mirrors this — features get marked `done` as they complete.

---

## Phase 0 — Scaffold ✅

**Goal**: working Django project deployable to Railway, with the build-time agent harness ready to run.

Deliverables:

- Repo skeleton (`config/`, `gymapp/apps/`, `gymapp/services/`).
- Custom `User` (email-as-username) with `users.0001_initial`.
- `core` app: `TimestampedModel`, `OwnerScopedQuerySet`, `OwnedMixin`, `OwnerScopedAdmin`.
- Empty placeholder apps: `exercises`, `routines`, `workouts`, `prs`, `metrics`, `dashboard`.
- Service-layer stubs with `Strategy` Protocols + `Deterministic*` implementations.
- Login + admin + placeholder dashboard.
- Tailwind via Play CDN (dev) and PostCSS pipeline (prod build).
- Docker + docker-compose + Railway config.
- GitHub Actions CI (ruff + pytest).
- `.claude/` harness: AGENTS.md, CHECKPOINTS.md, feature_list.json, init.sh, 5 agent definitions.
- Docs: CLAUDE.md, README.md, ARCHITECTURE.md, ROADMAP.md (this file), DATABASE.md, API_DESIGN.md, DEPLOYMENT.md, DECISIONS.md.

**Exit criterion**: `runserver` works, `/admin` login works, `pytest` passes, CI is green, and `.claude/init.sh` runs without errors.

---

## Phase 1 — Tracking MVP

**Goal**: a user can log a complete workout end-to-end and see PRs update.

Features (each becomes a row in `feature_list.json`):

1. **Exercise catalogue** (`exercises` app). `MuscleGroup`, `Equipment`, `Exercise` (nullable `owner` for custom), `ExerciseAlternative`. Data migration loads `seeds/exercises.yaml`. Admin CRUD. Curate ~80–120 exercises in `seeds/exercises.yaml`.
2. **Routines + WeeklySplit** (`routines` app). `Routine`, `RoutineDay`, `RoutineExercise`, `WeeklySplit`. Owner-scoped. Admin + minimal user-facing list/create/edit.
3. **Workout session with interactive set checklist** (`workouts` app). `WorkoutSession`, `ExerciseLog`, `SetLog` with `completed_at`. Tap-to-complete HTMX checklist; Alpine.js rest timer.
4. **PR auto-detection** (`prs` app). `PersonalRecord` model. Service updates PRs when a `SetLog` is completed. Manual override view.
5. **Body metric snapshots** (`metrics` app). `UserMetricSnapshot`. Profile edit form for height + DOB.
6. **Real dashboard**. Replace Phase 0 placeholder with cards driven by today's routine, this week's split, recent sessions, and PR highlights.

Parking-lot questions to revisit at the start of Phase 1: exact curated exercise list; icon set; rest-timer audio cue.

**Exit criterion**: from a clean DB, a superuser-created user can log in, create a routine, attach it to a weekday in their split, start "today's workout", tap-complete every set, finish the session, and see at least one new PR card on the dashboard.

---

## Phase 2 — Programming

**Goal**: the app starts recommending what to do next, not just recording what happened.

Features:

1. **Training-style behaviour**. The user's `Profile.training_style` drives default rep ranges, RPE caps, and warm-up patterns.
2. **`progression` service**. Linear progression and double progression rules. Returns `SetRecommendation` with weight × reps × rationale.
3. **`substitution` service**. Multi-factor scoring: muscle overlap, fatigue, equipment availability, user prefs.
4. **Weekly-split reconstruction**. If sessions are missed, recompute the upcoming week so the user doesn't lose their split.
5. **Warm-up generation**. Auto-prepend `is_warmup=True` `SetLog`s based on the working-set load.
6. **Monthly goals** (`metrics` app: `MonthlyGoal`). Volume / frequency / weight targets per month.

Parking-lot questions: progression rules per training style; deload trigger criteria; reconstruction algorithm (skip-forward vs cycle-shift).

**Exit criterion**: when a user starts a workout, the recommended weight × reps appears on every working set. The "swap exercise" button returns a ranked list of alternatives.

---

## Phase 3 — Nutrition

**Goal**: the app gives a daily macro target and a stub meal plan that respects food preferences.

Features:

1. **BMR + TDEE** (`nutrition` service). Mifflin-St Jeor + selectable activity factor.
2. **Bulk / cut / recomp recommendation**. Driven by body-fat snapshot trend + user goal.
3. **Macro split**. Protein-first by bodyweight, fat floor by bodyweight, carbs fill the rest.
4. **Food + vegetable preferences**. Profile fields. Stored as a tag list.
5. **Basic meal slot scaffolding**. Breakfast / lunch / dinner / snack templates that draw from the user's preferences.

Parking-lot questions: activity multiplier choices; macro split rules per phase; vegetable taxonomy depth.

**Exit criterion**: the user opens "Nutrition" and sees today's calorie + macro target, plus four meal slots respecting their food preferences.

---

## Phase 4 — AI integration

**Goal**: at least one service has a swappable `LLMStrategy` and stays cost-bounded.

Features:

1. **`LLMStrategy` infrastructure**. A common abstraction in `gymapp.services` for sending prompts to Claude, with prompt-caching wired in.
2. **AI food recommendations**. The `nutrition` service gets an `LLMStrategy` variant that generates meal slot suggestions from the user's pantry + preferences.
3. **AI progression rationale**. `progression` returns an LLM-authored "why" alongside the deterministic recommendation.
4. **AI substitution explanations**. `substitution` returns a one-sentence rationale per alternative.
5. **Cost ceiling**. Per-user daily token budget; falls back to deterministic when exhausted.

Parking-lot questions: which service goes first; prompt-cache budget per user/day; fallback policy on AI failure.

**Exit criterion**: a settings flag toggles a service between `Deterministic*` and `LLMStrategy` without code changes. With AI on, a user sees AI-authored copy in at least one place. Daily LLM cost stays under a configurable cap.

---

## Phase 5 — Polish

**Goal**: the coaching feels professional.

Features:

1. **6-week block programming**. Block templates per training style.
2. **Deload suggestions**. Auto-detect based on tonnage trend + missed-rep frequency.
3. **Volume / intensity dashboards**. Weekly / monthly rollups per muscle group.
4. **Analytics service**. PR cadence, weekly volume, intensity x exercise heatmap.

**Exit criterion**: a user opening the dashboard at the start of a new block sees a clear plan, a deload recommendation when warranted, and weekly volume trends per muscle group.

---

## Beyond Phase 5

Open-ended. Possibilities that aren't committed yet: native mobile (PWA + offline), Apple Health / Google Fit sync, video form-check, social features, public sharing of routines.
