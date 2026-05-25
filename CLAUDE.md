# CLAUDE.md — gymapp Architectural Memory

> **Read this first** at the start of every Claude Code session in this repo. Then read `.claude/AGENTS.md` and run `bash .claude/init.sh`.
>
> This file is the source of truth for *why* things are the way they are. Code answers *what* and *how*; this answers *why*. When the why changes, update this file in the same commit as the code.

---

## 1. Project overview

A **personal gym workout tracking web application** built with Django 5.2, deployed on Railway, used by a small private circle of users (≤ ~20). It will evolve, in phases, into an AI-powered fitness coach (workout programming, progression, nutrition). The MVP is tracking-only and deterministic — *no AI APIs* — with a service-layer seam so an AI provider can be added later without touching call sites.

The original brief lives in conversation history. The discovery decisions that shaped it live in §3 below, and as an ADR log in `DECISIONS.md`.

---

## 2. Tech stack (at a glance)

| Layer | Choice |
|---|---|
| Language | Python 3.12 |
| Framework | Django 5.2 (LTS) |
| Database | PostgreSQL 16 (Railway managed in prod; docker-compose locally) |
| Frontend | Django templates + HTMX 2 + Alpine.js 3 + Tailwind 3 (Play CDN dev, PostCSS prod) |
| Auth | `django.contrib.auth` only — invite-only via `/admin` |
| Static | `whitenoise` (no nginx required on Railway) |
| WSGI | `gunicorn` |
| Settings | `django-environ`, split into `base.py` / `dev.py` / `prod.py` / `test.py` |
| Tests | `pytest`, `pytest-django`, `factory-boy` |
| Lint/Format | `ruff` + `pre-commit` |
| Errors | `sentry-sdk[django]` (free tier, optional) |
| Container | Dockerfile (python:3.12-slim) + docker-compose for local Postgres |
| CI | GitHub Actions: lint + tests on push/PR |
| Deploy | Railway: web service (Dockerfile) + managed Postgres, auto-deploy on push to `main` |

---

## 3. Architecture decisions (locked-in)

| # | Topic | Decision |
|---|---|---|
| 1 | Audience | Personal + close circle (≤ ~20 users). No public signup, no Stripe, no marketing site. |
| 2 | AI provider (MVP) | **None.** Rule/formula/deterministic; clean `Service` seam for future AI injection. |
| 3 | Primary device | Desktop-first; responsive Tailwind, mobile-first breakpoints, no PWA/offline. |
| 4 | Frontend stack | Django templates + HTMX + Alpine.js + Tailwind. |
| 5 | Auth | Invite-only via `/admin`. Django built-in auth only (no allauth). |
| 6 | Units | Metric only (kg, cm). |
| 7 | Deployment | Railway (web + managed Postgres, GitHub→main auto-deploy). |
| 8 | Language | Spanish UI (`es-mx`), English domain data (exercise names, muscle groups). No i18n machinery. |
| 9 | Exercise data | Curated seed (~80–120 exercises) + per-user custom exercises. |
| 10 | Async jobs | **None for MVP.** Lazy/on-demand only. No Redis, no Celery, no workers. |
| 11 | MVP scope | **Tracking-only.** Auth + profile + exercises + routines + workout logging + PRs + history. Programming → Phase 2, Nutrition → Phase 3, AI → Phase 4. |
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
gymapp/                              # repo root
├── CLAUDE.md                        # this file
├── ARCHITECTURE.md                  # system design overview (deeper than CLAUDE.md)
├── ROADMAP.md                       # phased delivery plan
├── DATABASE.md                      # per-app schema docs
├── API_DESIGN.md                    # HTMX endpoint catalogue
├── DEPLOYMENT.md                    # Railway runbook + verification checklist
├── DECISIONS.md                     # ADR log
├── README.md                        # quickstart
│
├── .env.example                     # safe template; .env is gitignored
├── pyproject.toml                   # ruff + pytest + project metadata
├── requirements{,-dev}.txt
├── Dockerfile / docker-compose.yml / Procfile / railway.json
├── package.json + tailwind.config.js + postcss.config.js
├── .github/workflows/ci.yml
│
├── .claude/                         # build-time agent harness (see §11)
├── progress/                        # per-feature work logs (gitignored)
├── docs/                            # conventions, service layer, glossary
│
├── config/                          # Django project package
│   ├── settings/{base,dev,prod,test}.py
│   ├── urls.py / wsgi.py / asgi.py
│
├── gymapp/
│   ├── apps/                        # bounded-context Django apps (see §5)
│   │   ├── core/                    # mixins, OwnerScopedQuerySet
│   │   ├── users/                   # custom User + Profile
│   │   ├── exercises/               # MuscleGroup, Equipment, Exercise, alternatives
│   │   ├── routines/                # Routine, RoutineDay, RoutineExercise, WeeklySplit
│   │   ├── workouts/                # WorkoutSession, ExerciseLog, SetLog
│   │   ├── prs/                     # PersonalRecord
│   │   ├── metrics/                 # UserMetricSnapshot
│   │   └── dashboard/               # landing / weekly view / history
│   │
│   └── services/                    # runtime service layer (see §6)
│       ├── exercise_library/  progression/  substitution/
│       ├── coaching/  nutrition/  analytics/
│
├── templates/                       # base.html (Tailwind shell), partials/, auth/, dashboard/…
├── static/src/{tailwind.css,js/}    # compiled by PostCSS in prod
├── seeds/exercises.yaml             # curated exercise library
└── tests/                           # pytest, mirrors gymapp/ layout
```

`config/` is *the project*; `gymapp/apps/` is *the application code*. Renaming the project is cheap; adding new apps is just dropping a folder in `gymapp/apps/` and registering it in `LOCAL_APPS`.

---

## 5. Django apps (bounded contexts)

| App | Responsibility | Key models |
|---|---|---|
| `core` | Cross-cutting mixins: `TimestampedModel`, `OwnerScopedQuerySet`, `OwnedMixin`, `OwnerScopedAdmin`. | (no models) |
| `users` | Custom User (email-as-username), Profile (training prefs, height, DOB, sex, activity level), one-shot password-change-on-first-login. | `User`, `Profile` |
| `exercises` | Curated + custom exercise catalogue. Each tags primary/secondary muscle groups, equipment, category. Self-referencing alternatives M2M. | `MuscleGroup`, `Equipment`, `Exercise` (nullable `owner` → null = global), `ExerciseAlternative` |
| `routines` | User-defined workout templates, weekly schedule, skip-days, and 6-week training blocks. | `Routine`, `RoutineDay`, `RoutineExercise`, `WeeklySplit`, `SkippedDay`, `TrainingBlock` |
| `workouts` | Actual training sessions and set-by-set logs. Drives the interactive checklist. | `WorkoutSession`, `ExerciseLog`, `SetLog` |
| `prs` | Personal records per exercise per rep-count. Auto-detected from finished `SetLog`s + manual overrides. | `PersonalRecord` |
| `metrics` | Body composition snapshots + per-month goals. | `UserMetricSnapshot`, `MonthlyGoal` |
| `nutrition` | Nutrition page: calorie + macro target, food preferences, user-generated saved meals (generate from prefs / mark eaten / delete; daily-scoped), and an optional supplement tracker (common + custom, mark-taken with timestamp, daily reset). | `SavedMeal`, `Supplement` |
| `dashboard` | Read-only views: today's workout, this week's split, recent history, PR highlights. | (no models) |

---

## 6. Runtime service layer

Located in `gymapp/services/`. **No view ever calls another app's model directly across context boundaries; it calls a service.**

| Service | MVP behaviour | Later |
|---|---|---|
| `exercise_library` | Loads `seeds/exercises.yaml` via data migration. `lookup_alternatives(slug, equipment)` over the curated graph. | AI-ranked (Phase 4). |
| `progression` | `recommend_next` returns the last completed weight×reps. | Linear/double progression → RPE-driven → AI-tuned. |
| `substitution` | Delegates to `exercise_library`. | Multi-factor scoring (Phase 2). |
| `coaching` | Facade re-exporting `progression` + `substitution`; `blocks` submodule = deterministic 6-week block templates + `block_status`. | AI-orchestrated programming (Phase 4, skipped). |
| `nutrition` | `DeterministicNutrition` (BMR→TDEE→macros), `daily_target_for_user`, `FOOD_CATALOG`, `build_meal_plan` (deterministic plan) + `generate_meal` (varied, for saved meals). | AI meal rec (Phase 4, skipped). |
| `analytics` | `weekly_volume` + `sets_by_muscle` + `deload_recommendation`. Powers `/progreso/` + deload alerts. | PR cadence, intensity heatmaps (Phase 5 cont.). |

**The AI seam:** every service exposes a `Strategy` (Protocol) and a `Deterministic*` implementation. A future `LLMStrategy` (Claude API) can be selected via settings without touching call sites. Document the contract in `docs/service_layer.md`.

---

## 7. Coding conventions

- **Imports**: stdlib → third-party → first-party (ruff/isort enforces).
- **Type hints** on every function signature.
- **Docstrings** only when the *why* isn't obvious from the name. No restating *what* the code does.
- **No comments** that narrate the diff or reference a current task. Comments answer *why* a non-obvious thing is the way it is.
- **Naming**: `snake_case` Python, `kebab-case` URLs, `PascalCase` models, `UPPER_SNAKE` constants.
- **Spanish UI strings**, English domain identifiers. e.g., the model is `Exercise(name="Bench Press")` but the template says `"Banca"` somewhere.
- **No `from x import *`** outside settings layering.

---

## 8. Environment setup

### Full setup (matches prod: Postgres via Docker)

1. `python3.12 -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements-dev.txt`
3. `cp .env.example .env`; generate a secret key: `python -c "import secrets; print(secrets.token_urlsafe(50))"`; paste into `DJANGO_SECRET_KEY`.
4. `docker compose up -d` (Postgres on `localhost:5432`).
5. `python manage.py migrate`.
6. `python manage.py createsuperuser`.
7. `python manage.py runserver`. Visit `http://127.0.0.1:8000/` (redirects to `/auth/login/`) and `http://127.0.0.1:8000/admin/`.
8. `pre-commit install` once.

### Fast local shortcut (no Docker — SQLite)

For quick UI testing when Docker isn't running, override `DATABASE_URL` in `.env`:
```
DATABASE_URL=sqlite:///db.sqlite3
```
Then `migrate` + `createsuperuser` + `runserver` work unchanged. All models are SQLite-compatible (no Postgres-only features used). Tests still run against the test DB defined in `pyproject.toml`.

### Seeding demo data (after `migrate`)

Quickest way to get something to click around with — `python manage.py shell -c "..."` or save the seed snippet that was used in the first runserver session (see git log around the Phase 1 completion; the snippet creates a `PPL Demo` routine + a full `WeeklySplit` + a `UserMetricSnapshot`). A proper `manage.py seed_demo` command is a Phase 2 nicety.

---

## 9. Business rules

- **One user, one account.** No shared accounts. Privacy expectation: no user sees another user's data, ever (except superuser via `/admin`).
- **Workouts are append-only logical history.** Editing a past `SetLog`'s weight is allowed, but deleting a session that has `SetLog`s requires confirmation in UI (Phase 1 detail).
- **PRs are derived, not authoritative.** They're recomputed from `SetLog` history when a session is finished. Manual overrides exist for entries that pre-date the app.
- **Routines describe intent; sessions describe reality.** A `RoutineExercise` is the plan; an `ExerciseLog` + `SetLog`s are what actually happened. They can diverge — that's the whole point of tracking.
- **Metric units only.** All weights `kg`, heights `cm`. No conversion code. If a user pastes a value in lb, the form rejects it.
- **Spanish-language UI is the surface; data stays in English** (exercise names, muscle group slugs, equipment slugs).

---

## 10. Security rules

- `SECRET_KEY` from env. Never committed. `.env.example` documents required keys with empty values.
- `DEBUG = False` in prod (forced by `prod.py`, not just env-dependent).
- `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` from env.
- Prod enables `SECURE_PROXY_SSL_HEADER`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_*`, `X_FRAME_OPTIONS=DENY`.
- **Owner-scoping is the privacy rule.** Every user-owned model uses `OwnedMixin` (defined in `core.models`). Every view that reads user data calls `Model.objects.for_user(request.user)`. Admin uses `OwnerScopedAdmin`. A missing `.for_user` is a security bug, full stop.
- CSRF middleware always on. HTMX POSTs send the token via the meta-tag wiring in `base.html`.
- No `raw()`, no `extra()`, no string SQL. Code review smell.
- Templates auto-escape. `|safe` / `mark_safe` / `format_html` on untrusted input is forbidden without an explicit ADR.
- Sentry: `send_default_pii=False`. Forces us to think before logging anything user-identifying.

---

## 11. Build-time sub-agent harness (`.claude/`)

Adapted from `betta-tech/ejemplo-harness-subagentes`. Three roles, one feature `in_progress` at a time, disk-based work logs in `progress/`, anti-telephone reports.

| Agent | File | Role |
|---|---|---|
| Leader | `.claude/agents/leader.md` | Orchestrates a feature. Never writes code. |
| Implementer | `.claude/agents/implementer.md` | Writes the code and tests. Reports to `progress/impl_<id>.md`. |
| Reviewer | `.claude/agents/reviewer.md` | Validates against `CHECKPOINTS.md`. Reports to `progress/review_<id>.md`. |
| Migration Writer | `.claude/agents/migration-writer.md` | Specialized Implementer for schema migrations. |
| Test Writer | `.claude/agents/test-writer.md` | Specialized Implementer for pytest. |

Operating rules live in `.claude/AGENTS.md`. Per-feature success criteria in `.claude/CHECKPOINTS.md`. Backlog in `.claude/feature_list.json`. Session bootstrap: `bash .claude/init.sh`.

---

## 12. Deployment

Railway, Dockerfile-based. GitHub→main auto-deploys. **LIVE since 2026-05-25 at https://gymapp-production-1029.up.railway.app** (free trial credit, not paying).

- **Start command = `sh start.sh`** (in `railway.json` and Dockerfile `CMD`). `start.sh` starts **gunicorn immediately** and runs **`migrate` + `createsuperuser` (from `DJANGO_SUPERUSER_*`) in the BACKGROUND**. Three hard-won reasons (the 2026-05-25 deploy saga):
  1. **Healthcheck 400** — Railway's healthcheck hits the app with `Host: healthcheck.railway.app`, so `ALLOWED_HOSTS` MUST include `.railway.app` and `CSRF_TRUSTED_ORIGINS` `https://*.railway.app` (done in `prod.py`). Otherwise Django answers 400 → healthcheck fails.
  2. **`migrate` hung at boot** — connecting to Postgres before Railway's **private network** (`*.railway.internal`, IPv6) is ready, so gunicorn never started → healthcheck failed. Fix: gunicorn first, DB setup backgrounded.
  3. **"Failed to parse start command"** — Railway's startCommand parser rejects shell `&`, `()`, `<`. So the background logic lives in `start.sh`, invoked as the parser-safe `sh start.sh`.
- Healthcheck: `healthcheckPath=/auth/login/` (a GET that needs no DB → passes the moment gunicorn is up), `healthcheckTimeout=60`.
- **Triggering a deploy:** GitHub push *should* auto-deploy but was flaky/laggy. Reliable manual trigger: gymapp → Variables → add/delete any variable → "Apply change → **Deploy**" (builds the **latest** commit). Do NOT use "Redeploy" — it re-runs the SAME (often old) commit.
- Required env on the gymapp service: `DJANGO_SECRET_KEY`, and a Postgres service with `DATABASE_URL=${{Postgres.DATABASE_URL}}` referenced on gymapp (NOT auto-injected across services). Set `DJANGO_SUPERUSER_EMAIL` + `DJANGO_SUPERUSER_PASSWORD` to auto-create the admin. `DJANGO_SETTINGS_MODULE=config.settings.prod` is baked in the Dockerfile. Generate a public domain (Settings → Networking) to be reachable.
- **Adding users (invite-only):** `/admin/` → Users → Add user (email+password); Profile auto-creates via the post_save signal; leave is_staff/is_superuser OFF. `OwnerScopedAdmin` shows the superuser ALL users' data in `/admin/`, while each normal user sees only their own in the app.

Full runbook + Phase 0 verification checklist → `DEPLOYMENT.md`.

---

## 13. Roadmap

| Phase | Scope | Exit criteria |
|---|---|---|
| **0 — Scaffold** | Repo, settings, Docker, Postgres, Railway, base templates, custom User, owner-scoped manager, empty apps, `.claude/` harness, docs. | `runserver` works, `/admin` login works, CI passes. |
| **1 — Tracking MVP** | Exercises (seed + custom); Routines + WeeklySplit; WorkoutSession with interactive set checklist + client-side rest timer; PR auto-detection; profile + body metrics snapshots; dashboard. | A user can log a complete workout end-to-end and see PRs update. |
| **2 — Programming** | Training-style behaviour; progression service (linear + double); substitution scoring; weekly-split reconstruction; warm-up generation; monthly goals. | Recommended weight×reps appears on next session; "swap exercise" returns ranked alternatives. |
| **3 — Nutrition** | BMR, TDEE, bulk/cut/recomp, macro split, food preferences, basic meal slots. | Daily target macros + stub meal plan respecting preferences. |
| **4 — AI integration** | `LLMStrategy` (Claude API) behind existing service interfaces. AI food rec, AI progression, AI substitution rationale. Prompt caching + Haiku/Sonnet split. | At least one service has a toggleable AI strategy and stays cost-bounded. |
| **5 — Polish** | 6-week blocks, deload suggestions, volume/intensity dashboards, analytics. | Coach-grade insights surface in dashboard. |

Detail → `ROADMAP.md`.

---

## 14. Current implementation status

**Phase 1 — Tracking MVP: complete.** All six Phase 1 features in `.claude/feature_list.json` are `done`. The MVP loop works end-to-end: a user can build a routine, schedule it on weekdays, start today's workout from the dashboard, tap-complete sets with the rest timer, finish the session, and see PRs auto-detected.

**Phase 2 — Programming: in progress.** Features landed so far (2026-05-21):

- **session-live-edit**: add/delete exercises and sets mid-workout; add custom exercises; HTMX endpoints.
- **routine-crud**: full user-facing list/create/edit/delete for routines, days, and exercises. Exercise picker with search (240 exercises).
- **routine-generator**: pick split preset + training style → service generates RoutineDays + RoutineExercises with correct rep schemes. HTMX live preview on create form.
- **progression-service**: `DeterministicLinearProgression` (powerlifting) + `DeterministicDoubleProgression` (bodybuilding/powerbuilding). `recommend_next()` wired into `start_session` — every working set pre-filled with weight × reps from last finished session. Increment: +5 kg/+2.5 kg compound/isolation (powerlifting); +2.5 kg/+1.25 kg (others).

**Landed 2026-05-22 (UX + branding, beyond the original feature list):**

- **Smart Fit rebrand**: app branded "Smart Fit Altama"; yellow (`brand`=#F5E000) on near-black (`ink`) palette defined in `tailwind.config.js`; primary buttons `bg-brand text-ink`. Run `npm run build:css` after Tailwind class/config changes.
- **Decimal localization fix**: `FORMAT_MODULE_PATH=["config.formats"]` (+ `config/formats/es{,_MX}/formats.py`) forces a period decimal separator app-wide. es-MX was rendering commas, which also blanked `<input type="number">` values.
- **Rest timer**: green "¡Dale a la serie!" ready banner; `endsAt` persisted in `localStorage` so it survives reload/screen-lock; best-effort Web Notification opt-in (foreground only — no PWA, consistent with decision #3).
- **"Hoy no iré al gym"**: `SkippedDay` model (migration `routines.0002`) + `routines:skip_today` toggle; dashboard `build_week_view()` slides the week's workouts forward past skipped days.
- **Dashboard**: ignores archived routines in the schedule; routine picker to start ANY active routine (`set_today_split` also reschedules today's `WeeklySplit`); live working-set progress counter (DOM + `htmx:after-settle`, no reload); finishing redirects to home with a "¡Ya cumpliste hoy!" message + persistent `done_today` state.
- **Custom exercise from the routine editor**: "Crear nuevo" tab → `routines:exercise_add_custom`; shared creator `services.exercise_library.create_custom_exercise`.
- **Bug fixes**: reps forced integer (client strip + server coerce); set-delete was blocked by the Django Debug Toolbar's expanded panel covering right-aligned buttons (fixed with `DEBUG_TOOLBAR_CONFIG={"SHOW_COLLAPSED": True}`); fixed multi-line `{# #}` comments leaking as visible text (now guarded by tests).

- **substitution-scoring** (2026-05-22): deterministic multi-factor scorer in `services/substitution` (primary/secondary muscle Jaccard overlap, curated-graph bonus, equipment match/availability, category). `ranked_alternatives()` powers a "Cambiar" swap UI on the session exercise card → ranked list → swap (refuses once a set is completed). Satisfies the Phase 2 exit criterion "swap exercise returns ranked alternatives".
- **warmup-generation** (2026-05-22): `services/warmup.warmup_scheme()` ramps 40/60/80% of the working weight, snapped to **loadable** weights per equipment (barbell/smith → 5 kg steps @ 20 kg bar, since the smallest plate 2.5 kg loads both sides; ez-bar → 5 kg @ 10 kg; else 2.5 kg), never ≥ working. **Auto-generated on session start** for barbell/smith lifts with a known weight (`AUTO_WARMUP_EQUIPMENT`); per-exercise **"Calentamiento"** button (`workouts:add_warmups`, idempotent regen) for the rest. Warm-ups stay excluded from the progress counter and PRs.
- **monthly-goals** (2026-05-22): `metrics.MonthlyGoal` (one row per `owner` + `year` + `month`; unique constraint + month-range CHECK; nullable `target_sessions` / `target_volume_kg` / `target_bodyweight_kg`, migration `metrics.0002`). New service `gymapp.services.goals.monthly_goal_progress(goal)` returns `GoalMetric` rows (only for targets that are set): sessions = count of FINISHED sessions started in the month; volume = `Sum(weight_kg * reps)` over completed, non-warm-up working sets; bodyweight = baseline-relative progress (baseline = latest snapshot before the month) that fills toward the target in either direction (cut or bulk), `reached` within ±0.5 kg. Editor at `metrics:goals` (GET shows progress bars, POST upserts the current month). Dashboard "Metas del mes" card (between week view and the recent grid) + nav **"Metas"** link. **This completes Phase 2.**

**Phase 2 — Programming: complete (2026-05-22).** All Phase 2 features in `.claude/feature_list.json` are `done`. Both exit criteria met: recommended weight×reps on every working set (progression), and "swap exercise returns ranked alternatives" (substitution-scoring).

**Phase 3 — Nutrition: in progress (started 2026-05-23).** Features landed:

- **nutrition-targets** (2026-05-23): `users.Profile` gained `sex` (`Sex` choices, blank-default) + `activity_level` (`ActivityLevel` choices, default moderate); migration `users.0002`. `gymapp/services/nutrition` is now a real `DeterministicNutrition`: Mifflin-St Jeor BMR → TDEE (`ACTIVITY_FACTORS` 1.2–1.9) → goal calorie multiplier (`GOAL_CALORIE_MULTIPLIER`: cut 0.80, bulk/hypertrophy 1.10, strength 1.05, recomp/maintain 1.00) → macro split (protein 2.0 g/kg, **2.2 on a cut**; fat 0.8 g/kg; carbs fill remaining kcal, clamped ≥ 0). `daily_target_for_user(user)` pulls bodyweight from the latest `UserMetricSnapshot` + height/DOB/sex from `Profile`, returning `(MacroTarget | None, missing_fields)`. New **`gymapp.apps.nutrition`** app (no models yet, like `dashboard`) mounts `/nutrition/` showing today's kcal + macros, or an amber "completa tu perfil" prompt listing exactly what's missing. Nav **"Nutrición"** link; profile editor (`metrics:profile`) extended with sex + activity selects. The `recommend()` Protocol is the Phase 4 AI seam.
- **food-preferences** (2026-05-23): `users.Profile.food_preferences` (`JSONField(default=list)`, migration `users.0003`) stores a flat list of liked-food slugs. The catalogue lives as a constant in `services/nutrition` — `FOOD_CATALOG` groups protein/carb/vegetable/fat with English slug + Spanish label (no DB table; a deterministic stub plan doesn't need one). Helpers: `grouped_catalog(selected)`, `clean_food_preferences(slugs)` (keeps only known slugs, deduped, in catalogue order), `food_label`, `all_food_slugs`. Editor at `nutrition:preferences` (grouped checkboxes); the nutrition page shows the selected count + an "Editar" link (rendered regardless of profile completeness).
- **meal-slots** (2026-05-23): `services.nutrition.build_meal_plan(target, preferences)` → 4 `MealSlot`s. `MEAL_SLOTS` splits the daily target (breakfast 25% / lunch 35% / dinner 30% / snack 10%); `SLOT_COMPONENTS` says which food categories each slot suggests; foods are rotated through the user's liked items per category by slot index (so slots differ; an empty category contributes nothing). Rendered on `/nutrition/` below the macros. **Closes Phase 3.**

**Phase 3 — Nutrition: complete (2026-05-23).** Exit criterion met: the Nutrition page shows today's calorie + macro target plus four meal slots respecting food preferences.

**Phase 4 — AI integration: SKIPPED (user decision, 2026-05-23).** The user will not pay for anything, and Phase 4 as scoped needs a paid Claude API. We are not building it as a paid feature. The deterministic app is the finished product; the `recommend()` Protocol seam stays available if a free/local model is ever wired in. See memory `feedback-no-spend`.

**Phase 5 — Polish: in progress (started 2026-05-23).** Features landed:

- **analytics-volume** (2026-05-23): `services/analytics` is now real (was a stub). `weekly_volume(user, weeks=8)` → per-week tonnage (Σ weight×reps) + working-set count, Monday-anchored and zero-filled; `sets_by_muscle(user)` → this week's hard sets + volume per **primary** muscle group (full counting — a set counts for every primary muscle the exercise trains; warm-ups + incomplete sets excluded). New read-only view `dashboard:progress` (`/progreso/`) renders an 8-week tonnage trend + sets-per-muscle bars (no new app — lives in the model-less `dashboard` app); nav **"Progreso"** link. Pure functions, no AI (like `services.goals`).
- **deload-suggestions** (2026-05-23): `services.analytics.deload_recommendation(user)` → `DeloadAdvice`. Counts the trailing run of consecutive completed training weeks (the current partial week is ignored), stopping at any week whose tonnage ≤ `LIGHT_WEEK_RATIO` (0.6) of the run **median** (already a deload — median, not peak, so one big week doesn't mask a steady block). Recommends a deload once the count reaches `ACCUMULATION_WEEKS` (5). Always-on status card on `/progreso/` ("llevas N de 5 semanas acumulando") + a conditional amber alert on the dashboard home when recommended.
- **block-programming** (2026-05-23): `routines.TrainingBlock` (owner, `training_style`, `started_on`, `length_weeks`; migration `routines.0003`). `services/coaching/blocks.py` holds deterministic 6-week templates per style (`BLOCK_TEMPLATES`: bodybuilding / powerlifting / powerbuilding, week 6 = deload); `block_status(style, started_on, today)` derives the current week from the calendar (no jobs, like the rest of the MVP). View `routines:block` (`/routines/bloque/`) renders the full plan with the current week highlighted and starts a new block; dashboard **"Tu bloque"** card shows the current week's focus. **Closes Phase 5.** (Gotcha: a template context var named `block` collides with `{% block %}` — used `training_block`.)

**Phase 5 — Polish: complete (2026-05-23).** Exit criterion met: the dashboard surfaces the current block plan, a deload recommendation when warranted, and weekly volume trends (via `/progreso/`). **Phases 1, 2, 3, 5 are all done; Phase 4 (AI) intentionally skipped (no budget).** The deterministic app is feature-complete per the roadmap.

**Post-roadmap enhancements (user-requested, all deterministic/free):**

- **nutrition-meals-plus** (2026-05-23): curated `FOOD_CATALOG` (user trimmed it) + `FOOD_MACROS` (protein/carbs/fat per 100 g, raw/dry). **Meals are built from `MEAL_TEMPLATES`** — fixed *coherent* food combos (e.g. "Avena con whey y plátano", "Pollo, arroz y brócoli") each tagged with the slots it fits and a per-ingredient role (protein/carb/fat → sized to that macro; veg → fixed serving). This replaced the old "one random food per macro category" approach, which produced nonsense like steak + peanut butter. `eligible_templates(slot, prefs)` keeps templates whose protein/carb/fat foods the user likes (veg is swappable, not required), with a fallback to all slot templates so the user always gets a sensible meal. `_scale_template` sizes each ingredient in **raw grams** to the slot's macro share (splitting when a role repeats, e.g. oats+banana) and sums the real per-food macros → grams ↔ macros explain each other. `build_meal_plan` = deterministic pick per slot (at-a-glance plan); `generate_meal` = random eligible pick (variety) → `GeneratedMeal(items: list[MealItem(slug, grams, p/c/f, kcal)], totals)`. `nutrition.SavedMeal` stores the items (with grams) + totals + `eaten_at`. Views: generate (`nutrition:generate_meal`), toggle eaten w/ timestamp (`nutrition:meal_done`), delete (`nutrition:meal_delete`). The page shows only the user's generated meals ("Mis comidas"), **ordered by slot** (desayuno→comida→cena→snack regardless of generation order), each food row showing **grams + per-food kcal + P/C/F** and a meal total. The earlier read-only "Plan sugerido del día" was removed from the page at the user's request (it lacked grams + a mark-done button); `build_meal_plan` stays in the service (tested) but is no longer rendered. (A meal total can exceed the slot target when a fatty protein adds cross-macros — honest, and visible in the breakdown.)

- **nutrition-daily-reset + supplements** (2026-05-24): (1) **Daily reset of meals** — the nutrition page now shows only *today's* `SavedMeal`s (`created_at__date == timezone.localdate()`). Each calendar day starts fresh, so "eaten" marks effectively reset at midnight with **no background job** (consistent with the no-jobs constraint). Old meals stay in the DB (history/admin) but aren't rendered. (2) **Supplement tracker** — new `nutrition.Supplement(name, last_taken_at)` model (owner-scoped, `UniqueConstraint(owner, name)`, migration `nutrition.0002`). `taken_today` is derived (`localdate(last_taken_at) == localdate()`) so it also resets daily with no job. `COMMON_SUPPLEMENTS` (constant in `services/nutrition`) offers quick-add chips (Creatina, Omega 3, BCAAs, …) plus a free-text custom add. Views: `nutrition:supplements` (manage page: list + remove + quick-add + custom), `supplement_add` (get_or_create, trimmed/capped 60ch), `supplement_delete`, `supplement_take` (toggle taken-today, stamps `last_taken_at = now`). Home shows a **"Suplementos de hoy"** checklist: per supplement, "Marcar tomado" → "✓ Tomado a las HH:MM · deshacer". Optional feature — empty by default, never required.

- **nutrition-meal-variety → real curated recipes** (2026-05-24): two iterations the same day. First attempt **generated `MEAL_TEMPLATES` combinatorially** (~2066 sweet×carb×fat / protein×carb×veg combos). The user rejected it: the combos read as incoherent piles of foods ("¿whey aislada, plátano y crema de cacahuate? no dices si licuado o en agua/leche… esos desayunos unos sí, otros no tienen sentido; sé más creativo, busca recetas"). **Final design: a hand-curated library of ~60 REAL named recipes** — `MealTemplate` gained `name` (dish name, e.g. "Licuado de proteína, plátano y avena", "Huevos rancheros", "Tacos de pollo con nopales", "Salmón al horno con camote y espárragos") and `note` (prep hint, e.g. "Licúa con 250 ml de agua o leche", "Cocina la avena con agua o leche"). Counts: 24 breakfast / 27 lunch+dinner / 20 snack (the `_AM` ones serve both breakfast & snack). `generate_meal` picks a random eligible recipe (mains = protein/carb/fat must be liked; **veg is part of the recipe, not a preference filter**) → `GeneratedMeal` now carries `name` + `note`. **The UI renders the dish name as the card title + the prep note in italics + the slot badge** (`SavedMeal` gained `name`/`note`, migration `nutrition.0003`); this was the biggest perceived fix — a meal now reads like a recipe, not a macro spreadsheet. Combinatorial generator + veg-rotation removed. Coherence is curated by hand (still: no sweet nut-butter on a steak). **Variety scales with how many foods the user likes** — to get more breakfasts they should also like eggs/yogurt/granola, not just oats/whey/banana. Tests assert per-slot counts, every recipe has a real name, no sweet fats on savory plates, breakfast variety (≥5 distinct), and that mains respect prefs.

- **nutrition-recipe-shells** (2026-05-24): the user wanted *many more* recipes ("10000 más") but the prior ~60 were too few. Solution that keeps each one a REAL named dish: **recipe FAMILIES (`_Shell`)** — a dish type (`{protein} a la plancha con {carb} y {veg}`, `Licuado de proteína con {carb} y {fat}`, `Tacos de {protein} con {veg}`, `Bowl…`, `Huevos…`, `Salteado…`, `Pasta…`, `Ensalada…`) whose component pools are interchangeable *within culinary bounds*. `_expand_shells()` takes the cartesian product per family → `MEAL_TEMPLATES = _expand_shells(_SHELLS) + _SPECIALS` = **~852 coherent named recipes** (145 breakfast / 692 lunch+dinner / 99 snack). `_format_recipe_name()` builds the Spanish name from food labels (interior words lowercased, first capitalized) so "{protein} a la plancha…" → "Pollo a la plancha con arroz y brócoli". Sweet shells never use savory meats, savory shells never use sweet fats → coherence holds. The ~60 hand-written `_SPECIALS` (antojitos: huevos rancheros, chilaquiles, molletes, tinga, fajitas…) stay layered on top. To grow the count further just widen a shell's pools (one-line change). NOTE: not literally 10000 — that many would require nonsense combos; ~850 real dishes is the honest sweet spot.

- **nutrition-household-portions** (2026-05-24): raw grams aren't intuitive for many foods, so each food row now shows a **household portion** before the grams (e.g. "Huevo · 2 piezas (100 g)", "Jamón de pavo · 1 rebanada (30 g)", "Whey · 1.5 medidas (45 g)", "Crema de cacahuate · 1 cucharada (16 g)", "Almendras · 1 puño (28 g)", "Plátano/Nopal/Aguacate · pieza", "Aceite · cucharada"). `FOOD_PORTIONS` (slug → grams/unit + sing/plural) + `portion_label(slug, grams)` in `services/nutrition`; `SavedMeal.items` attaches `portion`. Foods deliberately left in grams (per user): rice/oats/pasta/quinoa/legumes, **tuna (cubed grams, not cans)**, **honey (grams)**, yogurt, vegetables, potato. `portion_label` rounds to the nearest half-unit and returns "" below half a unit so a 20 g sliver never reads as "0.5 aguacate". Grams stay in parentheses so the macro math still explains itself.

- **responsive fixes** (2026-05-24): (1) **"Esta semana" overflow** — long routine-day labels (e.g. "Push (pecho/hombro/tríceps)") overflowed the day card. Fixed with `break-words leading-tight` on the label so it wraps inside the card. (2) **Mobile nav** — the sidebar's mobile top-bar used a horizontal-scroll `<ul>` (`overflow-x-auto`). Replaced with an **Alpine hamburger toggle** in `partials/_nav.html`: `x-data="{ open }"`, a ☰/✕ button (`md:hidden`), and `<ul :class="open ? 'flex' : 'hidden'"` + `x-cloak` + static `md:flex` so the menu is a full-width vertical dropdown on mobile and the always-visible left sidebar on desktop. Logout lives inside the menu on mobile, pinned at the bottom on desktop. No horizontal scroll at 375px (browser-verified).

**Next up (user roadmap, confirmed 2026-05-23):** (1) **Fatigue/readiness** module — per-muscle fatigue that decays over days (deadlift → lumbar stays fatigued longer) + daily sleep/stress/soreness inputs → "hoy no vayas pesado" advice. User chose **auto + manual adjust**. (2) **Rehab/prevention** — corrective/mobility library + injury log + avoid/swap rules. Both deterministic/free.

**Bug fixes applied (2026-05-21):**

1. **Set numbering**: `delete_set` renumbers sibling `SetLog.ordering` to stay contiguous. Previously deleting set #2 of 3 caused "1., 3., 3., 4." on next add.
2. **Duplicate sessions**: `start` view redirects to existing `IN_PROGRESS` session instead of creating a second one. History page shows "Reanudar" banner.
3. **Template bugs**: multiline Django `{# #}` comments render as visible text — removed. Alpine v3 event handler fixed. Two-step finish confirmation added.
4. **Exercise picker in routines**: `_render_day_card()` now includes `picker_exercises` queryset.
5. **Routine create auto-preview**: hidden declarative HTMX button avoids `hx-boost` interference.

**Test suite: 244 tests passing (2026-05-24).** Coverage: workout service + views, progression service (unit + DB integration), exercise library, PR service, routine generator, substitution, warmup, monthly goals (service + editor view + dashboard card), nutrition (BMR/TDEE/macros service + page view + profile editor + food-preferences catalogue/editor + meal-plan builder + daily-reset scoping + supplement tracker), analytics (weekly volume + sets-per-muscle + deload recommendation + Progreso page), block-programming (block templates service + block page/view), dashboard (incl. skip-day slide-forward + archived-routine filtering), routines (incl. custom-exercise creation), metrics, smoke.

**Environment (2026-05-21):** Project is at `~/gymapp/` (moved off iCloud `Documents/`). Python 3.12, Node 24. `.env` → SQLite. Superuser: `fglzb00@gmail.com` / `gym1234`. Start server: `source .venv/bin/activate && python manage.py runserver`.

**First local test (2026-05-20):** Server ran on `127.0.0.1:8000` against SQLite with demo data. **User reported the UI feels slow.**

**Second test (2026-05-20, after applying app-level perf fixes):** A first request to `/auth/login/` took **10.1 seconds**. App-level fixes applied (still useful even after the real root cause is solved):

1. Compiled Tailwind locally (`npm install && npm run build:css`) and switched `templates/base.html` to always use `{% static 'tailwind.css' %}` instead of the Play CDN. No more browser-side JIT.
2. Added an HTMX progress bar (`#htmx-progress`) — a 2px line at the top of the viewport that animates whenever an HTMX request is in flight. Wired in `base.html`.
3. Overrode `STORAGES` in `config/settings/dev.py` to use `StaticFilesStorage` instead of Whitenoise's `CompressedManifestStaticFilesStorage`. The manifest variant requires `collectstatic` and would otherwise raise on every `{% static %}` tag in dev. (Prod keeps the manifest storage from `base.py`.)
4. Audited dashboard + list view querysets — all use `select_related`/`prefetch_related` correctly. No N+1.

**But the real root cause is environmental, not in the app code:**

- The project lives at `/Users/fernandoulrich/Documents/gymapp/`. **`Documents/` is synced to iCloud Drive by default on macOS.**
- The disk is **98% full (~4 GB free of 228 GB).**
- iCloud Drive (`bird` daemon) is aggressively **offloading project files** to free local disk. Observed: `.venv` shrunk from 10 MB to 2.2 MB between two checks within minutes; `du -sh node_modules` shows `0B` despite 84 packages being installed.
- Every Python `import` or template render that touches an offloaded file blocks waiting for iCloud to re-materialise it. `django.setup()` was observed to hang indefinitely on `django/utils/regex_helper.py` (captured via `faulthandler.dump_traceback_later`).

**Fix (user action required):** Pick one —

- **Move the project off iCloud.** `mkdir -p ~/Code && mv /Users/fernandoulrich/Documents/gymapp ~/Code/`. Cleanest fix; everything just works after.
- **Free a lot of disk space** AND right-click `gymapp/` in Finder → "Keep Downloaded". This pins the directory locally and tells iCloud not to evict it. Less reliable than moving.
- **Both.** Move it AND free up the disk (top hogs: `~/Library/Caches/Google` 3.9 GB, `~/Library/Caches/JetBrains` 1.4 GB, `~/Library/Caches/com.spotify.client` 1.1 GB, `~/Library/Caches/SiriTTS` 969 MB).

Until one of those is done, `runserver` is unusable on this machine. Code is correct; environment is the blocker.

**Phase 0 — Scaffold: complete.**

- Repo skeleton created, all config files in place.
- Custom `User` model with `users.0001_initial` migration landed.
- Owner-scoped manager + admin available in `core`.
- All other domain apps exist as empty shells with planned-entity docstrings in their `models.py`.
- Service layer has Protocols + `Deterministic*` stubs (Phase 1 fills behavior).
- Dashboard placeholder renders at `/`.
- Login at `/auth/login/`, admin at `/admin/`.
- Tailwind via Play CDN in dev; PostCSS pipeline ready for prod build.
- Sentry integration is wired but disabled until `SENTRY_DSN` is set.
- CI lints + tests on push.
- `.claude/` harness with Leader/Implementer/Reviewer + Migration Writer + Test Writer agents.
- Initial git commit and (optionally) the GitHub repo + Railway link land at the user's request.

Phase 1 features landed:
- **exercises**: `MuscleGroup`, `Equipment`, `Exercise` (nullable owner, `visible_to(user)`), `ExerciseAlternative` (directional, auto-mirrored). 78 curated exercises seeded across 17 muscle groups / 7 equipment types via idempotent loader + data migration. `DeterministicSubstitution` backs onto the real graph.
- **routines**: `Routine`, `RoutineDay`, `RoutineExercise`, `WeeklySplit`. Owner-scoped. CHECK constraint on `target_reps_low <= target_reps_high`. UNIQUE `(owner, weekday)` on splits.
- **workouts**: `WorkoutSession`, `ExerciseLog`, `SetLog`. Service-layer orchestration (`start_session`, `complete_set`, `update_set_values`, `swap_exercise`, `finish_session`, `session_progress`). HTMX tap-to-complete checklist + Alpine.js sticky rest timer. Owner-scoped at every entry point.
- **prs**: `PersonalRecord` with `(owner, exercise, reps)` unique. `update_prs_from_session` runs on `finish_session` — keeps the heaviest weight per rep count. Manual create/edit/delete views.
- **metrics**: `UserMetricSnapshot` (weight + optional body-fat) + self-serve `/metrics/profile/` editor for Profile baseline (height, DOB, training style, training goal, default rest seconds).
- **dashboard**: Real home page — today's planned routine day (or in-progress session), this week's split, recent sessions, recent PRs, latest body metric. Replaces the Phase 0 placeholder.

Update this section at the start of every phase transition.

---

## 15. Important constraints

- **No AI APIs in MVP.** All "coaching" features are deterministic. Future AI is a strategy swap, not a rewrite. Don't sneak `anthropic` / `openai` calls into Phase 1–3 code.
- **No background jobs in MVP.** No Celery, no Redis, no worker dynos. Recomputes happen lazily when a user opens the relevant screen. If you think you need a job, first prove the request can't be done on-demand.
- **No allauth, no social login.** Django built-in auth only. Account creation goes through `/admin` only.
- **No public signup.** Adding one needs an explicit decision in `DECISIONS.md`.
- **No multi-tenant isolation beyond owner-scoping.** No schemas per user. No row-level security in Postgres. The `for_user` pattern is the entire isolation story.
- **Single timezone.** All users see the same calendar day. Adding per-user TZ is a Phase 2+ decision.

---

## 16. Reusable patterns

- **Owner-scoped model**: subclass `OwnedMixin` (gives you `owner` FK + `OwnerScopedQuerySet.as_manager()`).
- **Owner-scoped admin**: subclass `OwnerScopedAdmin` from `core.admin`.
- **Timestamps**: subclass `TimestampedModel` from `core.models`.
- **Cross-app business logic**: write a service in `gymapp/services/<area>/` with a `Strategy` Protocol and a `Deterministic*` impl. Import the facade (`from gymapp.services.coaching import progression`).
- **HTMX partials**: render and return a fragment template from `templates/partials/`. Include `csrf_token` in any form; the meta-tag wiring in `base.html` handles `hx-post` automatically.
- **Tests**: `factory-boy` factories in `tests/factories.py`; tests mirror source layout under `tests/`.
- **Migrations**: data migrations are `RunPython` with both directions, or `reversible = False` with a comment.

---

## 17. When updating this file

- Edit `CLAUDE.md` in the same commit that introduces an architectural or business change. A drift between this file and the code is a bug.
- For one-line decisions, also append a line to `DECISIONS.md` (ADR format).
- For deeper architectural sections, expand `ARCHITECTURE.md`.

---

## 18. Pending pickup (resume here)

In priority order for the next session:

1. **GitHub push.** `gh` is installed. Run `! gh auth login --hostname github.com --git-protocol ssh --web`, then push. Auto-deploy to Railway triggers on push to `main`.
2. **Railway deploy.** Runbook in `DEPLOYMENT.md §2`. Requires env vars: `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DATABASE_URL` (auto-injected).
3. **Phase 2 remaining features** (in order from `ROADMAP.md`):
   - **substitution-scoring**: multi-factor ranking for the "swap exercise" picker (muscle overlap, equipment, fatigue).
   - **warmup-generation**: auto-prepend `is_warmup=True` SetLogs (e.g. 50%×5, 70%×3, 85%×1) when starting a session.
   - **monthly-goals**: `MonthlyGoal` model + dashboard card.
4. **Phase 2 exit criterion check**: "swap exercise returns ranked alternatives" — currently returns unranked. Progression pre-fill is done.

Local dev state:
- Project at `~/gymapp/`. Server starts with: `source .venv/bin/activate && python manage.py runserver`
- `pytest` → 100 passing. `ruff check .` → clean.
