---
name: auto-bug-fixer
description: Use when fixing or implementing ONE approved item (a specific BugReport id) from the gymapp feedback inbox — usually dispatched by /change-approval-orchestrator after the admin approved that item, or invoked directly as "fix bug #N".
---

# /auto-bug-fixer — execute one approved feedback item

Executor for a **single** `BugReport`. Composes `/debug` (for bugs) or the project
working agreement (for ideas/mejoras), tracks status through the production triage
API, commits and pushes — and **never deploys** (the admin deploys manually).

Operates on ONE item. The gate (which items, whether to act) belongs to
`/change-approval-orchestrator`; this skill assumes approval already happened.

**Prereqs:** `source .venv/bin/activate`; `PROD_BASE_URL` + `FEEDBACK_API_TOKEN`
in `.env` (gitignored). Load them without printing:
`export $(grep -E '^(FEEDBACK_API_TOKEN|PROD_BASE_URL)=' .env | xargs)`.

## Steps

0. **Resolve the item.** Given an id without details, fetch it:
   `curl -s "$PROD_BASE_URL/feedback/api/bugs/" -H "Authorization: Bearer $FEEDBACK_API_TOKEN"` and find the id. Classify: **bug** (something broken) vs **mejora/idea** (new behavior).
1. **Mark `triaged`** (work starting) — POST status `triaged` (see Quick reference).
2. **Fix it:**
   - **Bug** → follow the five steps of **`/debug`** (reproduce → isolate → minimal fix → regression test → verify). **REQUIRED SUB-SKILL:** `/debug`.
   - **Mejora** → implement per the working agreement: ONE focused change, minimal scope, with tests. Use **`/test`** conventions.
3. **Green gate:** `python -m pytest -q` passes. If UI changed → `npm run build:css` then browser-verify at 390×844 (`playwright.webkit`).
4. **Commit + push:** one commit, message referencing `bug #<id>: <subject>`. Push to `main`.
5. **Mark `resolved`** — POST status `resolved`. The fix is now on `main` but **not live until the admin deploys** — say so.
6. **Report back:** `done` (commit sha + one-line what) or `blocked` (reason + what you tried).

## Quick reference (prod API)

```bash
# mark a status (triaged | resolved | open)
curl -s -X POST "$PROD_BASE_URL/feedback/api/bugs/<id>/status/" \
  -H "Authorization: Bearer $FEEDBACK_API_TOKEN" \
  -H "Content-Type: application/json" -d '{"status":"triaged"}'
```

## Red flags — STOP

- **Never deploy.** Push to `origin/main` is NOT deploying. Only the admin deploys (Railway variable nudge).
- **One item only.** Notice another bug while in here? Don't fix it — note it for the next triage round.
- **Can't reproduce / too big / ambiguous / can't verify** → STOP, leave status `triaged`, report `blocked`. Do not guess a fix.
- **Never weaken a test** to go green (`/test` hard rule). Wrong test → say so; otherwise the code is wrong.
- **Never print or commit** `FEEDBACK_API_TOKEN`.

## Rationalizations (all mean: stop and follow the step)

| Excuse | Reality |
|--------|---------|
| "Tiny fix, skip the regression test" | Untested fix = unverified fix. `/debug` step 4 is mandatory. |
| "While I'm here I'll also fix X" | Breaks the per-item approval contract. One item. Note the rest. |
| "Resolved — the push is basically deployed" | Push ≠ live. `resolved` means pushed; the admin still deploys. |
| "Can't reproduce but this probably fixes it" | Don't guess. Mark `blocked`, report what you tried. |
| "Test fails but my fix is right, I'll adjust the test" | Never weaken a test to pass. |
