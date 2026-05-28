"""Per-muscle fatigue + daily training advice.

Deterministic, no jobs. `compute_muscle_fatigue` walks recent completed working
sets, sums one fatigue unit per primary muscle per set, and decays the
contribution exponentially with a per-muscle half-life (deadlift-driven lumbar
recovers slower than biceps). Manual `FatigueAdjustment` rows stack on top so
the user can override what the math says.

`daily_advice` combines today's targeted muscles' fatigue with the day's
readiness snapshot (sleep / stress / soreness) into a single "go heavy /
moderate / light or skip" recommendation. The thresholds are deliberate
round numbers — easy to read in tests, easy to tune later.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from django.utils import timezone


# Half-life in days for fatigue contribution from a set to decay. Bigger
# posterior-chain muscles take longer to recover than small isolation work.
MUSCLE_HALF_LIFE_DAYS: dict[str, float] = {
    # Slow recovery
    "lumbar": 4.0,
    "glutes": 3.0,
    "hamstrings": 3.0,
    # Medium
    "chest": 2.5,
    "lats": 2.5,
    "quads": 2.5,
    "traps-mid": 2.0,
    "delts-front": 2.0,
    "delts-side": 2.0,
    "delts-rear": 2.0,
    # Fast
    "biceps": 1.5,
    "triceps": 1.5,
    "forearms": 1.5,
    "calves": 1.5,
    "abs": 1.5,
}
DEFAULT_HALF_LIFE_DAYS = 2.0

# How far back to look. Beyond this the exponential decay makes the
# contribution negligible anyway, so bounding the query is free perf.
WINDOW_DAYS = 14

# Fatigue (in decayed sets-equivalent units) above which we recommend a lighter
# day for the targeted muscles. Calibrated for a typical hypertrophy block
# (8–14 weekly sets per muscle).
HEAVY_THRESHOLD = 12.0
MODERATE_THRESHOLD = 6.0


@dataclass
class MuscleFatigue:
    muscle: str
    score: float  # 0+; decayed sets-equivalent units
    raw_sets: int  # sets within the window (for transparency in the UI)


@dataclass
class DailyAdvice:
    level: str  # "rest" | "light" | "moderate" | "heavy"
    label: str  # Spanish UI string
    reason: str  # short Spanish explanation
    color: str  # "slate" | "rose" | "amber" | "emerald" (Tailwind hint)
    avg_fatigue: float
    readiness: float | None  # 1–5 combined from today's snapshot, if any
    target_muscles: list[str]  # primary muscle slugs scheduled for today


def _decay(days_since: int, half_life: float) -> float:
    return math.pow(0.5, max(0, days_since) / half_life)


def compute_muscle_fatigue(user, today: date | None = None) -> dict[str, MuscleFatigue]:
    """Return per-muscle fatigue, including manual `FatigueAdjustment` deltas
    for `today`. Only completed, non-warm-up working sets count."""
    from gymapp.apps.metrics.models import FatigueAdjustment
    from gymapp.apps.workouts.models import SetLog, WorkoutStatus

    today = today or timezone.localdate()
    cutoff = today - timedelta(days=WINDOW_DAYS)

    sets = (
        SetLog.objects.filter(
            exercise_log__session__owner=user,
            exercise_log__session__status=WorkoutStatus.FINISHED,
            is_warmup=False,
            completed_at__date__gte=cutoff,
            completed_at__date__lte=today,
        )
        .select_related("exercise_log__exercise")
        .prefetch_related("exercise_log__exercise__primary_muscles")
    )

    by_muscle: dict[str, dict[str, float]] = defaultdict(lambda: {"score": 0.0, "sets": 0})
    for s in sets:
        # `completed_at` is stored UTC; convert to local before extracting the
        # date so `days_since` matches `today = localdate()` instead of straddling
        # midnight UTC (Mexico City is UTC-6, so 18:00-24:00 local is the next UTC day).
        days_since = (today - timezone.localtime(s.completed_at).date()).days
        for m in s.exercise_log.exercise.primary_muscles.all():
            hl = MUSCLE_HALF_LIFE_DAYS.get(m.slug, DEFAULT_HALF_LIFE_DAYS)
            by_muscle[m.slug]["score"] += _decay(days_since, hl)
            by_muscle[m.slug]["sets"] += 1

    for adj in FatigueAdjustment.objects.for_user(user).filter(date=today):
        by_muscle[adj.muscle_slug]["score"] += float(adj.delta)

    return {
        slug: MuscleFatigue(muscle=slug, score=max(0.0, info["score"]), raw_sets=info["sets"])
        for slug, info in by_muscle.items()
    }


def current_readiness(user, today: date | None = None) -> float | None:
    """Today's combined 1–5 readiness score, or None if no snapshot today."""
    from gymapp.apps.metrics.models import ReadinessSnapshot

    today = today or timezone.localdate()
    snap = ReadinessSnapshot.objects.for_user(user).filter(date=today).first()
    return snap.readiness_score if snap else None


def _today_target_muscles(user, today: date) -> list[str]:
    """Primary muscle slugs scheduled for today via the user's WeeklySplit.
    Empty list = today is a rest day (per the user's split, not derived)."""
    from gymapp.apps.routines.models import WeeklySplit

    split = (
        WeeklySplit.objects.for_user(user)
        .filter(weekday=today.weekday())
        .select_related("routine_day__routine")
        .first()
    )
    if (
        split is None
        or split.routine_day is None
        or split.routine_day.routine.is_archived
        or split.routine_day.routine.owner_id != user.id
    ):
        return []
    muscles: set[str] = set()
    for rex in (
        split.routine_day.exercises.select_related("exercise").prefetch_related(
            "exercise__primary_muscles"
        )
    ):
        for m in rex.exercise.primary_muscles.all():
            muscles.add(m.slug)
    return sorted(muscles)


def daily_advice(user, today: date | None = None) -> DailyAdvice:
    """Combine today's targeted muscles' average fatigue with the readiness
    snapshot into a single training recommendation for the day."""
    today = today or timezone.localdate()

    targets = _today_target_muscles(user, today)
    if not targets:
        return DailyAdvice(
            level="rest",
            label="Descanso programado",
            reason="Hoy no tienes entrenamiento agendado.",
            color="slate",
            avg_fatigue=0.0,
            readiness=current_readiness(user, today),
            target_muscles=[],
        )

    fatigue = compute_muscle_fatigue(user, today)
    relevant_scores = [fatigue[m].score for m in targets if m in fatigue]
    avg = sum(relevant_scores) / len(relevant_scores) if relevant_scores else 0.0
    readiness = current_readiness(user, today)

    if avg >= HEAVY_THRESHOLD or (readiness is not None and readiness <= 2):
        return DailyAdvice(
            level="light",
            label="Hoy ligero o descansa",
            reason=(
                f"Tus músculos de hoy están cargados (promedio {avg:.1f})."
                if avg >= HEAVY_THRESHOLD
                else "Tu readiness es bajo hoy."
            ),
            color="rose",
            avg_fatigue=avg,
            readiness=readiness,
            target_muscles=targets,
        )

    if avg >= MODERATE_THRESHOLD or (readiness is not None and readiness <= 3):
        return DailyAdvice(
            level="moderate",
            label="Moderado",
            reason="Entrena sin buscar PR hoy; controla el RPE.",
            color="amber",
            avg_fatigue=avg,
            readiness=readiness,
            target_muscles=targets,
        )

    return DailyAdvice(
        level="heavy",
        label="Pesado: dale",
        reason="Estás recuperado, busca el PR.",
        color="emerald",
        avg_fatigue=avg,
        readiness=readiness,
        target_muscles=targets,
    )


def fatigue_table(user, today: date | None = None) -> list[MuscleFatigue]:
    """Sorted list (most fatigued first) for UI rendering."""
    today = today or timezone.localdate()
    rows = list(compute_muscle_fatigue(user, today).values())
    rows.sort(key=lambda m: m.score, reverse=True)
    return rows


__all__ = [
    "MUSCLE_HALF_LIFE_DAYS",
    "DEFAULT_HALF_LIFE_DAYS",
    "WINDOW_DAYS",
    "HEAVY_THRESHOLD",
    "MODERATE_THRESHOLD",
    "MuscleFatigue",
    "DailyAdvice",
    "compute_muscle_fatigue",
    "current_readiness",
    "daily_advice",
    "fatigue_table",
]
