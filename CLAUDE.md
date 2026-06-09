# CLAUDE.md — gymapp Architectural Memory

> **Read this first** at the start of every Claude Code session in this repo. Then read `.claude/AGENTS.md` and run `bash .claude/init.sh`.
>
> This file is the source of truth for *why* things are the way they are. Code answers *what* and *how*; this answers *why*. When the why changes, update this file in the same commit as the code.
>
> Companion docs: `ARCHITECTURE.md` (system design), `DEPLOYMENT.md` (Railway runbook), `HISTORY.md` (detailed implementation log + changelog), `DECISIONS.md` (ADR log), `ROADMAP.md`, `DATABASE.md`, `API_DESIGN.md`.

---

## 1. Project overview

A **personal gym workout tracking web application** built with Django 5.2, deployed on Railway, used by a small private circle of users (≤ ~20). It was scoped to evolve into an AI-powered fitness coach, but **Phase 4 (AI) is intentionally skipped** (no budget). The app is **deterministic — no AI APIs** — with a service-layer seam so an AI provider could be added later without touching call sites.

---

## 2. Tech stack

Python 3.12 · Django 5.2 (LTS) · PostgreSQL 16 (Railway prod; docker-compose / SQLite locally) · Django templates + HTMX 2 + Alpine.js 3 + Tailwind 3 · `django.contrib.auth` (invite-only via `/admin`) · `whitenoise` · `gunicorn` · `django-environ` settings split `base/dev/prod/test` · `pytest` + `pytest-django` + `factory-boy` · `ruff` + `pre-commit` · `sentry-sdk` (optional) · Dockerfile (python:3.12-slim) · GitHub Actions CI · Railway deploy.

---

## 3. Architecture decisions (locked-in)

| # | Topic | Decision |
|---|---|---|
| 1 | Audience | Personal + close circle (≤ ~20 users). No public signup, no Stripe, no marketing site. |
| 2 | AI provider | **None.** Rule/formula/deterministic; clean `Service` seam for future AI injection. |
| 3 | Primary device | Desktop-first; responsive Tailwind, mobile-first breakpoints, no PWA/offline. |
| 4 | Frontend stack | Django templates + HTMX + Alpine.js + Tailwind. |
| 5 | Auth | Invite-only via `/admin`. Django built-in auth only (no allauth). |
| 6 | Units | Metric base (cm; bodyweight kg). **Lifted weight is kg-canonical but displays kg or lb per exercise** (`Exercise.weight_unit`; cable defaults lb, machine kg, both flippable via a per-exercise toggle) — see ADR-027. |
| 7 | Deployment | Railway (web + managed Postgres, GitHub→main auto-deploy). |
| 8 | Language | Spanish UI (`es-mx`), English domain data (exercise names, muscle groups). No i18n machinery. |
| 9 | Exercise data | Curated seed (~80–120 exercises) + per-user custom exercises. |
| 10 | Async jobs | **None.** Lazy/on-demand only. No Redis, no Celery, no workers. |
| 11 | MVP scope | **Tracking-first.** Auth + profile + exercises + routines + workout logging + PRs + history. |
| 12 | Timezone | `America/Mexico_City` (single zone for all users). |
| 13 | GitHub | Private repo `github.com/imfgb/gymapp`; auto-deploy via Railway on push to `main`. |
| 14 | Sub-agent scope | Both runtime services + `.claude/` build-time harness (Leader/Implementer/Reviewer). |
| 15 | Build method | Dockerfile for prod + `manage.py runserver` for local dev. docker-compose for Postgres locally. |
| 16 | Observability | Sentry (free tier) via `SENTRY_DSN` env var; skip in dev. |
| 17 | Testing | Pytest + factory-boy. Services + non-trivial models only. No coverage gate. CI runs tests on push. |
| 18 | Set logging UX | Interactive tap-to-complete checklist → auto-rest-timer → next-set highlight. `completed_at` on `SetLog`. |

If you're about to do something that contradicts a row here, *stop and ask* before changing it. Then update this table.

---

## 4. Folder structure

```
config/            # the Django project: settings/{base,dev,prod,test}.py, urls, wsgi/asgi
gymapp/apps/       # bounded-context Django apps (see §5)
gymapp/services/   # runtime service layer (see §6)
templates/         # base.html (Tailwind shell), partials/, per-app templates
static/src/        # tailwind.css + js, compiled by PostCSS for prod
seeds/             # curated exercise library (exercises.yaml)
tests/             # pytest, mirrors gymapp/ layout
.claude/           # build-time agent harness (see §11)
docs/              # conventions, service_layer, domain_glossary
```

`config/` is *the project*; `gymapp/apps/` is *the application code*. Adding a new app = drop a folder in `gymapp/apps/` and register it in `LOCAL_APPS`.

---

## 5. Django apps (bounded contexts)

| App | Responsibility | Key models |
|---|---|---|
| `core` | Cross-cutting mixins: `TimestampedModel`, `OwnerScopedQuerySet`, `OwnedMixin`, `OwnerScopedAdmin`. `context_processors.page_hint` (per-page banners). | (no models) |
| `users` | Custom User (email-as-username), Profile (training prefs, height, DOB, sex, activity level, `onboarded_at`, `food_preferences`), first-login password change, `OnboardingMiddleware`. | `User`, `Profile` |
| `exercises` | Curated + custom exercise catalogue (primary/secondary muscle groups, equipment, category, `weight_unit` kg/lb). Self-referencing alternatives M2M. | `MuscleGroup`, `Equipment`, `Exercise` (nullable `owner` → null = global), `ExerciseAlternative` |
| `routines` | Workout templates, weekly schedule, skip-days, 6-week training blocks. | `Routine`, `RoutineDay`, `RoutineExercise`, `WeeklySplit`, `SkippedDay`, `TrainingBlock` |
| `workouts` | Actual training sessions + set-by-set logs. Drives the interactive checklist. | `WorkoutSession`, `ExerciseLog`, `SetLog` |
| `prs` | Personal records per exercise per rep-count. Auto-detected from finished `SetLog`s + manual overrides. | `PersonalRecord` |
| `metrics` | Body composition snapshots, monthly goals, fatigue/readiness inputs. | `UserMetricSnapshot`, `MonthlyGoal`, `ReadinessSnapshot`, `FatigueAdjustment` |
| `nutrition` | Calorie + macro target, food preferences, user-generated saved meals (daily-scoped), optional supplement tracker (daily reset). | `SavedMeal`, `Supplement` |
| `injuries` | Rehab/prevention: injury log + avoid-exercise warnings, mobility library + auto-swap. | `Injury`, `MobilityExercise` |
| `feedback` | In-app bug reporting: floating button → `BugReport`; superuser-only triage at `/feedback/admin/` + token-auth triage API (`/feedback/api/bugs/`). Not owner-scoped. | `BugReport` |
| `dashboard` | Read-only views: today's workout, week split, recent history, PR highlights, progreso charts. | (no models) |

---

## 6. Runtime service layer

Located in `gymapp/services/`. **No view ever calls another app's model directly across context boundaries; it calls a service.** Every service exposes a `Strategy` (Protocol) + a `Deterministic*` implementation — the **AI seam**: a future `LLMStrategy` can be selected via settings without touching call sites (`docs/service_layer.md`).

| Service | Behaviour |
|---|---|
| `exercise_library` | Loads `seeds/exercises.yaml` via data migration; `lookup_alternatives` over the curated graph; `create_custom_exercise`. |
| `progression` | `recommend_next` → linear (powerlifting) + double (bodybuilding/powerbuilding) progression; pre-fills working sets on session start. |
| `substitution` | Multi-factor scorer (muscle Jaccard, curated-graph bonus, equipment, category) → `ranked_alternatives`. |
| `coaching` | Facade re-exporting `progression` + `substitution`; `blocks` = deterministic 6-week block templates + `block_status`. |
| `nutrition` | `DeterministicNutrition` (BMR→TDEE→macros), `daily_target_for_user`, `FOOD_CATALOG`, `MEAL_TEMPLATES` (~852 recipe shells + specials), `build_meal_plan`/`generate_meal`, `FOOD_PORTIONS`/`portion_label`, supplement constants. |
| `analytics` | `weekly_volume`, `sets_by_muscle`, `deload_recommendation`, `body_comp_series`. Powers `/progreso/` + deload alerts. |
| `routine_generator` | `generate_routine` (split preset + style → days/exercises) + `assign_weekly_split` (`WEEKDAY_PATTERNS`). |
| `warmup` | `warmup_scheme()` — 40/60/80% ramp snapped to loadable weights per equipment. |
| `goals` | `monthly_goal_progress` → per-target `GoalMetric` bars (sessions / bodyweight, baseline-relative). |
| `fatigue` | `compute_muscle_fatigue` (per-muscle exponential decay) + `daily_advice`. Deterministic, no jobs. |
| `rehab` | `avoided_exercise_ids` / `warnings_for_exercise`, `mobility_for_user`, `suggested_swap`. |
| `units` | `to_kg` / `to_display` / `label` — kg↔lb conversion for per-exercise weight display (ADR-027). kg is canonical. |

---

## 7. Coding conventions

- **Imports**: stdlib → third-party → first-party (ruff/isort enforces).
- **Type hints** on every function signature.
- **Docstrings** only when the *why* isn't obvious from the name. No restating *what*.
- **No comments** that narrate the diff or reference a current task. Comments answer *why* a non-obvious thing is the way it is.
- **Naming**: `snake_case` Python, `kebab-case` URLs, `PascalCase` models, `UPPER_SNAKE` constants.
- **Spanish UI strings**, English domain identifiers (model `Exercise(name="Bench Press")`, template shows `"Banca"`).
- **No `from x import *`** outside settings layering.
- Run `npm run build:css` after any Tailwind class/config change — the deployed prod CSS must include new arbitrary values.

---

## 8. Local dev

```
source .venv/bin/activate && python manage.py runserver
```

Project lives at `~/gymapp/`. `.env` → SQLite for quick UI testing (`DATABASE_URL=sqlite:///db.sqlite3`); all models are SQLite-compatible. Full Postgres setup (docker-compose) is in `README.md` / `DEPLOYMENT.md`. Create your own superuser locally with `python manage.py createsuperuser`.

---

## 9. Business rules

- **One user, one account.** No shared accounts. No user sees another user's data, ever (except superuser via `/admin`).
- **Workouts are append-only logical history.** Editing a past `SetLog` weight is allowed; deleting a session with `SetLog`s requires UI confirmation.
- **PRs are derived, not authoritative.** Recomputed from `SetLog` history when a session finishes. Manual overrides exist for pre-app entries.
- **Routines describe intent; sessions describe reality.** A `RoutineExercise` is the plan; `ExerciseLog` + `SetLog`s are what happened. They can diverge — that's the point of tracking.
- **Weight is stored in kg; heights in cm.** **Lifted** weight displays in the exercise's unit (kg or lb — `Exercise.weight_unit`, blank = auto by equipment); conversion lives only at the input/display boundary via `gymapp/services/units.py` + the `in_unit` template filter (ADR-027). Bodyweight stays kg. Negative numeric input is rejected.
- **Spanish UI surface; English data** (exercise names, muscle/equipment slugs).

---

## 10. Security rules

- `SECRET_KEY` from env. Never committed. `.env.example` documents required keys with empty values. **Never commit credentials of any kind to this repo.**
- `DEBUG = False` in prod (forced by `prod.py`). `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` from env.
- Prod enables `SECURE_PROXY_SSL_HEADER`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_*`, `X_FRAME_OPTIONS=DENY`.
- **Owner-scoping is the privacy rule.** Every user-owned model uses `OwnedMixin` (`core.models`). Every view reading user data calls `Model.objects.for_user(request.user)`. Admin uses `OwnerScopedAdmin`. A missing `.for_user` is a security bug, full stop.
- **`for_user` does NOT bypass for superusers.** A superuser is just another user in the regular app; they see only their own rows. Superuser-sees-all lives in `/admin` only, via `OwnerScopedAdmin.get_queryset`. A past bypass leaked every user's data — see `tests/apps/core/test_owner_scoping.py`.
- **Cross-owner FK leaks.** When following a FK from one owner-scoped row to another (e.g. `WeeklySplit.routine_day → RoutineDay → Routine.owner`), re-check `routine.owner_id == request.user.id` in the render path so legacy/stale rows can't leak.
- CSRF middleware always on. HTMX POSTs send the token via the meta-tag wiring in `base.html`.
- No `raw()`, no `extra()`, no string SQL. Templates auto-escape; `|safe` / `mark_safe` / `format_html` on untrusted input is forbidden without an explicit ADR.
- Sentry: `send_default_pii=False`.

---

## 11. Build-time sub-agent harness (`.claude/`)

Three roles (Leader / Implementer / Reviewer) + specialized Migration Writer & Test Writer, one feature `in_progress` at a time, disk-based work logs in `progress/`. Operating rules in `.claude/AGENTS.md`; success criteria in `.claude/CHECKPOINTS.md`; backlog in `.claude/feature_list.json`; bootstrap `bash .claude/init.sh`.

**Project skills** (`.claude/skills/<name>/SKILL.md`, invoke with a slash):
- `/test` — run the pytest suite, target a file/app, repair failures without weakening tests, or delegate new tests to the `test-writer` subagent.
- `/debug` — reproduce → isolate → minimal fix → regression test → browser-verify (WebKit 390×844). Never claim "fixed" without test-green / screenshot / repro.
- `/change-approval-orchestrator` — read the **prod** feedback inbox, triage user-reported bugs/ideas, act only with per-item approval.
- `/auto-bug-fixer` — execute ONE approved feedback item (fix via `/debug` or implement per the working agreement; test; commit+push; never deploy). Needs `FEEDBACK_API_TOKEN` + `PROD_BASE_URL` in `.env`.

---

## 12. Deployment

**Railway.** See `DEPLOYMENT.md` for the runbook (start command, healthcheck, deploy triggering, env vars, adding users, verification checklist).

---

## 13. Roadmap

| Phase | Scope | Status |
|---|---|---|
| **0 — Scaffold** | Repo, settings, Docker, Postgres, Railway, base templates, custom User, owner-scoped manager, `.claude/` harness, docs. | Complete |
| **1 — Tracking MVP** | Exercises; Routines + WeeklySplit; WorkoutSession with interactive checklist + rest timer; PR auto-detection; profile + body metrics; dashboard. | Complete |
| **2 — Programming** | Training-style behaviour; progression (linear + double); substitution scoring; weekly-split reconstruction; warm-up generation; monthly goals. | Complete |
| **3 — Nutrition** | BMR, TDEE, bulk/cut/recomp, macro split, food preferences, meal slots. | Complete |
| **4 — AI integration** | `LLMStrategy` (Claude API) behind existing service interfaces. | **Skipped** (no budget) |
| **5 — Polish** | 6-week blocks, deload suggestions, volume/intensity dashboards, analytics. | Complete |

Detail → `ROADMAP.md` (plan) and `HISTORY.md` (what was built).

---

## 14. Current status

Roadmap phases:
- Phase 1: Complete
- Phase 2: Complete
- Phase 3: Complete
- Phase 4: Skipped (no budget)
- Phase 5: Complete

Post-roadmap (all deterministic / free): fatigue/readiness, rehab/prevention (injuries + mobility), nutrition meals/portions/supplements, onboarding wizard, body-comp charts, in-app bug reporting (`feedback`), per-page hint banners.

Test status: **377 pytest passing · `ruff check .` clean** (2026-05-28).

Detailed implementation history → `HISTORY.md`.

### Candidate next features (deterministic / free, none committed)

1. **Per-exercise strength charts** — weight×reps-over-time SVG on each PR/exercise page; reuse `analytics.body_comp_series` + the `/progreso/` SVG pattern. Data already in `SetLog`. (Highest user value.)
2. **`manage.py seed_demo`** — populate a new user with routine + WeeklySplit + metrics + session history so invited friends don't see empty screens.
3. **Create users outside `/admin`** — a superuser-only page to add friends (email+password).
4. **Export my data (CSV)** — download workout/PR history.

**Working agreement:** build ONE feature at a time with tests + `npm run build:css` (if Tailwind changed) + browser-verify at 390px + commit + push + memory update. The user deploys to Railway manually. Don't add paid APIs/hosting (`feedback-no-spend`). Verify before claiming fixed (`feedback-verify-before-deploy`).

---

## 15. Important constraints

- **No AI APIs.** All "coaching" features are deterministic. Future AI is a strategy swap, not a rewrite. Don't sneak `anthropic` / `openai` calls into the code.
- **No background jobs.** No Celery, no Redis, no workers. Recomputes happen lazily when a user opens the screen. Prove a request can't be done on-demand before reaching for a job.
- **No allauth, no social login.** Django built-in auth only. Account creation via `/admin` only.
- **No public signup.** Adding one needs an explicit decision in `DECISIONS.md`.
- **No multi-tenant isolation beyond owner-scoping.** No per-user schemas, no row-level security. The `for_user` pattern is the entire isolation story.
- **Single timezone** (`America/Mexico_City`). All users see the same calendar day.

---

## 16. Reusable patterns

- **Owner-scoped model**: subclass `OwnedMixin` (gives `owner` FK + `OwnerScopedQuerySet.as_manager()`).
- **Owner-scoped admin**: subclass `OwnerScopedAdmin` from `core.admin`.
- **Timestamps**: subclass `TimestampedModel` from `core.models`.
- **Cross-app business logic**: a service in `gymapp/services/<area>/` with a `Strategy` Protocol + `Deterministic*` impl. Import the facade.
- **HTMX partials**: render a fragment from `templates/partials/`; include `csrf_token` in forms (meta-tag wiring in `base.html` handles `hx-post`).
- **Tests**: `factory-boy` factories in `tests/factories.py`; tests mirror source layout.
- **Migrations**: data migrations are `RunPython` both directions, or `reversible = False` with a comment.

---

## 17. When updating this file

- Edit `CLAUDE.md` in the same commit that introduces an architectural or business change. Drift between this file and the code is a bug.
- Per-feature changelog → `HISTORY.md`. One-line decisions → `DECISIONS.md` (ADR). Deeper architecture → `ARCHITECTURE.md`. Deployment ops → `DEPLOYMENT.md`.
