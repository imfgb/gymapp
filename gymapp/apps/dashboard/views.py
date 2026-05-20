"""Dashboard: today's workout, weekly split, recent sessions, PR highlights."""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from gymapp.apps.metrics.models import UserMetricSnapshot
from gymapp.apps.prs.models import PersonalRecord
from gymapp.apps.routines.models import Weekday, WeeklySplit
from gymapp.apps.workouts.models import WorkoutSession, WorkoutStatus


@login_required
def home(request):
    today_weekday = timezone.localtime().weekday()

    # Today's planned routine day (if any)
    today_split = (
        WeeklySplit.objects.for_user(request.user)
        .filter(weekday=today_weekday)
        .select_related("routine_day__routine")
        .first()
    )

    # Active in-progress session
    in_progress = (
        WorkoutSession.objects.for_user(request.user)
        .filter(status=WorkoutStatus.IN_PROGRESS)
        .order_by("-started_at")
        .first()
    )

    # Whole week split
    week_splits = list(
        WeeklySplit.objects.for_user(request.user)
        .select_related("routine_day__routine")
        .order_by("weekday")
    )
    # Pad missing weekdays with placeholder objects so the template iterates 0..6
    by_weekday = {w.weekday: w for w in week_splits}
    week_view = []
    for wd in range(7):
        week_view.append(
            {
                "weekday": wd,
                "weekday_label": Weekday(wd).label,
                "split": by_weekday.get(wd),
                "is_today": wd == today_weekday,
            }
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
        UserMetricSnapshot.objects.for_user(request.user)
        .order_by("-measured_at")
        .first()
    )

    return render(
        request,
        "dashboard/home.html",
        {
            "today_split": today_split,
            "in_progress": in_progress,
            "week_view": week_view,
            "recent_sessions": recent_sessions,
            "recent_prs": recent_prs,
            "latest_metric": latest_metric,
        },
    )
