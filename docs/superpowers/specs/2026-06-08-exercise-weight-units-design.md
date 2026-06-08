# Exercise weight units (kg/lb) — design

**Date:** 2026-06-08
**Status:** approved (brainstorming) → implementing
**Bug:** feedback #8 — "Que se pueda seleccionar Kilos o Libras" (cable/machine in lb by default).
**Supersedes:** ADR-006 (metric-only) for *lifted* weight. Bodyweight stays metric.

## Goal

Let each exercise's **lifted** weight be entered and displayed in kg or lb. Cable
and Machine exercises default to lb; everything else defaults to kg; per-exercise
override; null = auto-by-equipment. Bodyweight (metrics/nutrition) is out of scope
and stays kg.

## Decisions (from brainstorming, 2026-06-08)

| # | Decision |
|---|---|
| Storage | **Canonical kg.** Weight is always stored in kg (single source of truth). The exercise's unit governs input/display only. Aggregations (tonnage, volume, PRs) stay in kg. |
| Scope | **Lifted weight only** (`SetLog`, `RoutineExercise`, `PersonalRecord`). Bodyweight (`UserMetricSnapshot`, `MonthlyGoal.target_bodyweight_kg`) stays kg. |
| Increments | **lb-sensible.** lb exercises advance +5 lb and warm-ups snap to 5-lb steps; kg exercises keep +2.5/+5/+1.25 and kg plate snapping. |
| Unit location | A field on **`Exercise`** (it already carries equipment + category). |
| Null unit | **Auto:** resolve from equipment (`cable`/`machine` → lb, else kg). No data migration for existing rows. |
| Conversion | 1 kg = 2.20462262 lb. Store kg @ 2 dp. Display lb rounded to 0.5. |

## Architecture — incremental layers

```
[A] model + units helper  →  [B] input/display conversion  →
[C] progression + warmup (lb-aware)  →  [D] create/edit unit UI  →  [E] docs
```

### A — model + units helper

- `Exercise.weight_unit`: `CharField(max_length=2, choices=WeightUnit.choices, blank=True, default="")`. `WeightUnit` = {`kg`, `lb`}; **blank `""` = auto** (ruff DJ001 discourages `null` on string fields, and `""` is a clean tri-state sentinel). Migration adds the column (no backfill).
- `Exercise.effective_weight_unit` (property): `self.weight_unit or ("lb" if self.equipment.slug in {"cable","machine"} else "kg")`.
- `gymapp/services/units.py` (deterministic, pure):
  - `KG_PER_LB`, `LB_PER_KG` constants.
  - `to_kg(value: Decimal, unit: str) -> Decimal` — display→kg (kg passthrough; lb÷factor), 2 dp.
  - `to_display(weight_kg: Decimal, unit: str) -> Decimal` — kg→display (kg passthrough; lb×factor), rounded (kg 2dp / lb 0.5).
  - `increment_kg(unit, category) -> Decimal` — kg-equiv of +5 lb (lb) / existing kg jumps.
  - `snap_loadable_kg(weight_kg, unit, equipment_slug) -> Decimal` — kg plate steps / 5-lb steps (converted).
  - `label(unit) -> str` ("kg"/"lb").
  - Tests: round-trip (100 lb → kg → 100 lb), passthrough kg, lb display rounding, snapping, increments.

### B — input/display conversion (kg stays source of truth)

- **Input (display→kg on save):** `workouts.complete_set_view` / `update_set_view`, `routines.exercise_update`, `prs` create/edit. Convert the posted value with `to_kg(value, exercise.effective_weight_unit)` before storing `weight_kg`.
- **Display (kg→display):** template filter `gymapp/apps/core/templatetags` `{{ weight_kg|in_unit:exercise }}` + `{{ exercise|weight_unit_label }}`. Apply on: workout set row, routine day-card target weight, PR list/detail, dashboard recent/PR cards, progression prefill (the prefilled SetLog weight shown on session start).
- The `<input>` for weight shows the value already converted to the exercise's unit, with a "kg"/"lb" label next to it.

### C — progression + warm-up (lb-aware)

- `progression._weight_increment` → delegate to `units.increment_kg(effective_unit, category)`. Stored kg advances by the kg-equivalent of +5 lb for lb exercises, so the displayed lb is a clean +5.
- `warmup.warmup_scheme` → for lb exercises, snap ramp steps to 5-lb (converted to kg) instead of kg plates.

### D — exercise create/edit unit UI

- The custom-exercise create form (routines editor `exercise_add_custom`, workouts `add_custom_exercise`) gets a unit `<select>`: **Auto (por equipo) / Kilos / Libras** → maps to `weight_unit = null | "kg" | "lb"`. Default Auto.
- (Optional, later) edit unit on an existing custom exercise.

### E — docs

- Update **ADR-006**: exercise weight is kg-canonical with kg/lb presentation; bodyweight stays metric. New ADR line documenting the unit field + null-auto rule.
- Update CLAUDE.md §9 business rule ("Metric units only") + the constraint note.

## Out of scope (YAGNI)

- Bodyweight / nutrition / BMI in lb.
- A global per-user unit preference (it's per-exercise).
- Editing the unit of seeded (global) exercises via UI (override only relevant for the user's own customs + the auto default covers seeds).
- Historical re-display nuance: existing kg-logged data on a now-lb exercise simply displays converted (it was always kg).

## Risks

- **Rounding drift:** mitigated by storing kg @ 2dp and rounding lb display to 0.5; round-trip is stable for typical gym weights.
- **Many display points:** the template filter centralizes conversion; missing one shows kg (safe, just not converted) — tests cover the main paths.
