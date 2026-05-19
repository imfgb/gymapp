# Database

Schema documentation by app. Updated alongside each model migration.

## Conventions

- **All PKs** are `BigAutoField` (set as `DEFAULT_AUTO_FIELD`).
- **User-owned models** subclass `OwnedMixin` from `core.models` (gives an `owner` FK to `AUTH_USER_MODEL`).
- **Time-tracked models** subclass `TimestampedModel` from `core.models`.
- **FKs to users**: always `settings.AUTH_USER_MODEL`, never the literal string `"users.User"`.
- **Indexes**: `db_index=True` on FKs that drive list queries and on date fields that drive ordering. Documented per model below.
- **Weight**: `kg` everywhere. `DecimalField(max_digits=5, decimal_places=2)` (supports up to 999.99kg, two decimals).
- **Heights / lengths**: `cm`, integers (`PositiveSmallIntegerField`).
- **Times**: stored UTC, displayed `America/Mexico_City`.

---

## users

### `User`
Custom user, email as the unique identifier (no `username`).

| Field | Type | Notes |
|---|---|---|
| `id` | BigAutoField | PK |
| `email` | EmailField | unique |
| `password` | CharField(128) | hashed |
| `is_active`, `is_staff`, `is_superuser` | Boolean | from `PermissionsMixin`/`AbstractUser` |
| `first_name`, `last_name` | CharField(150) | blank-allowed |
| `last_login` | DateTime | nullable |
| `date_joined` | DateTime | default `now` |

`USERNAME_FIELD = "email"`, `REQUIRED_FIELDS = []`. Auth via `users.managers.UserManager`.

### `Profile`
One-to-one with `User`, auto-created on first save.

| Field | Type | Notes |
|---|---|---|
| `user` | OneToOneField(User) | reverse: `user.profile` |
| `height_cm` | PositiveSmallIntegerField | nullable |
| `date_of_birth` | DateField | nullable |
| `training_style` | CharField(20) choices | bodybuilding / powerlifting / powerbuilding |
| `training_goal` | CharField(20) choices | hypertrophy / strength / recomposition / cut / bulk / maintain |
| `default_rest_seconds` | PositiveSmallIntegerField | default 120 |
| `must_change_password` | Boolean | true on admin-created accounts |
| `created_at`, `updated_at` | DateTime | |

Indexes: none beyond the OneToOne unique constraint.

---

## exercises *(Phase 1)*

Planned. Schema lands with the `exercises` migration.

### `MuscleGroup`
Global lookup. Seeded from `seeds/exercises.yaml`.

| Field | Type | Notes |
|---|---|---|
| `slug` | SlugField | unique, e.g. `chest`, `lats`, `delts-front` |
| `name` | CharField | display, English |
| `region` | CharField choices | chest / back / shoulders / arms / legs / core |

### `Equipment`
Global lookup.

| Field | Type | Notes |
|---|---|---|
| `slug` | SlugField | unique |
| `name` | CharField | display, English |

### `Exercise`
Either global (owner is null) or per-user (owner = a `User`).

| Field | Type | Notes |
|---|---|---|
| `slug` | SlugField | unique (consider per-owner uniqueness) |
| `name` | CharField | English |
| `equipment` | FK Equipment | indexed |
| `primary_muscles` | M2M MuscleGroup | related: `primary_for` |
| `secondary_muscles` | M2M MuscleGroup | related: `secondary_for` |
| `category` | CharField choices | compound / isolation |
| `unilateral` | Boolean | |
| `owner` | FK User nullable | null = global |
| `is_active` | Boolean | soft-delete flag |
| `created_at`, `updated_at` | DateTime | |

Indexes: `(owner, slug)` unique; `equipment`.

### `ExerciseAlternative`
Through-model for self-referencing M2M on `Exercise`.

| Field | Type | Notes |
|---|---|---|
| `from_exercise` | FK Exercise | related: `alternatives_from` |
| `to_exercise` | FK Exercise | related: `alternatives_to` |
| `reason` | CharField(200) | human-readable rationale |

Indexes: `(from_exercise, to_exercise)` unique.

---

## routines *(Phase 1)*

### `Routine`
| Field | Type | Notes |
|---|---|---|
| `owner` | FK User | from `OwnedMixin` |
| `name` | CharField | |
| `training_style` | CharField choices | snapshot at creation; updates don't backfill |
| `notes` | TextField | blank-allowed |
| `is_archived` | Boolean | |

### `RoutineDay`
| Field | Type | Notes |
|---|---|---|
| `routine` | FK Routine | |
| `label` | CharField | e.g. "Push A" |
| `ordering` | PositiveSmallIntegerField | within the routine |

### `RoutineExercise`
| Field | Type | Notes |
|---|---|---|
| `routine_day` | FK RoutineDay | |
| `exercise` | FK Exercise | |
| `ordering` | PositiveSmallIntegerField | |
| `target_sets` | PositiveSmallIntegerField | |
| `target_reps_low` | PositiveSmallIntegerField | |
| `target_reps_high` | PositiveSmallIntegerField | |
| `target_weight_kg` | Decimal(5,2) | nullable |
| `rest_seconds` | PositiveSmallIntegerField | falls back to `Profile.default_rest_seconds` |
| `notes` | TextField | blank-allowed |

### `WeeklySplit`
One row per (owner, weekday). Weekday integer follows ISO (1=Mon..7=Sun) or Python (`weekday()` 0=Mon..6=Sun) — decide and stay consistent.

| Field | Type | Notes |
|---|---|---|
| `owner` | FK User | |
| `weekday` | PositiveSmallIntegerField | |
| `routine_day` | FK RoutineDay | nullable (rest day) |

Indexes: `(owner, weekday)` unique.

---

## workouts *(Phase 1)*

### `WorkoutSession`
| Field | Type | Notes |
|---|---|---|
| `owner` | FK User | |
| `started_at` | DateTime | indexed |
| `finished_at` | DateTime | nullable |
| `status` | CharField choices | in_progress / finished / abandoned |
| `source_routine_day` | FK RoutineDay | nullable (ad-hoc sessions allowed) |
| `notes` | TextField | blank-allowed |

### `ExerciseLog`
| Field | Type | Notes |
|---|---|---|
| `session` | FK WorkoutSession | |
| `exercise` | FK Exercise | |
| `ordering` | PositiveSmallIntegerField | |

### `SetLog`
The unit of work. `completed_at` powers the tap-to-complete checklist.

| Field | Type | Notes |
|---|---|---|
| `exercise_log` | FK ExerciseLog | indexed |
| `ordering` | PositiveSmallIntegerField | |
| `weight_kg` | Decimal(5,2) | nullable until completion |
| `reps` | PositiveSmallIntegerField | nullable until completion |
| `rpe` | Decimal(3,1) | nullable (5.0–10.0) |
| `is_warmup` | Boolean | |
| `completed_at` | DateTime | nullable; null = not yet done |

---

## prs *(Phase 1)*

### `PersonalRecord`
| Field | Type | Notes |
|---|---|---|
| `owner` | FK User | |
| `exercise` | FK Exercise | |
| `weight_kg` | Decimal(5,2) | |
| `reps` | PositiveSmallIntegerField | |
| `achieved_at` | DateTime | indexed |
| `source` | CharField choices | auto / manual |
| `source_set` | FK SetLog | nullable; set when `source=auto` |

Indexes: `(owner, exercise, reps)` unique (only one PR per rep-count).

---

## metrics *(Phase 1)*

### `UserMetricSnapshot`
| Field | Type | Notes |
|---|---|---|
| `owner` | FK User | |
| `measured_at` | DateTime | indexed |
| `weight_kg` | Decimal(5,2) | |
| `body_fat_pct` | Decimal(4,2) | nullable |
| `notes` | TextField | blank-allowed |

### `MonthlyGoal` *(Phase 2)*
TBD.

---

## ER diagram

A high-level diagram lives in the plan; reproduce here once Phase 1 lands. Until then, the planned-entities docstrings in each app's `models.py` are the contract.
