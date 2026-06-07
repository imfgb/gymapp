# Architecture

System-design overview. Read `CLAUDE.md` first for the high-level "why"; this file is the deeper "how".

## 1. System shape

A monolithic Django web app. Single web service on Railway, single managed Postgres. No queue, no cache, no worker — by decision (`CLAUDE.md` constraint: no background jobs in MVP). Reads and writes go straight through Django views into services and the ORM.

```
                  ┌─────────────────┐
                  │   Browser       │
                  │ (HTMX + Alpine) │
                  └────────┬────────┘
                           │ HTTPS (Railway-terminated)
                  ┌────────▼────────┐
                  │   gunicorn      │
                  │   Django 5.2    │
                  │   whitenoise    │
                  └────────┬────────┘
                           │
                  ┌────────▼────────┐
                  │  PostgreSQL 16  │
                  │  (Railway)      │
                  └─────────────────┘
                           │
                  ┌────────▼────────┐
                  │   Sentry        │  (optional, prod only)
                  └─────────────────┘
```

## 2. Request lifecycle

1. Browser issues `GET /workouts/<id>/`.
2. `SecurityMiddleware` → `WhiteNoiseMiddleware` (serves static if matched, otherwise pass) → `SessionMiddleware` → `LocaleMiddleware` (Spanish) → `CommonMiddleware` → `CsrfViewMiddleware` → `AuthenticationMiddleware` → `MessageMiddleware` → `XFrameOptionsMiddleware`.
3. URL conf in `config/urls.py` routes to the relevant app's `urls.py`.
4. View calls a **service** (`gymapp.services.*`) for any cross-context logic. The view never reaches into another app's models directly.
5. Service queries models via `Model.objects.for_user(request.user)` (owner-scoping) — never raw `Model.objects.filter(...)` on user-owned data.
6. Template renders. HTMX-targeted endpoints return a fragment from `templates/partials/`; full-page requests extend `base.html`.

## 3. Bounded contexts (apps)

Each app in `gymapp/apps/` owns a coherent domain. Cross-app reads go through a service, not direct ORM access from one app's view into another app's model. This boundary is what keeps the AI strategy swap viable later — services are the only place where strategy injection happens.

| App | Owns | Talks to |
|---|---|---|
| `users` | `User`, `Profile` | (foundation — everyone references `AUTH_USER_MODEL`) |
| `exercises` | catalogue + alternatives graph | (nothing) |
| `routines` | planned workouts, weekly schedule | `exercises` (read-only via service) |
| `workouts` | actual sessions, sets | `exercises`, `routines` (read-only via service); writes `prs` via service |
| `prs` | personal records | (read-only consumer of workouts via service) |
| `metrics` | body composition, monthly goals, fatigue/readiness | `users`, `workouts` (read-only via service) |
| `nutrition` | calorie/macro targets, saved meals, supplements | `users`, `metrics` (read-only via service) |
| `injuries` | injury log, mobility library | `exercises` (read-only via service) |
| `feedback` | bug reports | standalone (superuser-read; not owner-scoped) |
| `dashboard` | read-only landing | all of the above via services |
| `core` | mixins, owner-scoping | (foundation) |

## 4. Service layer

Located in `gymapp/services/`. Every service subpackage exports a **Protocol** (the interface) and a **`Deterministic*` implementation**. The facade `gymapp.services.coaching` re-exports ready-to-use singletons.

```
┌───────────────────────────────────────────────────────────┐
│   gymapp/services/coaching/__init__.py  (the facade)      │
│     progression  = DeterministicProgression()             │
│     substitution = DeterministicSubstitution()            │
└────────────┬──────────────────────────┬────────────────────┘
             │                          │
   ┌─────────▼──────────┐    ┌──────────▼─────────────────┐
   │  progression/      │    │  substitution/             │
   │  Protocol          │    │  Protocol                  │
   │  Deterministic*    │    │  Deterministic*            │
   │  (LLMStrategy P4)  │    │  (LLMStrategy P4)          │
   └────────────────────┘    └─────────┬──────────────────┘
                                       │
                            ┌──────────▼──────────────┐
                            │  exercise_library/      │
                            │  Protocol               │
                            │  Deterministic          │
                            └─────────────────────────┘
```

**Why Protocol + Deterministic from day one?** Because retrofitting an AI seam after the fact requires rewriting every call site. Doing it up front costs ~20 LOC per service and zero ongoing maintenance.

## 5. Frontend architecture

Django templates render HTML. HTMX provides partial-page updates (logging a set, swapping an exercise, ticking the checklist). Alpine.js holds tiny client-side state (rest timer, dropdown open/close). Tailwind is compiled to `static/tailwind.css` (loaded via `{% static %}` in `base.html`) in **both dev and prod** — run `npm run build:css` after changing classes. (Dev originally used the Tailwind Play CDN but switched to compiled CSS for performance.)

- **Mobile-first responsive** with Tailwind utility classes. Desktop adds a left sidebar; mobile collapses to a top bar.
- **No SPA.** Views return real HTML. Browser back/forward "just works".
- **HTMX boost** is on (`hx-boost="true"` on `<body>`) so internal anchor clicks become AJAX swaps, but each URL still has a real server-rendered page.
- **CSRF** travels via a `<meta>` tag read on `htmx:configRequest`. Every HTMX form has `{% csrf_token %}` for the no-JS fallback.

## 6. Data layer

- PostgreSQL 16. One database per environment.
- Migrations are append-only after merge to `main`.
- `BigAutoField` PKs everywhere.
- Owner-scoped queries via `OwnerScopedQuerySet.for_user(user)`. This is the *only* isolation mechanism — no row-level security, no per-user schemas.
- Time stored UTC; displayed in `America/Mexico_City`.
- `db_index=True` on FKs that drive list queries and on date fields that drive ordering. Per-app index decisions documented in `DATABASE.md`.

## 7. Settings & secrets

Split-settings via `django-environ`:

- `base.py` — shared.
- `dev.py` — adds debug toolbar (if installed), console email backend, lenient defaults.
- `prod.py` — security headers, HSTS, secure cookies, optional Sentry init.
- `test.py` — fast hasher, locmem email, no Whitenoise manifest.

`SECRET_KEY`, `DATABASE_URL`, `SENTRY_DSN`, and similar come from env vars (`.env` in dev, Railway dashboard in prod). `.env` is gitignored. `.env.example` is the contract.

## 8. Build-time sub-agent harness

See `CLAUDE.md` §11 and `.claude/AGENTS.md`. The harness is the *development workflow*, not a runtime concern. It enforces single-feature flow, disk-based reports, and anti-telephone communication between Claude Code sub-agents. It has no production footprint.

## 9. Observability

- **Logs**: stdout via Django logging, picked up by Railway's log viewer.
- **Errors**: Sentry (free tier) if `SENTRY_DSN` is set. Otherwise unhandled exceptions still hit Django's default error logging.
- **Performance**: nothing in MVP. Sentry traces are off (`traces_sample_rate=0.0`). Add later only if a real bottleneck surfaces.

## 10. Failure modes & their handling

| Failure | Handling |
|---|---|
| Postgres unreachable | Gunicorn returns 500; Sentry captures; user retries. No queue to drain. |
| Migration fails at boot | `start.sh` runs `migrate` in the background *after* gunicorn is up (see `DEPLOYMENT.md §1a`), so a failure is logged to Railway but the container keeps serving (possibly with unapplied migrations). Fix forward and redeploy. |
| Out-of-memory on web | Gunicorn worker restarts (auto). Two workers per container gives breathing room. |
| Static file missing | Whitenoise's manifest storage raises at build time (catches during `collectstatic`), not at request time. |

## 11. Scaling assumptions

Designed for ≤ ~20 users. A single Railway service (one container) + the smallest managed Postgres tier comfortably handles this. If we ever cross into hundreds of users, the natural first move is enabling Sentry transactions to find slow queries, then adding indexes / select_related. We don't pre-optimize.

## 12. Anti-patterns we deliberately avoid

- **Premature multi-tenancy**. No schema-per-tenant. The `for_user` pattern is enough.
- **Premature CQRS / read models / event sourcing.** Reads and writes share the same models.
- **Premature SPA.** HTMX gets us 95% of the interactivity at 5% of the complexity.
- **Premature microservices.** The whole app is one Django process.
- **Premature feature flags.** Phases are gates instead.
