# API Design (HTMX endpoint catalogue)

The app has **no JSON API** for external consumption — it's a server-rendered Django app with HTMX partial-page swaps for interactivity. This file is the canonical list of every URL: what it returns, whether it's full-page or fragment, and what method/auth it expects.

Updated as endpoints land per phase.

## Conventions

- **Method**: GET unless noted.
- **Auth**: all routes require login except `/auth/login/`, `/auth/password/reset/` (Phase 2+ if added), and static assets.
- **CSRF**: required on every non-GET. HTMX automatically sends the token via the meta-tag wiring in `base.html`.
- **Response shape**:
  - `full` → returns a full HTML page (extends `base.html`).
  - `partial` → returns an HTML fragment, intended for `hx-target=` swap.
- **URL naming**: `{app}:{view}`. Reverse with `{% url 'app:view' %}`.

---

## Phase 0 (current)

| URL | Name | Method | Auth | Returns | Description |
|---|---|---|---|---|---|
| `/` | `dashboard:home` | GET | yes | full | Placeholder landing — three "próximamente" cards. |
| `/auth/login/` | `login` | GET, POST | no | full | Django built-in `LoginView`, custom template `auth/login.html`. |
| `/auth/logout/` | `logout` | POST | yes | redirect | Django built-in `LogoutView`. |
| `/auth/password/change/` | `password_change` | GET, POST | yes | full | Self-serve password change. |
| `/auth/password/change/done/` | `password_change_done` | GET | yes | full | Confirmation page. |
| `/admin/` | n/a | GET, POST | staff | full | Django admin (User CRUD, Profile editing, future model management). |
| `/static/*` | n/a | GET | no | static | Whitenoise-served assets (compiled Tailwind in prod). |

---

## Phase 1 (planned)

### routines

| URL | Name | Method | Returns | Description |
|---|---|---|---|---|
| `/routines/` | `routines:list` | GET | full | List the user's routines. |
| `/routines/new/` | `routines:create` | GET, POST | full | New routine form. |
| `/routines/<id>/` | `routines:detail` | GET | full | Routine detail with days/exercises. |
| `/routines/<id>/edit/` | `routines:edit` | GET, POST | full | Edit routine metadata. |
| `/routines/<id>/days/<day_id>/exercises/add/` | `routines:add_exercise` | GET, POST | partial | HTMX: append a `RoutineExercise` row. |
| `/routines/<id>/days/<day_id>/exercises/<rex_id>/delete/` | `routines:delete_exercise` | POST | partial | HTMX: remove the row. |
| `/split/` | `routines:weekly_split` | GET | full | The user's weekly split (Mon..Sun → RoutineDay). |
| `/split/<weekday>/assign/` | `routines:split_assign` | POST | partial | HTMX: assign or clear a routine day for a weekday. |

### workouts

| URL | Name | Method | Returns | Description |
|---|---|---|---|---|
| `/workouts/start/` | `workouts:start` | POST | redirect | Create a `WorkoutSession` from today's `WeeklySplit` row (or ad-hoc). |
| `/workouts/<id>/` | `workouts:session` | GET | full | Active session view with the interactive checklist. |
| `/workouts/<id>/sets/<set_id>/complete/` | `workouts:complete_set` | POST | partial | HTMX: tap-to-complete; sets `completed_at`, returns the row marked done + the rest-timer fragment. |
| `/workouts/<id>/sets/<set_id>/update/` | `workouts:update_set` | POST | partial | HTMX: edit weight/reps before completing. |
| `/workouts/<id>/exercises/<elog_id>/swap/` | `workouts:swap_exercise` | GET, POST | partial | HTMX: list alternatives (from `substitution` service) and pick one. |
| `/workouts/<id>/finish/` | `workouts:finish` | POST | redirect | Set `status=finished, finished_at=now`; trigger PR detection service. |
| `/workouts/` | `workouts:history` | GET | full | Recent sessions. |

### prs

| URL | Name | Method | Returns | Description |
|---|---|---|---|---|
| `/prs/` | `prs:list` | GET | full | All PRs per exercise. |
| `/prs/<exercise_slug>/` | `prs:detail` | GET | full | PR history for one exercise. |
| `/prs/<id>/edit/` | `prs:edit` | GET, POST | full | Manual override of an auto-detected PR. |

### metrics

| URL | Name | Method | Returns | Description |
|---|---|---|---|---|
| `/metrics/` | `metrics:list` | GET | full | Body weight + body fat trend. |
| `/metrics/new/` | `metrics:create` | GET, POST | full | Add a new snapshot. |

### dashboard (richer)

| URL | Name | Method | Returns | Description |
|---|---|---|---|---|
| `/` | `dashboard:home` | GET | full | Today's workout + this-week split + recent PRs (replaces Phase 0 placeholder). |

---

## Phase 2+ endpoints

Filled in as the relevant phase lands. Programming will likely add:

- `/coaching/recommendations/<session_id>/` — fragment with per-exercise progression hints.
- `/split/reconstruct/` — recompute the upcoming week when sessions were missed.

Nutrition (Phase 3) adds:

- `/nutrition/` — daily macro target.
- `/nutrition/meal/<slot>/` — meal slot preferences.

AI (Phase 4) does not add new URLs by default — services swap strategies internally.
