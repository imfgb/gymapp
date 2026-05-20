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
| `users` | Custom User (email-as-username), Profile (training prefs, height, DOB), one-shot password-change-on-first-login. | `User`, `Profile` |
| `exercises` | Curated + custom exercise catalogue. Each tags primary/secondary muscle groups, equipment, category. Self-referencing alternatives M2M. | `MuscleGroup`, `Equipment`, `Exercise` (nullable `owner` → null = global), `ExerciseAlternative` |
| `routines` | User-defined workout templates and weekly schedule. | `Routine`, `RoutineDay`, `RoutineExercise`, `WeeklySplit` |
| `workouts` | Actual training sessions and set-by-set logs. Drives the interactive checklist. | `WorkoutSession`, `ExerciseLog`, `SetLog` |
| `prs` | Personal records per exercise per rep-count. Auto-detected from finished `SetLog`s + manual overrides. | `PersonalRecord` |
| `metrics` | Body composition snapshots. Phase 2 adds `MonthlyGoal`. | `UserMetricSnapshot` |
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
| `nutrition` | Stub Protocol. | BMR (Mifflin-St Jeor), TDEE, macros (Phase 3). |
| `analytics` | Stub Protocol. | Volume/intensity rollups (Phase 4). |

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

1. `python3.12 -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements-dev.txt`
3. `cp .env.example .env`; generate a secret key: `python -c "import secrets; print(secrets.token_urlsafe(50))"`; paste into `DJANGO_SECRET_KEY`.
4. `docker compose up -d` (Postgres on `localhost:5432`).
5. `python manage.py migrate`.
6. `python manage.py createsuperuser`.
7. `python manage.py runserver`. Visit `http://127.0.0.1:8000/` (redirects to `/auth/login/`) and `http://127.0.0.1:8000/admin/`.
8. `pre-commit install` once.

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

**Phase 1 in progress.** `phase1-exercises-catalogue` landed (models, migrations, seed loader, admin, tests).

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

Phase 1 landed so far:
- `exercises` app fully implemented: `MuscleGroup`, `Equipment`, `Exercise` (nullable owner, `visible_to(user)` queryset), `ExerciseAlternative` through-model with a `from != to` check constraint.
- 78 curated exercises in `seeds/exercises.yaml` covering chest, back, shoulders, arms, legs, core across all equipment types, plus 42 alternative pairs (auto-mirrored to ~84 rows).
- Idempotent loader at `gymapp/services/exercise_library/loader.py`; wired into `exercises.0002_seed_catalog` data migration.
- `DeterministicSubstitution` service now backs onto the real graph (Protocol unchanged).
- Admin for all 4 models with owner-scoped queryset for non-superusers.
- Tests: `tests/apps/exercises/test_models.py` + `tests/services/test_exercise_library.py`.

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
