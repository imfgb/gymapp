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
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from gymapp.apps.routines.models import RoutineDay, WeeklySplit
from gymapp.apps.workouts.models import ExerciseLog, SetLog, WorkoutSession, WorkoutStatus
from gymapp.services import units
from gymapp.services import workouts as workouts_service


def _decimal_or_none(raw):
    """Parse a weight. Negatives are invalid (the ORM skips full_clean, so a
    crafted POST would otherwise persist a negative weight → negative tonnage),
    so they're dropped rather than stored."""
    if raw in (None, ""):
        return None
    try:
        value = Decimal(raw)
    except (InvalidOperation, TypeError):
        return None
    return value if value >= 0 else None


def _int_or_none(raw):
    """Parse reps as a whole number. Reps are never fractional, so a decimal
    string (e.g. a pasted "2.5") is rounded rather than dropped. Negative reps
    are invalid (PositiveSmallIntegerField has no DB CHECK on SQLite/Postgres
    and the ORM skips validators) and are dropped."""
    if raw in (None, ""):
        return None
    try:
        value = int(round(float(raw)))
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _weight_to_kg(raw, exercise):
    """Parse a posted weight (in the exercise's display unit) into canonical kg."""
    value = _decimal_or_none(raw)
    if value is None:
        return None
    return units.to_kg(value, exercise.effective_weight_unit)


@login_required
@require_POST
def start(request: HttpRequest) -> HttpResponse:
    """Start a session from today's WeeklySplit, or from a specific RoutineDay
    (when `routine_day` is in POST), or ad-hoc.

    If the user already has an in-progress session, redirect to it instead of
    creating a second one.
    """
    active = (
        WorkoutSession.objects.for_user(request.user)
        .filter(status=WorkoutStatus.IN_PROGRESS)
        .first()
    )
    if active:
        return redirect("workouts:session", session_id=active.pk)

    routine_day = None
    raw_day_id = request.POST.get("routine_day")
    if raw_day_id:
        routine_day = get_object_or_404(RoutineDay, pk=raw_day_id, routine__owner=request.user)
    else:
        weekday = timezone.localtime().weekday()
        split = WeeklySplit.objects.for_user(request.user).filter(weekday=weekday).first()
        # Defense in depth: don't start a session from a stale split row that
        # still points at another user's routine day.
        if (
            split is not None
            and split.routine_day is not None
            and split.routine_day.routine.owner_id == request.user.id
        ):
            routine_day = split.routine_day

    # When started from the dashboard picker, make today's schedule reflect the
    # chosen routine so "Esta semana" stays in sync with what the user trained.
    if routine_day is not None and request.POST.get("set_today_split"):
        WeeklySplit.objects.update_or_create(
            owner=request.user,
            weekday=timezone.localtime().weekday(),
            defaults={"routine_day": routine_day},
        )

    session = workouts_service.start_session(request.user, routine_day=routine_day)
    return redirect("workouts:session", session_id=session.pk)


@login_required
@require_GET
def session(request: HttpRequest, session_id: int) -> HttpResponse:
    from gymapp.apps.exercises.models import Equipment, Exercise, MuscleGroup
    from gymapp.services.rehab import avoided_exercise_ids, suggested_swap

    sess = get_object_or_404(
        WorkoutSession.objects.for_user(request.user).prefetch_related(
            "exercise_logs__exercise__equipment",
            "exercise_logs__set_logs",
        ),
        pk=session_id,
    )
    picker_exercises = (
        Exercise.objects.visible_to(request.user)
        .select_related("equipment")
        .prefetch_related("primary_muscles")
        .order_by("name")
    )
    avoid_ids = avoided_exercise_ids(request.user)
    # Annotate each elog with a swap suggestion when its exercise is avoided.
    for elog in sess.exercise_logs.all():
        elog.swap_suggestion = (
            suggested_swap(elog.exercise, request.user)
            if elog.exercise_id in avoid_ids
            else None
        )

    context = {
        "session": sess,
        "progress": workouts_service.session_progress(sess),
        "rest_seconds_default": getattr(request.user.profile, "default_rest_seconds", 120),
        "picker_exercises": picker_exercises,
        "equipment_choices": Equipment.objects.order_by("name"),
        "muscle_groups": MuscleGroup.objects.order_by("region", "name"),
        # Set of exercise ids the user should avoid (active injuries).
        # The template uses this both for per-card warnings and picker badges.
        "avoid_ids": avoid_ids,
    }
    return render(request, "workouts/session.html", context)


@login_required
@require_POST
def complete_set_view(request: HttpRequest, session_id: int, set_id: int) -> HttpResponse:
    sess = _require_active_session(request.user, session_id)
    set_log = get_object_or_404(
        SetLog.objects.select_related("exercise_log__exercise__equipment"),
        pk=set_id,
        exercise_log__session=sess,
    )
    set_log = workouts_service.complete_set(
        set_log,
        weight_kg=_weight_to_kg(request.POST.get("weight_kg"), set_log.exercise_log.exercise),
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
            "rest_seconds_default": getattr(request.user.profile, "default_rest_seconds", 120),
        },
    )


@login_required
@require_POST
def update_set_view(request: HttpRequest, session_id: int, set_id: int) -> HttpResponse:
    sess = _require_active_session(request.user, session_id)
    set_log = get_object_or_404(
        SetLog.objects.select_related("exercise_log__exercise__equipment"),
        pk=set_id,
        exercise_log__session=sess,
    )
    set_log = workouts_service.update_set_values(
        set_log,
        weight_kg=_weight_to_kg(request.POST.get("weight_kg"), set_log.exercise_log.exercise),
        reps=_int_or_none(request.POST.get("reps")),
        rpe=_decimal_or_none(request.POST.get("rpe")),
    )
    return render(
        request,
        "workouts/partials/_set_row.html",
        {"set_log": set_log, "session": sess, "trigger_timer": False},
    )


@login_required
@require_GET
def swap_options_view(request: HttpRequest, session_id: int, elog_id: int) -> HttpResponse:
    """HTMX: render ranked substitute exercises for an ExerciseLog. Refuses (with
    a note) if any set is already completed, since swapping would misattribute
    performed reps."""
    from gymapp.services.substitution import ranked_alternatives

    sess = get_object_or_404(WorkoutSession.objects.for_user(request.user), pk=session_id)
    elog = get_object_or_404(
        ExerciseLog.objects.select_related("exercise__equipment"), pk=elog_id, session=sess
    )
    blocked = elog.set_logs.filter(completed_at__isnull=False).exists()
    alternatives = [] if blocked else ranked_alternatives(elog.exercise, user=request.user)
    return render(
        request,
        "workouts/partials/_swap_options.html",
        {"session": sess, "elog": elog, "alternatives": alternatives, "blocked": blocked},
    )


@login_required
@require_POST
def swap_exercise_view(request: HttpRequest, session_id: int, elog_id: int) -> HttpResponse:
    from gymapp.apps.exercises.models import Exercise

    sess = _require_active_session(request.user, session_id)
    elog = get_object_or_404(ExerciseLog, pk=elog_id, session=sess)

    new_slug = request.POST.get("to_slug")
    if not new_slug:
        return HttpResponseBadRequest("Missing to_slug")
    new_exercise = get_object_or_404(Exercise.objects.visible_to(request.user), slug=new_slug)
    try:
        workouts_service.swap_exercise(elog, new_exercise=new_exercise)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))

    elog.refresh_from_db()
    return _render_exercise_card(request, elog)


@login_required
@require_POST
def finish(request: HttpRequest, session_id: int) -> HttpResponse:
    sess = get_object_or_404(WorkoutSession.objects.for_user(request.user), pk=session_id)
    workouts_service.finish_session(sess)
    # The dashboard's done_today card already confirms completion, so no flash here.
    return redirect("dashboard:home")


@login_required
@require_GET
def history(request: HttpRequest) -> HttpResponse:
    sessions = (
        WorkoutSession.objects.for_user(request.user)
        .order_by("-started_at")
        .select_related("source_routine_day__routine")[:50]
    )
    active_session = next((s for s in sessions if s.status == WorkoutStatus.IN_PROGRESS), None)
    return render(
        request,
        "workouts/history.html",
        {"sessions": sessions, "active_session": active_session},
    )


# ---------------------------------------------------------------------------
# Live session editing (Phase 2: session-live-edit)
# ---------------------------------------------------------------------------


def _require_active_session(user, session_id: int) -> WorkoutSession:
    """Load an owned session and refuse if it's finished.

    A finished session is view-only (bug #10): completing/editing/swapping sets
    or adding exercises is rejected. `PermissionDenied` → a clean 403 (not 500).
    """
    sess = get_object_or_404(WorkoutSession.objects.for_user(user), pk=session_id)
    if not sess.is_active:
        raise PermissionDenied("Session is finished; it is view-only.")
    return sess


def _render_exercise_card(request, elog: ExerciseLog) -> HttpResponse:
    from gymapp.services.rehab import avoided_exercise_ids, suggested_swap

    avoid_ids = avoided_exercise_ids(request.user)
    elog.swap_suggestion = (
        suggested_swap(elog.exercise, request.user)
        if elog.exercise_id in avoid_ids
        else None
    )
    return render(
        request,
        "workouts/partials/_exercise_card.html",
        {
            "elog": elog,
            "session": elog.session,
            "avoid_ids": avoid_ids,
        },
    )


@login_required
@require_POST
def add_exercise_view(request: HttpRequest, session_id: int) -> HttpResponse:
    """HTMX: append a catalogue exercise to the session. Returns the new card."""
    from gymapp.apps.exercises.models import Exercise

    sess = _require_active_session(request.user, session_id)
    slug = request.POST.get("slug", "").strip()
    if not slug:
        return HttpResponseBadRequest("Missing slug")
    exercise = get_object_or_404(Exercise.objects.visible_to(request.user), slug=slug)
    try:
        sets_count = max(1, int(request.POST.get("sets_count", "3")))
    except ValueError:
        sets_count = 3

    elog = workouts_service.add_exercise_to_session(sess, exercise=exercise, sets_count=sets_count)
    return _render_exercise_card(request, elog)


@login_required
@require_POST
def add_custom_exercise_view(request: HttpRequest, session_id: int) -> HttpResponse:
    """HTMX: create a per-user custom Exercise and add it to the session in one shot."""
    sess = _require_active_session(request.user, session_id)
    name = request.POST.get("name", "").strip()
    equipment_slug = request.POST.get("equipment", "").strip()
    primary_muscle_slugs = [s for s in request.POST.getlist("primary_muscles") if s.strip()]
    try:
        sets_count = max(1, int(request.POST.get("sets_count", "3")))
    except ValueError:
        sets_count = 3

    try:
        _, elog = workouts_service.add_custom_exercise_and_use(
            sess,
            name=name,
            equipment_slug=equipment_slug,
            primary_muscle_slugs=primary_muscle_slugs,
            sets_count=sets_count,
            weight_unit=request.POST.get("weight_unit", ""),
        )
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))
    return _render_exercise_card(request, elog)


@login_required
@require_POST
def add_set_view(request: HttpRequest, session_id: int, elog_id: int) -> HttpResponse:
    """HTMX: append one empty SetLog and return the parent card."""
    sess = _require_active_session(request.user, session_id)
    elog = get_object_or_404(ExerciseLog, pk=elog_id, session=sess)
    workouts_service.add_set_to_exercise(elog)
    elog.refresh_from_db()
    return _render_exercise_card(request, elog)


@login_required
@require_POST
def add_warmups_view(request: HttpRequest, session_id: int, elog_id: int) -> HttpResponse:
    """HTMX: generate warm-up sets for an exercise from its working weight."""
    sess = _require_active_session(request.user, session_id)
    elog = get_object_or_404(ExerciseLog, pk=elog_id, session=sess)
    workouts_service.add_warmups_to_exercise(elog)
    elog.refresh_from_db()
    return _render_exercise_card(request, elog)


@login_required
@require_POST
def toggle_unit_view(request: HttpRequest, session_id: int, elog_id: int) -> HttpResponse:
    """HTMX: flip this exercise's weight display between kg and lb (#8). Safe
    anytime — weight is stored in kg, so only the display/entry unit changes."""
    sess = _require_active_session(request.user, session_id)
    elog = get_object_or_404(
        ExerciseLog.objects.select_related("exercise__equipment"), pk=elog_id, session=sess
    )
    exercise = elog.exercise
    exercise.weight_unit = units.other_unit(exercise.effective_weight_unit)
    exercise.save(update_fields=["weight_unit"])
    elog.refresh_from_db()
    return _render_exercise_card(request, elog)


@login_required
@require_POST
def delete_set_view(request: HttpRequest, session_id: int, set_id: int) -> HttpResponse:
    """HTMX: delete a SetLog and return the parent card."""
    sess = _require_active_session(request.user, session_id)
    set_log = get_object_or_404(SetLog, pk=set_id, exercise_log__session=sess)
    elog = set_log.exercise_log
    workouts_service.delete_set(set_log)
    elog.refresh_from_db()
    return _render_exercise_card(request, elog)


@login_required
@require_POST
def delete_exercise_log_view(request: HttpRequest, session_id: int, elog_id: int) -> HttpResponse:
    """HTMX: delete an entire exercise from the session. Returns empty body for
    hx-swap=outerHTML to remove the card."""
    sess = _require_active_session(request.user, session_id)
    elog = get_object_or_404(ExerciseLog, pk=elog_id, session=sess)
    workouts_service.delete_exercise_log(elog)
    return HttpResponse("", status=200)
