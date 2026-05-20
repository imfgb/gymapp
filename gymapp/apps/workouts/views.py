"""Workouts views.

URL-shape:
    POST /workouts/start/                          -> create session, redirect to /workouts/<id>/
    GET  /workouts/<id>/                            -> full session page
    POST /workouts/<id>/sets/<set_id>/complete/    -> HTMX partial (set row + timer)
    POST /workouts/<id>/sets/<set_id>/update/      -> HTMX partial (set row)
    POST /workouts/<id>/exercises/<elog_id>/swap/  -> HTMX partial (exercise card)
    POST /workouts/<id>/finish/                    -> redirect to /workouts/
    GET  /workouts/                                -> history list

Owner scoping is enforced via `WorkoutSession.objects.for_user(request.user)`
plus `get_object_or_404`. Any view that loads a child row (SetLog,
ExerciseLog) walks up to the session and re-checks.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from gymapp.apps.routines.models import RoutineDay, WeeklySplit
from gymapp.apps.workouts.models import ExerciseLog, SetLog, WorkoutSession
from gymapp.services import workouts as workouts_service


def _decimal_or_none(raw):
    if raw in (None, ""):
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, TypeError):
        return None


def _int_or_none(raw):
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


@login_required
@require_POST
def start(request: HttpRequest) -> HttpResponse:
    """Start a session from today's WeeklySplit, or from a specific RoutineDay
    (when `routine_day` is in POST), or ad-hoc."""
    routine_day = None
    raw_day_id = request.POST.get("routine_day")
    if raw_day_id:
        routine_day = get_object_or_404(
            RoutineDay, pk=raw_day_id, routine__owner=request.user
        )
    else:
        weekday = timezone.localtime().weekday()
        split = WeeklySplit.objects.for_user(request.user).filter(weekday=weekday).first()
        if split is not None:
            routine_day = split.routine_day
    session = workouts_service.start_session(request.user, routine_day=routine_day)
    return redirect("workouts:session", session_id=session.pk)


@login_required
@require_GET
def session(request: HttpRequest, session_id: int) -> HttpResponse:
    sess = get_object_or_404(
        WorkoutSession.objects.for_user(request.user).prefetch_related(
            "exercise_logs__exercise",
            "exercise_logs__set_logs",
        ),
        pk=session_id,
    )
    context = {
        "session": sess,
        "progress": workouts_service.session_progress(sess),
        "rest_seconds_default": getattr(request.user.profile, "default_rest_seconds", 120),
    }
    return render(request, "workouts/session.html", context)


@login_required
@require_POST
def complete_set_view(
    request: HttpRequest, session_id: int, set_id: int
) -> HttpResponse:
    sess = get_object_or_404(
        WorkoutSession.objects.for_user(request.user), pk=session_id
    )
    set_log = get_object_or_404(
        SetLog, pk=set_id, exercise_log__session=sess
    )
    set_log = workouts_service.complete_set(
        set_log,
        weight_kg=_decimal_or_none(request.POST.get("weight_kg")),
        reps=_int_or_none(request.POST.get("reps")),
        rpe=_decimal_or_none(request.POST.get("rpe")),
    )
    return render(
        request,
        "workouts/partials/_set_row.html",
        {
            "set_log": set_log,
            "session": sess,
            "trigger_timer": True,
            "rest_seconds_default": getattr(
                request.user.profile, "default_rest_seconds", 120
            ),
        },
    )


@login_required
@require_POST
def update_set_view(
    request: HttpRequest, session_id: int, set_id: int
) -> HttpResponse:
    sess = get_object_or_404(
        WorkoutSession.objects.for_user(request.user), pk=session_id
    )
    set_log = get_object_or_404(
        SetLog, pk=set_id, exercise_log__session=sess
    )
    set_log = workouts_service.update_set_values(
        set_log,
        weight_kg=_decimal_or_none(request.POST.get("weight_kg")),
        reps=_int_or_none(request.POST.get("reps")),
        rpe=_decimal_or_none(request.POST.get("rpe")),
    )
    return render(
        request,
        "workouts/partials/_set_row.html",
        {"set_log": set_log, "session": sess, "trigger_timer": False},
    )


@login_required
@require_POST
def swap_exercise_view(
    request: HttpRequest, session_id: int, elog_id: int
) -> HttpResponse:
    from gymapp.apps.exercises.models import Exercise

    sess = get_object_or_404(
        WorkoutSession.objects.for_user(request.user), pk=session_id
    )
    elog = get_object_or_404(ExerciseLog, pk=elog_id, session=sess)

    new_slug = request.POST.get("to_slug")
    if not new_slug:
        return HttpResponseBadRequest("Missing to_slug")
    new_exercise = get_object_or_404(
        Exercise.objects.visible_to(request.user), slug=new_slug
    )
    try:
        workouts_service.swap_exercise(elog, new_exercise=new_exercise)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))

    elog.refresh_from_db()
    return render(
        request,
        "workouts/partials/_exercise_card.html",
        {"elog": elog, "session": sess},
    )


@login_required
@require_POST
def finish(request: HttpRequest, session_id: int) -> HttpResponse:
    sess = get_object_or_404(
        WorkoutSession.objects.for_user(request.user), pk=session_id
    )
    workouts_service.finish_session(sess)
    return redirect("workouts:history")


@login_required
@require_GET
def history(request: HttpRequest) -> HttpResponse:
    sessions = (
        WorkoutSession.objects.for_user(request.user)
        .order_by("-started_at")
        .select_related("source_routine_day__routine")[:50]
    )
    return render(request, "workouts/history.html", {"sessions": sessions})
