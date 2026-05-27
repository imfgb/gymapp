---
name: debug
description: Systematic debugging workflow for gymapp — reproduce, isolate, minimal fix, regression test, browser-verify when UI-adjacent. Avoids the "claim fixed without checking" failure mode.
---

# /debug — gymapp debugging workflow

A discipline, not a magic command. Five steps, in order. Skipping any one is the usual reason a "fixed" bug isn't actually fixed (see memory `feedback-verify-before-deploy`).

Always activate the venv first: `source .venv/bin/activate && ...`.

## 1. Reproduce, locally and minimally

Get the failure to happen in a controlled place — preferably a pytest test, otherwise the local dev server.

- **If the user described the bug**: extract concrete inputs (user, route, click sequence, payload) and reproduce on `http://127.0.0.1:8000/` (the user's local dev server, port 8000). Credentials and seeded data live in memory `[[project-env]]`.
- **If reproducing in tests**: write the failing test FIRST (TDD style) — that test is the regression test you ship in step 4. Even a one-line `pytest.raises` or response-status assertion counts.
- **If the bug is UI/HTMX/Safari-specific**: use Playwright with WebKit (already installed under `.venv`). The user is on iPhone Safari, so chromium can give false greens — see memory `[[project-superuser-privacy]]` for an example where a multi-user bug only surfaced on WebKit + real auth.
- **Snapshot the user's local data before mutating it** if you're going to write to their DB. Example: dump `WeeklySplit` rows for `fglzb00@gmail.com` as JSON before the test, restore at the end.

## 2. Isolate the root cause

Don't fix the first thing that looks suspicious. Trace from the symptom to the cause.

- Walk the call chain: which view → which service → which model query. Print intermediate values via `manage.py shell -c "..."` if needed.
- For owner-scoping / privacy bugs, audit ALL `.objects.` usages of the model in views: `grep -rn "Model\.objects\." gymapp/apps/*/views.py | grep -v for_user` — anything that reads user data without `for_user` is suspect (memory `[[project-superuser-privacy]]`).
- For "deployed code looks old" bugs, **first verify what's actually deployed** before touching code: fetch the prod compiled CSS and grep for marker classes introduced in your commit, and probe a known-new URL (`HTTP 200 → exists; 404 → old code`). Cache > server > network — eliminate each layer before assuming a code bug.
- For HTMX/`hx-boost` weirdness, check whether the response from the boosted form actually swaps the relevant DOM nodes. `page.content()` after a click is sometimes stale because `networkidle` doesn't always fire after a boosted swap — re-`goto` the page to get a clean GET render.

## 3. Apply the minimum fix

Per CLAUDE.md §7: bug fixes do NOT include surrounding cleanups, refactors, or extra features.

- One commit per concern: privacy bug ≠ defense-in-depth ≠ docs. Keep them separable so a revert is surgical.
- Add a **WHY** comment only if the fix encodes a non-obvious constraint (e.g. "Defense in depth against legacy cross-owner FK rows"). Don't comment WHAT the code does.
- If the fix touches owner-scoping or any shared core code, scan all callers for the same pattern — bugs in shared helpers usually leak in more than one place.

## 4. Lock the fix with a regression test

The test you wrote in step 1 should now pass. If you didn't write one then, write one now. Same factories conventions as `/test` (see `[/test](.claude/skills/test/SKILL.md)`).

- The test must FAIL on the pre-fix code and PASS after. Verify with `git stash && pytest <new test> && git stash pop`.
- For privacy fixes, write the regression at view level (assert another user's data string is NOT in `response.content`) — pure model-level tests can miss leaks that come from FK traversal in templates.

## 5. Browser-verify if UI-adjacent, then commit

- For UI changes (templates, Tailwind classes, HTMX flows): screenshot the affected pages at 390×844 with `playwright.webkit` to match the user's iPhone Safari (see memory `[[project-superuser-privacy]]` for the recipe). Look at the screenshot — don't assume.
- After Tailwind class additions: `npm run build:css` BEFORE screenshotting, or the new classes won't render in dev either.
- Commit + push only when the suite is green AND (for UI) the screenshot looks right. Don't push three "fix" commits in a row hoping the next deploy will sort it out.

## Hard rules

- **Never** report a bug as fixed without one of (test passes proving it / browser screenshot showing it / user-reproducible repro). Memory `[[feedback-verify-before-deploy]]` is the why.
- **Never** weaken a test to make it green. If the test is wrong, say so explicitly; otherwise the code is wrong.
- **Never** trigger a Railway deploy yourself — only the user can (variable nudge). Pushing to `origin/main` is not deploying.
- When in doubt about a destructive action on the user's local DB (delete routines, modify split, drop session), snapshot first, ask second, mutate third.
