---
name: test
description: Run the gymapp pytest suite, surface failures crisply, and (with an argument) target tests for one file/app/feature or delegate writing new tests to the test-writer subagent.
---

# /test — gymapp test workflow

A small wrapper around the project's test conventions ([docs/conventions.md], `tests/factories.py`, `pyproject.toml`) so common test workflows are one command.

Always activate the venv first: every shell call should start with `source .venv/bin/activate && ...`. The default test command is `python -m pytest -q`.

## How to invoke

| Form | What I do |
|---|---|
| `/test` | Run the full suite (`pytest -q`). Report `N passed in Xs` or list failures. |
| `/test <path-or-pattern>` | Run a subset (e.g. `tests/services/test_fatigue.py` or `tests/apps/metrics/`). Use `pytest -v` so individual test names show up. |
| `/test write <target>` | The target needs tests written. Delegate to the **`test-writer`** subagent (`Agent` tool, `subagent_type=test-writer`) with a self-contained prompt. The prompt MUST include: the file path of the code under test, the public API I want covered, the relevant model fields, existing factories I can reuse, and definitive DO / DO NOT bullets. After the subagent returns, re-run `pytest -q` to confirm green and report the new pass count. |
| `/test repair` | A run is failing. Read the first failure, identify whether the test or the code is wrong, fix the minimum needed (per CLAUDE.md §7: no scope creep), re-run, repeat until green. Don't mass-rewrite tests to make them pass — if a behavior changed legitimately, update the test to assert the new contract and say so. |

## Rules of the road

- **Never** edit a test to silence an assertion without first confirming the production code is right. Updating tests to match a deliberate behavior change is fine; updating tests to hide a regression is a hard NO.
- **Do not** add `time.sleep`, network calls, or filesystem state outside `tmp_path` to any test. (Mirrors the test-writer agent's hard rules.)
- Use `@pytest.mark.django_db` only when the test actually hits the DB. Pure-function service tests don't need it.
- After landing or modifying a service / view / model, the corresponding test file is **expected** to exist. If it doesn't, run `/test write <target>` rather than skipping.
- When delegating to `test-writer`, brief it like a colleague who just walked in: paths, public API, models, factories, and the exact behaviors to cover. Terse prompts produce shallow tests.

## When NOT to use

- For end-to-end browser checks, run Playwright directly (the project has `playwright` + WebKit installed under `.venv` and the local dev server lives at `http://127.0.0.1:8000/`). Pytest is for code-level units, not UI verification.
- For one-off REPL exploration, use `manage.py shell` directly.
