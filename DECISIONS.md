# Architectural Decision Records

One bullet per decision. Newest at the bottom. The reasoning for early decisions is in `CLAUDE.md` §3; this file is the chronological log.

Format: `ADR-NNN: title — short rationale. (date, source)`

---

- **ADR-001: Personal + close circle audience (≤ ~20 users).** No public signup, no Stripe, no marketing site. Keeps Phase 0 small. (2026-05-19, discovery #1)
- **ADR-002: No AI APIs in MVP.** Rule-based recommendations, formula-based nutrition, algorithmic progression, deterministic exercise substitutions. Services expose a `Strategy` Protocol so an `LLMStrategy` can swap in later without touching call sites. (2026-05-19, discovery #2)
- **ADR-003: Desktop-first responsive web.** Mobile-first breakpoints in Tailwind, but no PWA, no offline, no service workers. (2026-05-19, discovery #3)
- **ADR-004: Django templates + HTMX + Alpine.js + Tailwind.** No SPA. Tailwind via Play CDN in dev, PostCSS pipeline in prod. (2026-05-19, discovery #4)
- **ADR-005: Invite-only auth via `/admin`.** Django built-in auth (no allauth, no social login, no public signup). Superuser creates accounts. (2026-05-19, discovery #5)
- **ADR-006: Metric units only (kg, cm).** No conversion layer. (2026-05-19, discovery #6)
- **ADR-007: Deploy on Railway.** Web service from Dockerfile + Railway-managed Postgres + GitHub→main auto-deploy. (2026-05-19, discovery #7; supersedes original plan to use Hostinger)
- **ADR-008: Spanish UI, English domain data.** `LANGUAGE_CODE=es-mx`, no i18n machinery, exercise names + muscle groups stay in English. (2026-05-19, discovery #8)
- **ADR-009: Curated seed (~80–120 exercises) + per-user custom exercises.** Unified `Exercise` model with nullable `owner` FK. (2026-05-19, discovery #9)
- **ADR-010: No background jobs in MVP.** No Celery, no Redis, no workers. All recomputes are lazy/on-demand. (2026-05-19, discovery #10)
- **ADR-011: Tracking-only MVP scope.** Auth + profile + exercises + routines + logging + PRs + history. Programming → Phase 2, Nutrition → Phase 3, AI → Phase 4. (2026-05-19, discovery #11)
- **ADR-012: Single timezone `America/Mexico_City`.** Shared by all users; no per-user TZ field. (2026-05-19, discovery #12)
- **ADR-013: Private GitHub repo `imfgb/gymapp`** with Railway auto-deploy on push to `main`. (2026-05-19, discovery #13)
- **ADR-014: Both runtime services and build-time `.claude/` harness.** Runtime: services package under `gymapp/services/`. Build-time: Leader/Implementer/Reviewer (+ Migration Writer, Test Writer) under `.claude/agents/`, with disk-based progress logs. (2026-05-19, discovery #14)
- **ADR-015: Dockerfile for prod, `manage.py runserver` for local dev.** docker-compose for local Postgres only — Django runs on the host for faster reload. (2026-05-19, discovery #15)
- **ADR-016: Sentry free tier for error reporting.** Optional via `SENTRY_DSN`; disabled in dev. (2026-05-19, discovery #16)
- **ADR-017: Pytest + factory-boy, services + non-trivial models only.** No coverage gate. CI runs tests on push. (2026-05-19, discovery #17)
- **ADR-018: Interactive UI checklist for set logging.** Tap-to-complete sets, auto-rest-timer, next-set highlight. `completed_at` on `SetLog`. (2026-05-19, discovery #18)
- **ADR-019: Custom User with email-as-username.** Phase 0. `users.User` extends `AbstractUser`, drops `username`. Required because invite-only via admin uses email as the identifier. (2026-05-19, scaffold)
- **ADR-020: Owner-scoping as the only privacy boundary.** No row-level security, no per-tenant schemas. `OwnedMixin` + `OwnerScopedQuerySet.for_user(user)` is the rule. (2026-05-19, scaffold)
- **ADR-021: Whitenoise instead of nginx/CDN.** Acceptable at this scale; removes a moving part on Railway. (2026-05-19, scaffold)
- **ADR-022: `ruff` replaces black + isort + flake8.** Single tool, faster, less config. (2026-05-19, scaffold)
- **ADR-023: `Exercise.objects.visible_to(user)` instead of `OwnedMixin.for_user(user)`.** Exercises have nullable `owner` because global (seeded) rows are visible to everyone; the standard `OwnedMixin` would hide them. `visible_to` returns globals ∪ user's own; `for_user` is reserved for edit/delete paths that only touch user-owned rows. (2026-05-19, phase1-exercises-catalogue)
- **ADR-024: Seed data is upsert-only, never delete.** Re-running the loader updates existing rows and adds new ones, but never removes a seeded row even if it disappears from YAML. Removing a seeded exercise would orphan any user FK pointing at it; explicit deletion is a manual mgmt-command operation. (2026-05-19, phase1-exercises-catalogue)
- **ADR-025: ExerciseAlternative is directional with auto-mirroring.** The model allows A→B without B→A, but the seed loader mirrors each declared pair by default (override via `mirror: false` per-link). Lets us model asymmetric substitutions later (e.g. "X is an okay sub for Y but Y is bad for X") without rewriting the schema. (2026-05-19, phase1-exercises-catalogue)
- **ADR-026: Bug-triage JSON API authenticated by a bearer token, not by session.** The `feedback` app exposes `GET /feedback/api/bugs/` + `POST /feedback/api/bugs/<id>/status/` for the admin triage-automation skills to reach production over HTTPS. Auth is a single `FEEDBACK_API_TOKEN` (env var, `hmac.compare_digest`; 503 when unset, 401 on mismatch) instead of a logged-in session, because the caller is a CLI/skill with no browser. The POST endpoints are therefore `@csrf_exempt` — CSRF protects cookie-based sessions, which this API doesn't use; the bearer token is the auth boundary. Token lives only in env (Railway + local `.env`), never committed. (2026-06-07, bug-triage-automation) See `docs/superpowers/specs/2026-06-07-bug-triage-automation-design.md`.
