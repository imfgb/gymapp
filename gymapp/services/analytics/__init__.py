"""Analytics service — Phase 5.

Deterministic training-volume rollups from finished sessions:

- `weekly_volume`: tonnage (Σ weight×reps) + working-set count per week.
- `sets_by_muscle`: this week's hard sets + volume attributed to each primary
  muscle group (full counting — a set counts once for every primary muscle the
  exercise trains).

Warm-ups and incomplete sets never count. Pure functions (no AI, no Protocol
seam needed) — same shape as `services.goals`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from django.utils import timezone

from gymapp.apps.workouts.models import SetLog, WorkoutStatus


@dataclass(frozen=True)
class WeeklyPoint:
    week_start: date
    volume_kg: int
    sets: int


@dataclass(frozen=True)
class MuscleWeek:
    muscle: str
    sets: int
    volume_kg: int


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _completed_working_sets(user):
    return SetLog.objects.filter(
        exercise_log__session__owner=user,
        exercise_log__session__status=WorkoutStatus.FINISHED,
        is_warmup=False,
        completed_at__isnull=False,
        weight_kg__isnull=False,
        reps__isnull=False,
    )


def weekly_volume(user, *, weeks: int = 8, today: date | None = None) -> list[WeeklyPoint]:
    """Tonnage + set count for each of the last `weeks` weeks (oldest first).

    Weeks are Monday-anchored; empty weeks are included as zero so the trend
    has no gaps.
    """
    today = today or timezone.localdate()
    first_monday = _monday(today) - timedelta(weeks=weeks - 1)

    buckets: dict[date, list[float]] = {
        first_monday + timedelta(weeks=i): [0.0, 0] for i in range(weeks)
    }
    rows = (
        _completed_working_sets(user)
        .filter(exercise_log__session__started_at__date__gte=first_monday)
        .values_list("exercise_log__session__started_at", "weight_kg", "reps")
    )

    for started_at, weight, reps in rows:
        wk = _monday(timezone.localdate(started_at))
        if wk in buckets:
            buckets[wk][0] += float(weight) * reps
            buckets[wk][1] += 1

    return [
        WeeklyPoint(week_start=wk, volume_kg=int(round(vol)), sets=int(count))
        for wk, (vol, count) in sorted(buckets.items())
    ]


def sets_by_muscle(user, *, today: date | None = None) -> list[MuscleWeek]:
    """Current week's hard sets + volume per primary muscle group, busiest first."""
    today = today or timezone.localdate()
    wk = _monday(today)
    rows = (
        _completed_working_sets(user)
        .filter(
            exercise_log__session__started_at__date__gte=wk,
            exercise_log__session__started_at__date__lt=wk + timedelta(days=7),
        )
        .select_related("exercise_log__exercise")
        .prefetch_related("exercise_log__exercise__primary_muscles")
    )

    agg: dict[str, list[float]] = {}
    for s in rows:
        vol = float(s.weight_kg) * s.reps
        for muscle in s.exercise_log.exercise.primary_muscles.all():
            entry = agg.setdefault(muscle.name, [0, 0.0])
            entry[0] += 1
            entry[1] += vol

    return sorted(
        (
            MuscleWeek(muscle=name, sets=int(count), volume_kg=int(round(vol)))
            for name, (count, vol) in agg.items()
        ),
        key=lambda m: m.sets,
        reverse=True,
    )
