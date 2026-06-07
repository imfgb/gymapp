# Bug-triage automation — design

**Date:** 2026-06-07
**Status:** approved (brainstorming) → ready to implement

## Goal

Let the gymapp admin work through user-submitted feedback (bugs + ideas) in a
controlled loop: read the open reports **from production**, get per-item
approval, then fix/implement the approved ones with the project's existing
discipline (`/debug` + `/test`), commit and push — **never deploy** (the admin
deploys manually).

This is the admin-facing automation layer over the existing `feedback` app
(`BugReport`, `/feedback/admin/`).

## Decisions (from brainstorming, 2026-06-07)

| # | Decision |
|---|---|
| Trigger | **Manual.** Admin invokes a slash command. No daemon, no hook, no schedule. |
| Scope | **All `BugReport`s with `status=open`, any reporter.** Bug vs. idea is classified at triage (the model has no type field). |
| Data source | **Production** (Railway Postgres). The local SQLite DB is irrelevant for this workflow. |
| Reach mechanism | **HTTPS JSON API + bearer token** (not a browser session, not a local DB connection). Clean for a portfolio repo; no DB creds on the laptop. |
| Git boundary | Per item: fix → test/verify → **commit + push to `main`** → mark `resolved`. Stop before deploy. |
| Status writes | `triaged` when the executor starts an item; `resolved` after a successful push (with a "deploy to make it live" reminder). |
| Cost | **$0.** All custom Django code + markdown skills. No paid APIs/services. Railway hosting is a pre-existing, separate decision. |

## Architecture — 3 deliverables, built in order

```
[1] Bug-Triage API  ──►  [2] /auto-bug-fixer  ──►  [3] /change-approval-orchestrator
  (Django feature)         (executor skill)          (gate + loop skill)
```

### 1 — Bug-Triage API (`feedback` app)

Token-authenticated JSON endpoints so a CLI/skill can read open bugs and update
status over HTTPS against production.

- `GET /feedback/api/bugs/?status=open` → `{"bugs": [{id, subject, description, page_area, page_url, reporter_email, status, created_at}, ...]}`. `status` filter optional (defaults to all); validated against `BugStatus`.
- `POST /feedback/api/bugs/<id>/status/` → body `{"status": "triaged"|"resolved"|"open"}` → updates and returns the row.

**Auth:**
- Single bearer token from env `FEEDBACK_API_TOKEN`. Header `Authorization: Bearer <token>`.
- Constant-time compare (`hmac.compare_digest`).
- If `FEEDBACK_API_TOKEN` is empty/unset → endpoints return **503** (no empty-token bypass).
- A bad/missing token → **401**.
- The POST endpoint is `@csrf_exempt` (bearer auth, not session/cookie). Documented as an ADR in `DECISIONS.md`.

**Security notes:**
- Exposes the same PII as `/feedback/admin/` (subject/description text + reporter email). The token gates it equivalently. `send_default_pii=False` for Sentry stays.
- Token lives only in env vars (Railway + local `.env`, gitignored). `.env.example` lists it empty. **Never committed.**
- Reuses the existing `BugStatus` validation. No `raw()`/`extra()`.

**Tests (TDD):** no token configured → 503; missing/!wrong token → 401; valid token GET returns only open bugs with the right shape; valid token POST changes status and rejects invalid status (400); non-bearer/garbage header → 401.

### 2 — `/auto-bug-fixer` skill (executor)

`.claude/skills/auto-bug-fixer/SKILL.md`. Operates on **one** approved bug id.

Workflow: mark `triaged` (API) → reproduce/scope → fix (bug: `/debug` discipline; idea: per working agreement) → `/test` green → if UI: `npm run build:css` + browser-verify at 390px (WebKit) → commit referencing `bug #<id>` + push to `main` → mark `resolved` (API) → report `done`/`blocked` back.

Guardrails (the baseline failure modes to counter):
- **Never deploys.** Push to `main` is the last git step; the admin deploys.
- **Exactly one item.** Doesn't batch or wander to other bugs.
- **Stops and reports `blocked`** if: can't reproduce, too big/ambiguous, can't verify, or the fix would touch unrelated scope. Leaves status `triaged`. Does not guess.
- **Never weakens a test** to go green (no deleting/`xfail`/loosening asserts).
- Reads `FEEDBACK_API_TOKEN` + `PROD_BASE_URL` from local env; never prints/commits them.

### 3 — `/change-approval-orchestrator` skill (gate + loop)

`.claude/skills/change-approval-orchestrator/SKILL.md`. The entry point the admin runs.

Workflow: `GET` open bugs from the prod API → triage each (classify bug/idea, guess area, propose action, size S/M/L, flag risky) → present a numbered table → **get per-item approval** (all/some/none; skipped stay `open`) → for each approved, invoke `/auto-bug-fixer` with that id → final summary (fixed+pushed / skipped / blocked).

Guardrails:
- **Never fixes without explicit approval** for that specific item.
- Approves and executes **one item at a time**; a blocked item doesn't abort the rest.
- Surfaces the deploy reminder at the end (fixes are pushed, not live until the admin deploys).

## Out of scope (YAGNI)

- Session-cookie / password auth for the API (bearer token only).
- Auto-deploy, scheduled/cron runs, session-start hooks (possible later; explicitly deferred).
- A type field on `BugReport` (classification stays inferred at triage).
- Local-DB triage (production only).

## Secrets summary

| Secret | Where | In git? |
|---|---|---|
| `FEEDBACK_API_TOKEN` | Railway var + local `.env` | No (`.env.example` empty) |
| `PROD_BASE_URL` (`https://gymapp-production-1029.up.railway.app`) | local `.env` | No |
