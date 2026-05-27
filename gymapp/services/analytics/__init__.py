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

import statistics
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


# Deload heuristic: suggest a light week after this many consecutive training
# weeks without a week light enough to count as a deload.
ACCUMULATION_WEEKS = 5
LIGHT_WEEK_RATIO = 0.6  # a week ≤ 60% of the run's peak tonnage already deloads


@dataclass(frozen=True)
class DeloadAdvice:
    recommended: bool
    weeks_accumulated: int
    threshold: int
    reason: str  # "accumulated_fatigue" | "accumulating" | "no_recent_training"


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


@dataclass(frozen=True)
class BodyCompPoint:
    """One row from `UserMetricSnapshot`, with BMI derived from profile height."""

    date: date
    weight_kg: float
    bmi: float | None
    body_fat_pct: float | None
    muscle_pct: float | None


def body_comp_series(user, *, days: int = 180) -> list[BodyCompPoint]:
    """Chronological body-composition points over the last `days` calendar days.

    BMI is computed from `profile.height_cm` (None if height isn't set).
    Returns oldest -> newest, so a line chart reads left-to-right naturally.
    """
    from gymapp.apps.metrics.models import UserMetricSnapshot

    cutoff_dt = timezone.now() - timedelta(days=days)
    height_cm = getattr(getattr(user, "profile", None), "height_cm", None)
    snaps = (
        UserMetricSnapshot.objects.for_user(user)
        .filter(measured_at__gte=cutoff_dt)
        .order_by("measured_at")
    )
    out: list[BodyCompPoint] = []
    for s in snaps:
        out.append(
            BodyCompPoint(
                date=s.measured_at.date(),
                weight_kg=float(s.weight_kg),
                bmi=s.bmi_for(height_cm),
                body_fat_pct=float(s.body_fat_pct) if s.body_fat_pct is not None else None,
                muscle_pct=float(s.muscle_pct) if s.muscle_pct is not None else None,
            )
        )
    return out


def deload_recommendation(
    user, *, today: date | None = None, threshold: int = ACCUMULATION_WEEKS
) -> DeloadAdvice:
    """Suggest a deload after enough consecutive hard weeks.

    Looks at completed weeks (the current, partial week is ignored), counts the
    trailing run of training weeks (sets > 0), and stops counting at any week
    whose tonnage already dipped to a deload level (≤ `LIGHT_WEEK_RATIO` of the
    run's median). Using the median (not the peak) keeps one unusually big week
    from masking a steady block. If the count reaches `threshold`, a deload is
    recommended.
    """
    today = today or timezone.localdate()
    this_monday = _monday(today)
    weeks = weekly_volume(user, weeks=threshold + 4, today=today)
    completed = [w for w in weeks if w.week_start < this_monday]

    run: list[WeeklyPoint] = []
    for w in reversed(completed):
        if w.sets > 0:
            run.append(w)
        else:
            break
    if not run:
        return DeloadAdvice(False, 0, threshold, "no_recent_training")

    reference = statistics.median(w.volume_kg for w in run)
    accumulated = 0
    for w in run:  # run is newest-first
        if reference and w.volume_kg <= LIGHT_WEEK_RATIO * reference:
            break
        accumulated += 1

    recommended = accumulated >= threshold
    reason = "accumulated_fatigue" if recommended else "accumulating"
    return DeloadAdvice(recommended, accumulated, threshold, reason)
