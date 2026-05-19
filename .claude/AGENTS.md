# Agents Roster & Rules (Build-Time Harness)

Adapted from `betta-tech/ejemplo-harness-subagentes`. This file is **progressive disclosure**: rules surface to whichever agent is acting now, not in one wall of text at the top of every session.

## Roles

| Agent | Reads | Writes | Code? |
|---|---|---|---|
| **leader** | `feature_list.json`, `CHECKPOINTS.md`, `progress/*.md` | `feature_list.json` (status only), spawns subagents | **No** |
| **implementer** | spec, `docs/conventions.md`, current code | code, tests, `progress/impl_<feature>.md` | **Yes** |
| **reviewer** | `progress/impl_<feature>.md`, the diff | `progress/review_<feature>.md`, may push fixes to implementer | **No edits to feature code** |
| **migration-writer** | model changes spec | the migration file + a unit test that round-trips it | **Yes (migrations only)** |
| **test-writer** | feature spec | `tests/...` files + `progress/impl_<feature>.md` updates | **Yes (tests only)** |

## Invariants enforced by `init.sh`

1. Exactly one feature may be `in_progress` in `feature_list.json` at a time.
2. `.env` exists locally; required keys present.
3. Python 3.12 is active.

## Anti-telephone rule

Subagents return **a path** (`progress/impl_<feature>.md`), not a paraphrased summary. The Leader reads that file. The Reviewer reads that file plus the diff. Information does not pass through a chain of summaries.

## Single-feature flow

```
queued ─► (leader claims) ─► in_progress ─► (implementer writes) ─► (reviewer validates) ─► done
                                            │
                                            └► (reviewer rejects) ─► back to in_progress
```

## What goes in `progress/`

- `impl_<feature>.md`: what was changed, where, why, how it was verified, follow-ups discovered.
- `review_<feature>.md`: verdict + checkpoints with pass/fail, blocking issues, advisory notes.

Both are gitignored — they're per-session working memory, not project history. Project history lives in commits + `DECISIONS.md`.
