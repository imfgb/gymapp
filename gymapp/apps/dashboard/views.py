"""Dashboard: today's workout, weekly split, recent sessions, PR highlights."""

from __future__ import annotations

from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from gymapp.apps.metrics.models import UserMetricSnapshot
from gymapp.apps.prs.models import PersonalRecord
from gymapp.apps.routines.models import Routine, SkippedDay, Weekday, WeeklySplit
from gymapp.apps.workouts.models import WorkoutSession, WorkoutStatus
from gymapp.services.analytics import (
    deload_recommendation,
    sets_by_muscle,
    weekly_volume,
)
from gymapp.services.goals import current_goal, monthly_goal_progress


def build_week_view(
    base: list, week_dates: list[date], skipped_dates: set[date], today: date
) -> list[dict]:
    """Slide planned workouts forward past skipped days within the week.

    `base[i]` is the RoutineDay (or None) the WeeklySplit assigns to
    `week_dates[i]`. A skipped date keeps its workout queued for the next
    non-skipped day so a missed session isn't lost; overflow past the week's end
    is dropped (it resumes next week).
    """
    pending: list = []
    week_view: list[dict] = []
    for routine_day, d in zip(base, week_dates, strict=True):
        if routine_day is not None:
            pending.append(routine_day)
        is_skipped = d in skipped_dates
        effective = None if is_skipped else (pending.pop(0) if pending else None)
        week_view.append(
            {
                "date": d,
                "weekday_label": Weekday(d.weekday()).label,
                "routine_day": effective,
                "is_today": d == today,
                "is_skipped": is_skipped,
            }
        )
    return week_view


@login_required
def home(request):
    today = timezone.localdate()
    today_weekday = today.weekday()
    monday = today - timedelta(days=today_weekday)
    week_dates = [monday + timedelta(days=i) for i in range(7)]

    week_splits = (
        WeeklySplit.objects.for_user(request.user)
        .select_related("routine_day__routine")
        .order_by("weekday")
    )
    by_weekday = {w.weekday: w for w in week_splits}
    base = []
    for wd in range(7):
        w = by_weekday.get(wd)
        rd = w.routine_day if (w and w.routine_day_id) else None
        # An archived routine no longer drives the schedule.
        if rd is not None and rd.routine.is_archived:
            rd = None
        base.append(rd)

    skipped_dates = set(
        SkippedDay.objects.for_user(request.user)
        .filter(date__in=week_dates)
        .values_list("date", flat=True)
    )

    week_view = build_week_view(base, week_dates, skipped_dates, today)
    today_entry = week_view[today_weekday]

    # Active in-progress session
    in_progress = (
        WorkoutSession.objects.for_user(request.user)
        .filter(status=WorkoutStatus.IN_PROGRESS)
        .order_by("-started_at")
        .first()
    )

    recent_sessions = (
        WorkoutSession.objects.for_user(request.user)
        .order_by("-started_at")
        .select_related("source_routine_day__routine")[:5]
    )

    # PR highlights: most recently improved
    recent_prs = (
        PersonalRecord.objects.for_user(request.user)
        .select_related("exercise")
        .order_by("-achieved_at")[:5]
    )

    latest_metric = (
        UserMetricSnapshot.objects.for_user(request.user).order_by("-measured_at").first()
    )

    done_today = (
        WorkoutSession.objects.for_user(request.user)
        .filter(status=WorkoutStatus.FINISHED, started_at__date=today)
        .exists()
    )

    # Any active routine's days the user can start manually from the dashboard.
    startable_routines = (
        Routine.objects.for_user(request.user)
        .filter(is_archived=False)
        .prefetch_related("days")
        .order_by("name")
    )

    goal = current_goal(request.user, today)
    goal_progress = monthly_goal_progress(goal) if goal else []

    deload = deload_recommendation(request.user, today=today)

    return render(
        request,
        "dashboard/home.html",
        {
            "deload": deload,
            "today_routine_day": today_entry["routine_day"],
            "today_skipped": today_entry["is_skipped"],
            "in_progress": in_progress,
            "week_view": week_view,
            "recent_sessions": recent_sessions,
            "recent_prs": recent_prs,
            "latest_metric": latest_metric,
            "startable_routines": startable_routines,
            "done_today": done_today,
            "goal_progress": goal_progress,
        },
    )


@login_required
def progress(request):
    """Training analytics: weekly tonnage trend + this week's sets per muscle."""
    weekly = weekly_volume(request.user, weeks=8)
    max_vol = max((p.volume_kg for p in weekly), default=0) or 1
    weekly_rows = [
        {
            "week_start": p.week_start,
            "volume_kg": p.volume_kg,
            "sets": p.sets,
            "pct": int(round(p.volume_kg / max_vol * 100)),
        }
        for p in weekly
    ]

    muscles = sets_by_muscle(request.user)
    max_sets = max((m.sets for m in muscles), default=0) or 1
    muscle_rows = [
        {
            "muscle": m.muscle,
            "sets": m.sets,
            "volume_kg": m.volume_kg,
            "pct": int(round(m.sets / max_sets * 100)),
        }
        for m in muscles
    ]

    return render(
        request,
        "dashboard/progress.html",
        {
            "weekly_rows": weekly_rows,
            "muscle_rows": muscle_rows,
            "this_week_volume": weekly_rows[-1]["volume_kg"] if weekly_rows else 0,
            "this_week_sets": sum(m["sets"] for m in muscle_rows),
            "deload": deload_recommendation(request.user),
        },
    )
