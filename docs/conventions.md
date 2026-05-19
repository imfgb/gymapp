# Conventions

Read this before touching code. Most rules are enforced by `ruff` or the Reviewer agent's checklist; the rest is for human reviewers.

## Python

- **Style**: `ruff format` (PEP 8, double quotes, 100-char line, sorted imports).
- **Type hints** on every function signature. Use modern syntax: `list[str]`, `str | None`, `Iterable[...]`.
- **Imports**: stdlib → third-party → first-party, sorted by `ruff` (`I` rules). No wildcard imports outside settings.
- **Docstrings**: only when the *why* isn't obvious. Don't restate the *what*.
- **No comments narrating the diff** ("removed X", "added Y", "for the new feature"). Comments answer *why* a non-obvious thing is the way it is.
- **f-strings** for interpolation. No `.format()` or `%` formatting unless logging.
- **Dataclasses or Pydantic** for inert data containers — Pydantic only if a class crosses a serialization boundary.

## Django

- **Apps live under** `gymapp/apps/<name>/`, with an explicit `AppConfig` named `<Name>Config` and `label = "<name>"`.
- **Custom User**: `settings.AUTH_USER_MODEL` always; never the literal `"users.User"`.
- **Owner-scoping**: every user-owned model uses `OwnedMixin` (from `gymapp.apps.core.models`). Every view that reads user data calls `Model.objects.for_user(request.user)`.
- **Cross-app reads**: through a service in `gymapp/services/<area>/`, not by importing another app's models in your view.
- **Migrations**: one per logical schema change. Hand-edit only to add `db_index`, `RunPython` directions, or comments. Never edit a migration after merge to `main`.
- **No raw SQL** (`raw()`, `extra()`, string queries). Use the ORM.
- **Templates**: auto-escape on (default). No `|safe` / `mark_safe` / `format_html` on untrusted input.

## URLs & templates

- **URL names** are `app:view` (e.g. `routines:weekly_split`). Reverse via `{% url %}`.
- **URLs in Spanish where user-visible** (`/rutinas/`, `/entrenamientos/`) is fine, but app names + view names stay in English (`routines`, `weekly_split`).
- **Templates** extend `base.html` for full pages; live in `templates/partials/` for HTMX fragments.
- **CSRF**: `{% csrf_token %}` in every form (HTMX or not). The meta-tag wiring in `base.html` handles `hx-post`/`hx-put`/`hx-delete`.
- **Tailwind**: utility-first. No custom CSS files unless really needed; if so, isolated under `static/src/`.

## JavaScript

- **HTMX** for partial swaps.
- **Alpine.js** for tiny client-side state (a few lines of `x-data`).
- **No bundler**, no npm install in dev, no TypeScript. If you reach for those, push back and discuss first.

## Services

- One subpackage per area under `gymapp/services/`.
- **Each service exposes a `Strategy` Protocol and a `Deterministic*` implementation.** Even if you're not adding an LLM variant today, the seam is mandatory — see `docs/service_layer.md`.
- **Facade** (`gymapp/services/coaching/__init__.py`) re-exports ready-to-use instances so views import one name.

## Tests

- **`pytest` + `pytest-django` + `factory-boy`.**
- **`@pytest.mark.django_db`** only where DB access is needed. Pure service tests don't need it.
- **One observable behavior per test.** No "test the whole world".
- **Factories** in `tests/factories.py`. Per-test data in the test body, not in fixtures (unless cross-test setup).
- **No network**, no filesystem outside `tmp_path`, no `time.sleep`.

## Naming

- `snake_case` for Python identifiers, JSON/YAML keys, and template variables.
- `PascalCase` for classes (including models, factories, views-as-classes).
- `UPPER_SNAKE` for constants and Django settings.
- `kebab-case` for URLs, CSS class names, slugs.
- **Spanish for user-visible strings**; English for identifiers, slugs, exercise names, muscle groups, equipment names. Never mix in the same string.

## Commits

- Conventional commits are not required. Keep messages short and accurate: *"add Exercise model + seed loader"*, *"fix owner scoping in routines list view"*.
- One logical change per commit. The Reviewer agent's "scope creep" check applies here too.

## Code review smells (flag immediately)

- `raw()`, `extra()`, `.execute(`
- `|safe`, `mark_safe`, `format_html`
- A view that doesn't call `.for_user(...)` while reading user data
- A new model that skips `OwnedMixin` or `TimestampedModel`
- New deps without a corresponding `requirements.txt` pin
- Hardcoded URLs (use `reverse` / `{% url %}`)
- Hardcoded secrets (.env / settings only)
