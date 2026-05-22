"""Progression service — Phase 2.

Determines recommended weight × reps for the next working sets based on the
user's history and training style.

Linear progression (powerlifting):
  Fixed rep target. When all working sets hit the target, add a weight
  increment on the next session. Otherwise repeat the same weight/reps.

Double progression (bodybuilding / powerbuilding):
  Rep-range target (low–high). Accumulate reps until all sets hit the top of
  the range; then increase weight and drop back to the low end.

Phase 4: replace DeterministicLinear/Double with an LLMStrategy that reasons
over longer history windows. The public `recommend_next` entry point is the
seam — callers never touch the strategy directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SetRecommendation:
    weight_kg: Decimal | None
    reps: int | None
    rationale: str = ""


@runtime_checkable
class ProgressionStrategy(Protocol):
    def recommend(
        self,
        *,
        last_sets: list,
        target_reps_low: int,
        target_reps_high: int,
        current_weight: Decimal | None,
        weight_increment_kg: Decimal,
    ) -> SetRecommendation: ...


class DeterministicLinearProgression:
    """If every working set in the previous session hit the rep target, add one
    weight increment. Otherwise repeat the same weight and reps."""

    def recommend(
        self,
        *,
        last_sets: list,
        target_reps_low: int,
        target_reps_high: int,
        current_weight: Decimal | None,
        weight_increment_kg: Decimal,
    ) -> SetRecommendation:
        if not last_sets:
            return SetRecommendation(
                weight_kg=current_weight,
                reps=target_reps_low,
                rationale="no_history",
            )

        last_weight = last_sets[0].weight_kg
        all_hit = all(s.reps is not None and s.reps >= target_reps_low for s in last_sets)

        if all_hit and last_weight is not None:
            return SetRecommendation(
                weight_kg=last_weight + weight_increment_kg,
                reps=target_reps_low,
                rationale="linear_increase",
            )

        return SetRecommendation(
            weight_kg=last_weight,
            reps=target_reps_low,
            rationale="repeat_weight",
        )


class DeterministicDoubleProgression:
    """Accumulate reps within the rep range. When every working set hits the
    top of the range, add a weight increment and reset to the low end."""

    def recommend(
        self,
        *,
        last_sets: list,
        target_reps_low: int,
        target_reps_high: int,
        current_weight: Decimal | None,
        weight_increment_kg: Decimal,
    ) -> SetRecommendation:
        if not last_sets:
            return SetRecommendation(
                weight_kg=current_weight,
                reps=target_reps_low,
                rationale="no_history",
            )

        last_weight = last_sets[0].weight_kg
        completed_reps = [s.reps for s in last_sets if s.reps is not None]

        all_hit_top = bool(completed_reps) and all(r >= target_reps_high for r in completed_reps)

        if all_hit_top and last_weight is not None:
            return SetRecommendation(
                weight_kg=last_weight + weight_increment_kg,
                reps=target_reps_low,
                rationale="double_progression_increase",
            )

        # Stay at same weight; target the average of what was done, clamped to
        # the prescribed range, so the user keeps building toward the top.
        if completed_reps:
            avg = sum(completed_reps) // len(completed_reps)
            next_reps = max(target_reps_low, min(avg, target_reps_high))
        else:
            next_reps = target_reps_low

        return SetRecommendation(
            weight_kg=last_weight,
            reps=next_reps,
            rationale="repeat_build_reps",
        )


def _weight_increment(exercise, training_style: str) -> Decimal:
    """Smaller plates for isolation exercises; bigger jumps for powerlifting."""
    from gymapp.apps.users.models import TrainingStyle

    if training_style == TrainingStyle.POWERLIFTING:
        return Decimal("2.5") if exercise.category == "isolation" else Decimal("5.0")
    return Decimal("1.25") if exercise.category == "isolation" else Decimal("2.5")


def _get_strategy(training_style: str) -> ProgressionStrategy:
    from gymapp.apps.users.models import TrainingStyle

    if training_style == TrainingStyle.POWERLIFTING:
        return DeterministicLinearProgression()
    return DeterministicDoubleProgression()


def _last_completed_sets(user, exercise) -> list:
    """Return working SetLogs from the most recent finished session that
    included this exercise, ordered by set position."""
    from gymapp.apps.workouts.models import ExerciseLog, WorkoutStatus

    last_elog = (
        ExerciseLog.objects.filter(
            exercise=exercise,
            session__owner=user,
            session__status=WorkoutStatus.FINISHED,
        )
        .order_by("-session__finished_at")
        .first()
    )

    if last_elog is None:
        return []

    return list(
        last_elog.set_logs.filter(
            completed_at__isnull=False,
            is_warmup=False,
        ).order_by("ordering")
    )


def recommend_next(
    *,
    user,
    exercise,
    target_reps_low: int,
    target_reps_high: int,
    current_weight: Decimal | None = None,
) -> SetRecommendation:
    """Public entry point.

    Returns a single SetRecommendation that applies to all working sets for
    this exercise in the upcoming session. The caller (start_session) stamps
    the same weight×reps onto every SetLog — the user adjusts per-set live.
    """
    training_style: str = getattr(getattr(user, "profile", None), "training_style", "powerbuilding")
    strategy = _get_strategy(training_style)
    last_sets = _last_completed_sets(user, exercise)
    increment = _weight_increment(exercise, training_style)

    return strategy.recommend(
        last_sets=last_sets,
        target_reps_low=target_reps_low,
        target_reps_high=target_reps_high,
        current_weight=current_weight,
        weight_increment_kg=increment,
    )
