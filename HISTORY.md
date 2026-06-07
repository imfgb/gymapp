# HISTORY.md — gymapp implementation log

Detailed, dated record of what was built and why. `CLAUDE.md` keeps only the
current state; this file is the append-only history behind it. Newest phase
summaries first, then the full per-feature changelog.

---

## Status snapshot (2026-05-28)

Roadmap phases **1, 2, 3, 5 complete; Phase 4 (AI) intentionally skipped** (no
budget — see memory `feedback-no-spend`). The deterministic app is
feature-complete and live on Railway. Post-roadmap work added: fatigue/readiness,
rehab/prevention (injuries + mobility), nutrition meals/portions/supplements,
onboarding wizard, body-comp charts, in-app bug reporting (`feedback` app), and
per-page hint banners (`core.context_processors.page_hint`).

Recent hardening: removed a `for_user` superuser bypass (privacy), fixed two
UTC-vs-local `.date()` bugs (fatigue + body-comp chart), rejected negative numeric
form input, fixed a leaked multi-line `{# #}` comment, cleaned all ruff lint.

**Test suite: 377 passing; `ruff check .` clean (2026-05-28).** Coverage: workout
service + views (incl. negative-input rejection), progression service (unit + DB
integration), exercise library, PR service, routine generator + weekly-split
assignment, substitution, warmup, monthly goals, nutrition (BMR/TDEE/macros +
meals + portions + daily-reset + supplements), analytics (weekly volume +
sets-per-muscle + deload + body-comp series incl. TZ-correctness), fatigue/readiness
service + recovery views, injuries (rehab service + CRUD views + owner scoping),
block-programming, dashboard (skip-day slide-forward + archived-routine filtering),
routines, metrics (incl. body-comp + edit), feedback (bug report + superuser triage),
per-page hints, owner-scoping regression suite, onboarding, smoke.

---

## Phase 0 — Scaffold: complete

- Repo skeleton created, all config files in place.
- Custom `User` model with `users.0001_initial` migration landed.
- Owner-scoped manager + admin available in `core`.
- All other domain apps exist as empty shells with planned-entity docstrings in their `models.py`.
- Service layer has Protocols + `Deterministic*` stubs (Phase 1 fills behavior).
- Dashboard placeholder renders at `/`.
- Login at `/auth/login/`, admin at `/admin/`.
- Tailwind via Play CDN in dev; PostCSS pipeline ready for prod build.
- Sentry integration wired but disabled until `SENTRY_DSN` is set.
- CI lints + tests on push.
- `.claude/` harness with Leader/Implementer/Reviewer + Migration Writer + Test Writer agents.

---

## Phase 1 — Tracking MVP: complete

All six Phase 1 features in `.claude/feature_list.json` are `done`. The MVP loop
works end-to-end: build a routine, schedule it on weekdays, start today's workout
from the dashboard, tap-complete sets with the rest timer, finish the session, and
see PRs auto-detected.

- **exercises**: `MuscleGroup`, `Equipment`, `Exercise` (nullable owner, `visible_to(user)`), `ExerciseAlternative` (directional, auto-mirrored). 78 curated exercises seeded across 17 muscle groups / 7 equipment types via idempotent loader + data migration. `DeterministicSubstitution` backs onto the real graph.
- **routines**: `Routine`, `RoutineDay`, `RoutineExercise`, `WeeklySplit`. Owner-scoped. CHECK constraint on `target_reps_low <= target_reps_high`. UNIQUE `(owner, weekday)` on splits.
- **workouts**: `WorkoutSession`, `ExerciseLog`, `SetLog`. Service-layer orchestration (`start_session`, `complete_set`, `update_set_values`, `swap_exercise`, `finish_session`, `session_progress`). HTMX tap-to-complete checklist + Alpine.js sticky rest timer. Owner-scoped at every entry point.
- **prs**: `PersonalRecord` with `(owner, exercise, reps)` unique. `update_prs_from_session` runs on `finish_session` — keeps the heaviest weight per rep count. Manual create/edit/delete views.
- **metrics**: `UserMetricSnapshot` (weight + optional body-fat) + self-serve `/metrics/profile/` editor for Profile baseline (height, DOB, training style, training goal, default rest seconds).
- **dashboard**: Real home page — today's planned routine day (or in-progress session), this week's split, recent sessions, recent PRs, latest body metric.

### Bug fixes (2026-05-21)

1. **Set numbering**: `delete_set` renumbers sibling `SetLog.ordering` to stay contiguous. Previously deleting set #2 of 3 caused "1., 3., 3., 4." on next add.
2. **Duplicate sessions**: `start` view redirects to existing `IN_PROGRESS` session instead of creating a second one. History page shows "Reanudar" banner.
3. **Template bugs**: multiline Django `{# #}` comments render as visible text — removed. Alpine v3 event handler fixed. Two-step finish confirmation added.
4. **Exercise picker in routines**: `_render_day_card()` now includes `picker_exercises` queryset.
5. **Routine create auto-preview**: hidden declarative HTMX button avoids `hx-boost` interference.

---

## Phase 2 — Programming: complete (2026-05-22)

Both exit criteria met: recommended weight×reps on every working set (progression),
and "swap exercise returns ranked alternatives" (substitution-scoring).

Features landed (2026-05-21):

- **session-live-edit**: add/delete exercises and sets mid-workout; add custom exercises; HTMX endpoints.
- **routine-crud**: full user-facing list/create/edit/delete for routines, days, and exercises. Exercise picker with search (240 exercises).
- **routine-generator**: pick split preset + training style → service generates RoutineDays + RoutineExercises with correct rep schemes. HTMX live preview on create form.
- **progression-service**: `DeterministicLinearProgression` (powerlifting) + `DeterministicDoubleProgression` (bodybuilding/powerbuilding). `recommend_next()` wired into `start_session` — every working set pre-filled with weight × reps from last finished session. Increment: +5 kg/+2.5 kg compound/isolation (powerlifting); +2.5 kg/+1.25 kg (others).

### Landed 2026-05-22 (UX + branding, beyond the original feature list)

- **Smart Fit rebrand**: app branded "Smart Fit Altama"; yellow (`brand`=#F5E000) on near-black (`ink`) palette defined in `tailwind.config.js`; primary buttons `bg-brand text-ink`. Run `npm run build:css` after Tailwind class/config changes.
- **Decimal localization fix**: `FORMAT_MODULE_PATH=["config.formats"]` (+ `config/formats/es{,_MX}/formats.py`) forces a period decimal separator app-wide. es-MX was rendering commas, which also blanked `<input type="number">` values.
- **Rest timer**: green "¡Dale a la serie!" ready banner; `endsAt` persisted in `localStorage` so it survives reload/screen-lock; best-effort Web Notification opt-in (foreground only — no PWA, consistent with decision #3).
- **"Hoy no iré al gym"**: `SkippedDay` model (migration `routines.0002`) + `routines:skip_today` toggle; dashboard `build_week_view()` slides the week's workouts forward past skipped days.
- **Dashboard**: ignores archived routines in the schedule; routine picker to start ANY active routine (`set_today_split` also reschedules today's `WeeklySplit`); live working-set progress counter (DOM + `htmx:after-settle`, no reload); finishing redirects to home with a "¡Ya cumpliste hoy!" message + persistent `done_today` state.
- **Custom exercise from the routine editor**: "Crear nuevo" tab → `routines:exercise_add_custom`; shared creator `services.exercise_library.create_custom_exercise`.
- **Bug fixes**: reps forced integer (client strip + server coerce); set-delete was blocked by the Django Debug Toolbar's expanded panel covering right-aligned buttons (fixed with `DEBUG_TOOLBAR_CONFIG={"SHOW_COLLAPSED": True}`); fixed multi-line `{# #}` comments leaking as visible text (now guarded by tests).
- **substitution-scoring**: deterministic multi-factor scorer in `services/substitution` (primary/secondary muscle Jaccard overlap, curated-graph bonus, equipment match/availability, category). `ranked_alternatives()` powers a "Cambiar" swap UI on the session exercise card → ranked list → swap (refuses once a set is completed).
- **warmup-generation**: `services/warmup.warmup_scheme()` ramps 40/60/80% of the working weight, snapped to **loadable** weights per equipment (barbell/smith → 5 kg steps @ 20 kg bar; ez-bar → 5 kg @ 10 kg; else 2.5 kg), never ≥ working. Auto-generated on session start for barbell/smith lifts with a known weight (`AUTO_WARMUP_EQUIPMENT`); per-exercise "Calentamiento" button (`workouts:add_warmups`, idempotent regen) for the rest. Warm-ups excluded from the progress counter and PRs.
- **monthly-goals**: `metrics.MonthlyGoal` (one row per `owner` + `year` + `month`; unique constraint + month-range CHECK; nullable `target_sessions` / `target_volume_kg` / `target_bodyweight_kg`, migration `metrics.0002`). `gymapp.services.goals.monthly_goal_progress(goal)` returns `GoalMetric` rows: sessions = count of FINISHED sessions started in the month; volume = `Sum(weight_kg * reps)` over completed, non-warm-up working sets; bodyweight = baseline-relative progress (baseline = latest snapshot before the month), `reached` within ±0.5 kg. Editor at `metrics:goals`. Dashboard "Metas del mes" card + nav "Metas" link.

---

## Phase 3 — Nutrition: complete (2026-05-23)

Exit criterion met: the Nutrition page shows today's calorie + macro target plus
meal slots respecting food preferences.

- **nutrition-targets**: `users.Profile` gained `sex` (`Sex` choices, blank-default) + `activity_level` (`ActivityLevel` choices, default moderate); migration `users.0002`. `gymapp/services/nutrition` is a real `DeterministicNutrition`: Mifflin-St Jeor BMR → TDEE (`ACTIVITY_FACTORS` 1.2–1.9) → goal calorie multiplier (`GOAL_CALORIE_MULTIPLIER`: cut 0.80, bulk/hypertrophy 1.10, strength 1.05, recomp/maintain 1.00) → macro split (protein 2.0 g/kg, **2.2 on a cut**; fat 0.8 g/kg; carbs fill remaining kcal, clamped ≥ 0). `daily_target_for_user(user)` pulls bodyweight from the latest `UserMetricSnapshot` + height/DOB/sex from `Profile`, returning `(MacroTarget | None, missing_fields)`. New `gymapp.apps.nutrition` app mounts `/nutrition/`. Profile editor (`metrics:profile`) extended with sex + activity selects. The `recommend()` Protocol is the Phase 4 AI seam.
- **food-preferences**: `users.Profile.food_preferences` (`JSONField(default=list)`, migration `users.0003`) stores a flat list of liked-food slugs. `FOOD_CATALOG` (constant in `services/nutrition`) groups protein/carb/vegetable/fat with English slug + Spanish label. Helpers: `grouped_catalog(selected)`, `clean_food_preferences(slugs)`, `food_label`, `all_food_slugs`. Editor at `nutrition:preferences`.
- **meal-slots**: `services.nutrition.build_meal_plan(target, preferences)` → 4 `MealSlot`s. `MEAL_SLOTS` splits the daily target (breakfast 25% / lunch 35% / dinner 30% / snack 10%); `SLOT_COMPONENTS` says which food categories each slot suggests; foods rotated through liked items per category by slot index.

---

## Phase 4 — AI integration: SKIPPED (user decision, 2026-05-23)

The user will not pay for anything, and Phase 4 as scoped needs a paid Claude API.
The deterministic app is the finished product; the `recommend()` Protocol seam stays
available if a free/local model is ever wired in. See memory `feedback-no-spend`.

---

## Phase 5 — Polish: complete (2026-05-23)

Exit criterion met: the dashboard surfaces the current block plan, a deload
recommendation when warranted, and weekly volume trends (via `/progreso/`).

- **analytics-volume**: `weekly_volume(user, weeks=8)` → per-week tonnage (Σ weight×reps) + working-set count, Monday-anchored and zero-filled; `sets_by_muscle(user)` → this week's hard sets + volume per **primary** muscle group (warm-ups + incomplete sets excluded). Read-only view `dashboard:progress` (`/progreso/`) renders an 8-week tonnage trend + sets-per-muscle bars; nav "Progreso" link.
- **deload-suggestions**: `services.analytics.deload_recommendation(user)` → `DeloadAdvice`. Counts the trailing run of consecutive completed training weeks (current partial week ignored), stopping at any week whose tonnage ≤ `LIGHT_WEEK_RATIO` (0.6) of the run **median**. Recommends a deload once the count reaches `ACCUMULATION_WEEKS` (5). Status card on `/progreso/` + conditional amber alert on the dashboard home.
- **block-programming**: `routines.TrainingBlock` (owner, `training_style`, `started_on`, `length_weeks`; migration `routines.0003`). `services/coaching/blocks.py` holds deterministic 6-week templates per style (`BLOCK_TEMPLATES`: bodybuilding / powerlifting / powerbuilding, week 6 = deload); `block_status(style, started_on, today)` derives the current week from the calendar. View `routines:block` (`/routines/bloque/`); dashboard "Tu bloque" card. (Gotcha: a template context var named `block` collides with `{% block %}` — used `training_block`.)

---

## Post-roadmap enhancements (all deterministic / free)

- **bug-triage automation** (2026-06-07): a token-authenticated JSON API in `feedback` (`GET /feedback/api/bugs/`, `POST /feedback/api/bugs/<id>/status/`; bearer `FEEDBACK_API_TOKEN`, `hmac.compare_digest`, 503 when unset / 401 on mismatch, `@csrf_exempt` per ADR-026) + two project skills over it: `/change-approval-orchestrator` (reads open reports from **production**, triages, gets per-item approval) and `/auto-bug-fixer` (executes ONE approved item via `/debug` or the working agreement, commit+push, never deploy, marks status triaged→resolved via the API). Targets prod only (local SQLite is irrelevant for this). Design spec: `docs/superpowers/specs/2026-06-07-bug-triage-automation-design.md`. 11 API tests; suite 388 green. Setup: `FEEDBACK_API_TOKEN` on Railway + local `.env` (same value), `PROD_BASE_URL` in `.env`.

- **nutrition-meals-plus** (2026-05-23): curated `FOOD_CATALOG` + `FOOD_MACROS` (protein/carbs/fat per 100 g). Meals built from `MEAL_TEMPLATES` — fixed *coherent* food combos each tagged with the slots it fits and a per-ingredient role (protein/carb/fat sized to that macro; veg fixed serving). Replaced the old "one random food per macro category" approach (which produced nonsense like steak + peanut butter). `eligible_templates(slot, prefs)` keeps templates whose protein/carb/fat foods the user likes. `_scale_template` sizes each ingredient in raw grams to the slot's macro share and sums real per-food macros. `build_meal_plan` = deterministic pick per slot; `generate_meal` = random eligible pick → `GeneratedMeal(items, totals)`. `nutrition.SavedMeal` stores items + totals + `eaten_at`. Views: `generate_meal`, `meal_done`, `meal_delete`. Page shows the user's generated meals ("Mis comidas"), ordered by slot.

- **nutrition-daily-reset + supplements** (2026-05-24): (1) **Daily reset of meals** — the nutrition page shows only *today's* `SavedMeal`s (`created_at__date == timezone.localdate()`); "eaten" marks effectively reset at midnight with no background job. (2) **Supplement tracker** — `nutrition.Supplement(name, last_taken_at)` (owner-scoped, `UniqueConstraint(owner, name)`, migration `nutrition.0002`). `taken_today` derived (`localdate(last_taken_at) == localdate()`) so it resets daily with no job. `COMMON_SUPPLEMENTS` quick-add chips + free-text custom. Views: `supplements`, `supplement_add`, `supplement_delete`, `supplement_take`. Home shows a "Suplementos de hoy" checklist.

- **nutrition-meal-variety → real curated recipes** (2026-05-24): a combinatorial generator (~2066 combos) was rejected by the user as incoherent. Final design: a hand-curated library of REAL named recipes — `MealTemplate` gained `name` (dish name) and `note` (prep hint). `generate_meal` picks a random eligible recipe (mains = protein/carb/fat must be liked; veg is part of the recipe, not a preference filter). UI renders the dish name as card title + prep note in italics + slot badge (`SavedMeal` gained `name`/`note`, migration `nutrition.0003`).

- **nutrition-recipe-shells** (2026-05-24): recipe FAMILIES (`_Shell`) — a dish type (`{protein} a la plancha con {carb} y {veg}`, `Licuado de proteína con {carb} y {fat}`, `Tacos de {protein} con {veg}`, `Bowl…`, `Huevos…`, etc.) whose component pools are interchangeable *within culinary bounds*. `_expand_shells()` takes the cartesian product per family → `MEAL_TEMPLATES = _expand_shells(_SHELLS) + _SPECIALS` ≈ 852 coherent named recipes (145 breakfast / 692 lunch+dinner / 99 snack). `_format_recipe_name()` builds the Spanish name from food labels. Sweet shells never use savory meats, savory shells never use sweet fats. ~60 hand-written `_SPECIALS` (antojitos) layered on top. To grow the count, widen a shell's pools.

- **nutrition-household-portions** (2026-05-24): each food row shows a household portion before the grams (e.g. "Huevo · 2 piezas (100 g)", "Whey · 1.5 medidas (45 g)", "Crema de cacahuate · 1 cucharada (16 g)"). `FOOD_PORTIONS` (slug → grams/unit + sing/plural) + `portion_label(slug, grams)`. Foods deliberately left in grams: rice/oats/pasta/quinoa/legumes, tuna (cubed grams), honey, yogurt, vegetables, potato. `portion_label` rounds to the nearest half-unit and returns "" below half a unit. Grams stay in parentheses.

- **responsive fixes** (2026-05-24): (1) "Esta semana" overflow — long routine-day labels wrapped with `break-words leading-tight`. (2) Mobile nav — replaced the horizontal-scroll top-bar with an Alpine hamburger toggle in `partials/_nav.html` (`x-data="{ open }"`, ☰/✕ `md:hidden`, `:class="open ? 'flex' : 'hidden'"` + `x-cloak` + static `md:flex`). No horizontal scroll at 375px.

- **mobile responsive overhaul** (2026-05-25): browser-verified at 390px (iPhone 13/Safari) with Playwright + WebKit. (1) Workout exercise card header stacks name above buttons on mobile. (2) Routine day-card editor restructured to a `flex justify-between` header + `grid grid-cols-2 sm:grid-cols-5`. (3) Tables wrapped in `overflow-x-auto` with `whitespace-nowrap`. (4) `truncate` → `break-words` everywhere. (5) Nutrition macro cards `text-[11px] leading-tight`. Always `npm run build:css` after Tailwind class changes.

- **scheduling: auto-program the week** (2026-05-25): generating a routine never wrote `WeeklySplit`, so the dashboard stayed empty. Added `WEEKDAY_PATTERNS` + `assign_weekly_split(owner, routine)` in `services/routine_generator/__init__.py` (1 day → Mon; 2 → Mon/Thu; 3 → Mon/Wed/Fri; 4 → Mon/Tue/Thu/Fri; 5 → Mon-Fri; 6 → Mon-Sat; 7 → all). Wired into `routine_create`. New view + button "Programar en la semana" on routine detail (`routines:apply_to_week`). The split editor replaced 7 per-day forms with a single bulk form (`weekly_split_save`; kept `weekly_split_assign` for compat).

- **fatigue/readiness** module: per-muscle fatigue that decays over days + daily sleep/stress/soreness inputs → "hoy no vayas pesado" advice (auto + manual adjust). `services/fatigue`: `compute_muscle_fatigue` (per-muscle exponential decay) + `daily_advice` (fatigue × readiness → rest/light/moderate/heavy). Deterministic, no jobs. Models `ReadinessSnapshot`, `FatigueAdjustment`.

- **rehab/prevention** module: corrective/mobility library + injury log + avoid/swap rules. `injuries` app (`Injury`, `MobilityExercise`). `services/rehab`: `avoided_exercise_ids` / `warnings_for_exercise` (active-injury avoid set), `mobility_for_user`, `suggested_swap`.

- **feedback** app: in-app bug reporting (floating button → `BugReport`) + superuser-only triage dashboard at `/feedback/admin/`. Not owner-scoped (reports belong to the superuser to read).

- **per-page hint banners**: `core.context_processors.page_hint` shows new-user suggestion banners per page.

---

## CRITICAL privacy fix — superuser bypass in `for_user` (2026-05-26)

`OwnerScopedQuerySet.for_user()` short-circuited to `self.all()` when
`user.is_superuser` was true. The superuser therefore saw every user's data on the
regular pages (dashboard, routines, metrics, PRs, weekly split). Surfaced when a
second account was created and the superuser saw that user's new routine + metrics
on their own home. The bypass is removed; `/admin` is unaffected because
`OwnerScopedAdmin.get_queryset` has its own superuser branch and doesn't call
`for_user`. Added defense-in-depth in dashboard + workouts.start: when following
`WeeklySplit.routine_day → Routine.owner`, re-check ownership so legacy split rows
can't leak another user's routine label. Regression suite in
`tests/apps/core/test_owner_scoping.py`. See memory `project-superuser-privacy`.

---

## Performance investigation (2026-05-20) — RESOLVED

A first request to `/auth/login/` took ~10 s on the user's machine. App-level
fixes applied (still useful):

1. Compiled Tailwind locally (`npm run build:css`) and switched `templates/base.html` to `{% static 'tailwind.css' %}` instead of the Play CDN. No more browser-side JIT.
2. Added an HTMX progress bar (`#htmx-progress`) in `base.html`.
3. Overrode `STORAGES` in `config/settings/dev.py` to use `StaticFilesStorage` instead of Whitenoise's manifest storage (which requires `collectstatic`). Prod keeps the manifest storage.
4. Audited dashboard + list querysets — all use `select_related`/`prefetch_related`. No N+1.

**Real root cause was environmental:** the project lived under `~/Documents/`, which
macOS syncs to iCloud Drive; with the disk ~98% full, iCloud's `bird` daemon was
offloading project files (`.venv`, `node_modules`), so every Python import or
template render blocked waiting for re-materialisation. **Fix:** the project was
moved off iCloud to `~/gymapp/`. Resolved.
