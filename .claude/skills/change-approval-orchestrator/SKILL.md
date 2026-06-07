---
name: change-approval-orchestrator
description: Use when the gymapp admin wants to review and act on the feedback inbox — the user-reported bugs and improvement ideas submitted in the app. Reads the open reports from production and works through them only with the admin's per-item approval.
---

# /change-approval-orchestrator — triage the feedback inbox, gated by approval

Entry point for working through user feedback. Reads open `BugReport`s **from
production**, triages them, gets the admin's approval **per item**, and dispatches
each approved one to **`/auto-bug-fixer`**. The admin stays in control: nothing is
fixed without an explicit yes for that specific item.

**Prereqs:** `source .venv/bin/activate`; `PROD_BASE_URL` + `FEEDBACK_API_TOKEN`
in `.env` (gitignored). Load without printing:
`export $(grep -E '^(FEEDBACK_API_TOKEN|PROD_BASE_URL)=' .env | xargs)`.

## Steps

1. **Read the inbox** — open reports from prod:
   ```bash
   curl -s "$PROD_BASE_URL/feedback/api/bugs/?status=open" \
     -H "Authorization: Bearer $FEEDBACK_API_TOKEN"
   ```
   None open → say so and stop.
2. **Triage each** into a row: `#id · subject · type (bug|idea) · área · acción propuesta · tamaño (S/M/L) · riesgo`. Classify type from the text (the model has no type field). Flag anything risky/ambiguous/large.
3. **Present the numbered table** and **ask which to approve** — the admin replies `todos` / a subset (`1,3,4`) / `ninguno`. Items not approved stay `open` (untouched).
4. **Execute approved items one at a time:** for each, follow **`/auto-bug-fixer`** with that id. A `blocked` item does **not** abort the rest — continue to the next.
5. **Summary:** per item, `resuelto+push` / `bloqueado (motivo)` / `saltado`. End with the **deploy reminder**: fixes are on `main` but not live until the admin deploys (Railway variable nudge).

## Red flags — STOP

- **Never fix an item without explicit approval for that item.** "Obvious" or "trivial" is not approval.
- **Never deploy.** That is always the admin's manual step. (`/auto-bug-fixer` only pushes.)
- **Don't batch-approve in the admin's voice.** If the reply is ambiguous, ask again — don't assume `todos`.
- **One item at a time** through `/auto-bug-fixer`; don't parallel-edit the working tree.

## Rationalizations (all mean: stop and get real approval)

| Excuse | Reality |
|--------|---------|
| "These are all small, I'll just do them" | Per-item approval is the whole point of this skill. Ask. |
| "The admin said yes to bug #1, so #2 is fine too" | Approval is per item. #2 needs its own yes. |
| "I'll fix and push, the admin can revert if they dislike it" | No. Approval precedes the work, not the revert. |
| "Inbox is empty locally" | This skill reads **production**, never local. Check `PROD_BASE_URL` is set. |
