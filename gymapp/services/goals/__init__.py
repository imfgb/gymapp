"""Monthly goal progress service.

Computes how far a `metrics.MonthlyGoal` has come within its calendar month.
This is a cross-app read rollup (workouts sessions + completed sets + bodyweight
snapshots) so it lives in the service layer rather than in a view or model.

Deterministic only — no AI. Phase 4's analytics service may subsume the volume
rollup later, but monthly goals need it now.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from gymapp.apps.metrics.models import MonthlyGoal, UserMetricSnapshot
from gymapp.apps.workouts.models import WorkoutSession, WorkoutStatus


@dataclass(frozen=True)
class GoalMetric:
    """One target/actual pair, ready to render as a progress row."""

    key: str
    label: str
    target: Decimal | int
    actual: Decimal | int
    unit: str
    pct: int
    reached: bool


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """Return [start, end) dates spanning the given calendar month."""
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def _pct(actual, target) -> int:
    if not target:
        return 0
    return min(100, int(round(float(actual) / float(target) * 100)))


def get_or_create_current(user, today: date) -> MonthlyGoal:
    """Fetch (or create empty) the goal for the month containing `today`."""
    goal, _ = MonthlyGoal.objects.get_or_create(
        owner=user, year=today.year, month=today.month
    )
    return goal


def current_goal(user, today: date) -> MonthlyGoal | None:
    return (
        MonthlyGoal.objects.for_user(user)
        .filter(year=today.year, month=today.month)
        .first()
    )


def monthly_goal_progress(goal: MonthlyGoal) -> list[GoalMetric]:
    """Build the list of progress rows for the goal's month.

    Only targets that were actually set produce a row, so a goal with just a
    session target renders a single bar.
    """
    start, end = month_bounds(goal.year, goal.month)

    finished_sessions = WorkoutSession.objects.filter(
        owner=goal.owner,
        status=WorkoutStatus.FINISHED,
        started_at__date__gte=start,
        started_at__date__lt=end,
    )

    metrics: list[GoalMetric] = []

    if goal.target_sessions:
        done = finished_sessions.count()
        metrics.append(
            GoalMetric(
                key="sessions",
                label="Entrenamientos",
                target=goal.target_sessions,
                actual=done,
                unit="",
                pct=_pct(done, goal.target_sessions),
                reached=done >= goal.target_sessions,
            )
        )

    if goal.target_bodyweight_kg:
        metrics.append(_bodyweight_metric(goal, start, end))

    return metrics


def _bodyweight_metric(goal: MonthlyGoal, start: date, end: date) -> GoalMetric:
    """Bodyweight progress from a baseline toward the target.

    Baseline = the most recent snapshot before the month began (where the user
    started). Progress runs in whichever direction the target lies, so a cut and
    a bulk both fill toward 100%. With no baseline we can't draw a bar, so pct
    stays 0 and only the current/target numbers are meaningful.
    """
    target = goal.target_bodyweight_kg
    snaps = UserMetricSnapshot.objects.filter(owner=goal.owner)
    latest = snaps.filter(measured_at__date__lt=end).order_by("-measured_at").first()
    baseline = snaps.filter(measured_at__date__lt=start).order_by("-measured_at").first()

    current = latest.weight_kg if latest else None
    base_w = baseline.weight_kg if baseline else None

    pct = 0
    reached = False
    if current is not None:
        if base_w is not None and base_w != target:
            span = abs(target - base_w)
            moved = abs(current - base_w)
            # Only count movement in the right direction toward the target.
            toward = (current - base_w) * (target - base_w) > 0
            pct = min(100, int(round(float(moved) / float(span) * 100))) if toward else 0
        reached = abs(current - target) <= Decimal("0.5")
        if reached:
            pct = 100

    return GoalMetric(
        key="bodyweight",
        label="Peso corporal",
        target=target,
        actual=current if current is not None else Decimal("0"),
        unit="kg",
        pct=pct,
        reached=reached,
    )
