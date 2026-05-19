# Feature Checkpoints

Every feature passes this list before its `feature_list.json` row flips to `done`. The Reviewer copies these into `progress/review_<feature>.md` and marks each one.

## Universal

- [ ] All new model classes inherit `TimestampedModel` if they have time-tracked fields.
- [ ] All user-owned models use `OwnedMixin` (and therefore `OwnerScopedQuerySet`).
- [ ] Every view that reads user data calls `.for_user(request.user)`.
- [ ] No `raw()` / `extra()` / string SQL.
- [ ] No use of `|safe`, `mark_safe`, or `format_html` with untrusted input.
- [ ] Migrations generated for every model change; `python manage.py makemigrations --check` is clean.
- [ ] `ruff check .` and `ruff format --check .` both pass.
- [ ] `python manage.py check` passes (and `check --deploy` for prod-touching work).
- [ ] `pytest` passes locally.
- [ ] New service-layer code exposes a `Strategy` Protocol and a `Deterministic*` impl.
- [ ] No secrets, no hardcoded URLs, no print-statement debugging left behind.
- [ ] Docs updated: `DATABASE.md` on schema change, `API_DESIGN.md` on endpoint change, `DECISIONS.md` on architectural change.

## UI-specific

- [ ] Mobile-first responsive: no horizontal scroll at 360px width.
- [ ] HTMX POST/PUT/DELETE includes the CSRF token (via the meta-tag wiring in `base.html`).
- [ ] Forms have proper labels and `autocomplete` hints.

## Data-migration-specific

- [ ] Idempotent: re-running on top of itself is a no-op.
- [ ] Reversible OR explicitly marked `reversible = False` with a justifying comment.
