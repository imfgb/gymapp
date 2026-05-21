"""Routine generator.

Given a split preset and the user's training style, builds a complete
`Routine` with `RoutineDay`s and `RoutineExercise`s. The output is editable
in the routine UI like any other routine.

Heuristics (Phase 2; deterministic, no AI):

- Preset = ordered list of `DayPlan`s. Each day declares the muscle groups
  it focuses on, in priority order.
- For each day, pick `compounds` compounds (one per top-priority muscle)
  then one isolation per muscle in focus (skipping muscles whose group is
  already used by a chosen compound).
- Rep scheme per (training_style × compound|isolation) — see `_rep_scheme`.

Picking is greedy: alphabetically the first global exercise whose primary
muscles contain the target. The user immediately edits to taste — we're
trying to skip the blank-page problem, not to be brilliant.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from django.db import transaction


class SplitPreset(str, Enum):
    PPL_6 = "ppl_6"
    PPL_3 = "ppl_3"
    UPPER_LOWER_4 = "upper_lower_4"
    BRO_SPLIT_5 = "bro_split_5"
    FULL_BODY_3 = "full_body_3"
    CUSTOM = "custom"


@dataclass
class DayPlan:
    label: str
    muscle_focus: list[str]  # primary muscle slugs, highest priority first
    compounds: int = 2  # how many compounds to pick from the top of muscle_focus


# All slugs here must exist in seeds/exercises.yaml's muscle_groups.
PRESETS: dict[SplitPreset, list[DayPlan]] = {
    SplitPreset.PPL_6: [
        DayPlan("Push A", ["chest", "delts-front", "triceps", "delts-side"]),
        DayPlan("Pull A", ["lats", "traps-mid", "biceps", "delts-rear"]),
        DayPlan("Legs A", ["quads", "glutes", "hamstrings", "calves"]),
        DayPlan("Push B", ["chest", "delts-side", "delts-front", "triceps"]),
        DayPlan("Pull B", ["lats", "biceps", "traps-mid", "delts-rear"]),
        DayPlan("Legs B", ["hamstrings", "glutes", "quads", "calves"]),
    ],
    SplitPreset.PPL_3: [
        DayPlan("Push", ["chest", "delts-front", "triceps", "delts-side"]),
        DayPlan("Pull", ["lats", "traps-mid", "biceps", "delts-rear"]),
        DayPlan("Legs", ["quads", "hamstrings", "glutes", "calves"]),
    ],
    SplitPreset.UPPER_LOWER_4: [
        DayPlan("Upper A", ["chest", "lats", "delts-front", "biceps", "triceps"]),
        DayPlan("Lower A", ["quads", "glutes", "hamstrings", "calves"]),
        DayPlan("Upper B", ["lats", "chest", "delts-side", "triceps", "biceps"]),
        DayPlan("Lower B", ["hamstrings", "glutes", "quads", "calves"]),
    ],
    SplitPreset.BRO_SPLIT_5: [
        DayPlan("Chest", ["chest", "triceps"]),
        DayPlan("Back", ["lats", "traps-mid", "biceps"]),
        DayPlan("Shoulders", ["delts-front", "delts-side", "delts-rear"]),
        DayPlan("Arms", ["biceps", "triceps", "forearms"]),
        DayPlan("Legs", ["quads", "hamstrings", "glutes", "calves"]),
    ],
    SplitPreset.FULL_BODY_3: [
        DayPlan("Full Body A", ["quads", "chest", "lats", "delts-front"], compounds=3),
        DayPlan("Full Body B", ["hamstrings", "chest", "lats", "delts-side"], compounds=3),
        DayPlan("Full Body C", ["glutes", "chest", "lats", "triceps"], compounds=3),
    ],
}


PRESET_LABELS: dict[SplitPreset, str] = {
    SplitPreset.PPL_6: "Push / Pull / Legs (6 días)",
    SplitPreset.PPL_3: "Push / Pull / Legs (3 días)",
    SplitPreset.UPPER_LOWER_4: "Upper / Lower (4 días)",
    SplitPreset.BRO_SPLIT_5: "Bro split (5 días)",
    SplitPreset.FULL_BODY_3: "Full body (3 días)",
}


def _rep_scheme(training_style: str, *, compound: bool) -> tuple[int, int, int]:
    """Return (sets, reps_low, reps_high) per training style."""
    if training_style == "powerlifting":
        return (5, 3, 5) if compound else (3, 8, 12)
    if training_style == "bodybuilding":
        return (4, 8, 12) if compound else (3, 10, 15)
    # powerbuilding (default)
    return (4, 5, 8) if compound else (3, 8, 12)


def _pick(muscle_slug: str, category: str, excluded_ids: set[int]):
    from gymapp.apps.exercises.models import Exercise

    return (
        Exercise.objects.filter(
            owner__isnull=True,
            category=category,
            is_active=True,
            primary_muscles__slug=muscle_slug,
        )
        .exclude(id__in=excluded_ids)
        .order_by("name")
        .first()
    )


@dataclass
class GeneratedDayPreview:
    label: str
    exercises: list[tuple[str, int, int, int]] = field(default_factory=list)
    # (exercise_name, sets, reps_low, reps_high)


def _resolve_plans(preset: SplitPreset, custom_days):
    if preset == SplitPreset.CUSTOM:
        if not custom_days:
            raise ValueError("Custom preset requires non-empty `custom_days`.")
        return custom_days
    return PRESETS[preset]


def _build_day_exercises(plan: DayPlan, training_style: str):
    """Yields tuples (exercise, sets, reps_low, reps_high) in order."""
    used_ids: set[int] = set()
    for muscle in plan.muscle_focus[: plan.compounds]:
        ex = _pick(muscle, "compound", used_ids)
        if ex is None:
            continue
        used_ids.add(ex.id)
        sets, lo, hi = _rep_scheme(training_style, compound=True)
        yield ex, sets, lo, hi
    for muscle in plan.muscle_focus:
        ex = _pick(muscle, "isolation", used_ids)
        if ex is None:
            continue
        used_ids.add(ex.id)
        sets, lo, hi = _rep_scheme(training_style, compound=False)
        yield ex, sets, lo, hi


@transaction.atomic
def generate_routine(
    *,
    owner,
    preset: SplitPreset,
    training_style: str,
    name: str,
    custom_days: list[DayPlan] | None = None,
):
    """Create the routine + days + exercises and return the Routine instance."""
    from gymapp.apps.routines.models import Routine, RoutineDay, RoutineExercise

    plans = _resolve_plans(preset, custom_days)

    routine = Routine.objects.create(
        owner=owner, name=name, training_style=training_style
    )
    for day_idx, plan in enumerate(plans):
        day = RoutineDay.objects.create(
            routine=routine, label=plan.label, ordering=day_idx
        )
        for ordering, (ex, sets, lo, hi) in enumerate(
            _build_day_exercises(plan, training_style)
        ):
            RoutineExercise.objects.create(
                routine_day=day,
                exercise=ex,
                ordering=ordering,
                target_sets=sets,
                target_reps_low=lo,
                target_reps_high=hi,
            )
    return routine


def preview_routine(
    *,
    preset: SplitPreset,
    training_style: str,
    custom_days: list[DayPlan] | None = None,
) -> list[GeneratedDayPreview]:
    """Compute what generate_routine would produce, without persisting."""
    plans = _resolve_plans(preset, custom_days)
    out: list[GeneratedDayPreview] = []
    for plan in plans:
        preview = GeneratedDayPreview(label=plan.label)
        for ex, sets, lo, hi in _build_day_exercises(plan, training_style):
            preview.exercises.append((ex.name, sets, lo, hi))
        out.append(preview)
    return out
