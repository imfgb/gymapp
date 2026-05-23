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
| `routines` | User-defined workout templates and weekly schedule. | `Routine`, `RoutineDay`, `RoutineExercise`, `WeeklySplit` |
| `workouts` | Actual training sessions and set-by-set logs. Drives the interactive checklist. | `WorkoutSession`, `ExerciseLog`, `SetLog` |
| `prs` | Personal records per exercise per rep-count. Auto-detected from finished `SetLog`s + manual overrides. | `PersonalRecord` |
| `metrics` | Body composition snapshots + per-month goals. | `UserMetricSnapshot`, `MonthlyGoal` |
| `nutrition` | Read-only nutrition page: today's calorie + macro target (computed by `services.nutrition`). Meal-slot models land with Phase 3 meal-slots. | (no models yet) |
| `dashboard` | Read-only views: today's workout, this week's split, recent history, PR highlights. | (no models) |

---

## 6. Runtime service layer

Located in `gymapp/services/`. **No view ever calls another app's model directly across context boundaries; it calls a service.**

| Service | MVP behaviour | Later |
|---|---|---|
| `exercise_library` | Loads `seeds/exercises.yaml` via data migration. `lookup_alternatives(slug, equipment)` over the curated graph. | AI-ranked (Phase 4). |
| `progression` | `recommend_next` returns the last completed weight×reps. | Linear/double progression → RPE-driven → AI-tuned. |
| `substitution` | Delegates to `exercise_library`. | Multi-factor scoring (Phase 2). |
| `coaching` | Facade re-exporting `progression` + `substitution`. | Orchestrates programming sessions / 6-week blocks. |
| `nutrition` | `DeterministicNutrition`: Mifflin-St Jeor BMR → TDEE → goal-adjusted calories → macro split. `daily_target_for_user`. | AI meal rec (Phase 4). |
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

Railway, Dockerfile-based. GitHub→main auto-deploys.

- Release phase (`Procfile`): `python manage.py migrate --noinput`.
- Web phase: `gunicorn config.wsgi --bind 0.0.0.0:$PORT --workers 2 --timeout 30`.
- Required env vars in Railway: `DJANGO_SETTINGS_MODULE=config.settings.prod`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `SENTRY_DSN` (optional), `DJANGO_CSRF_TRUSTED_ORIGINS` (when adding a custom domain). `DATABASE_URL` is auto-injected.

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

Phase 5 features still queued: **block-programming** (6-week block templates per training style). Closing it meets the Phase 5 exit criterion (clear plan + deload rec + weekly volume trends).

**Bug fixes applied (2026-05-21):**

1. **Set numbering**: `delete_set` renumbers sibling `SetLog.ordering` to stay contiguous. Previously deleting set #2 of 3 caused "1., 3., 3., 4." on next add.
2. **Duplicate sessions**: `start` view redirects to existing `IN_PROGRESS` session instead of creating a second one. History page shows "Reanudar" banner.
3. **Template bugs**: multiline Django `{# #}` comments render as visible text — removed. Alpine v3 event handler fixed. Two-step finish confirmation added.
4. **Exercise picker in routines**: `_render_day_card()` now includes `picker_exercises` queryset.
5. **Routine create auto-preview**: hidden declarative HTMX button avoids `hx-boost` interference.

**Test suite: 200 tests passing (2026-05-23).** Coverage: workout service + views, progression service (unit + DB integration), exercise library, PR service, routine generator, substitution, warmup, monthly goals (service + editor view + dashboard card), nutrition (BMR/TDEE/macros service + page view + profile editor + food-preferences catalogue/editor + meal-plan builder), analytics (weekly volume + sets-per-muscle + deload recommendation + Progreso page), dashboard (incl. skip-day slide-forward + archived-routine filtering), routines (incl. custom-exercise creation), metrics, smoke.

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
