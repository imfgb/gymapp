"""User-facing routine CRUD + the generator entry point + WeeklySplit UI.

All entry points are owner-scoped through `Routine.objects.for_user(request.user)`
or `WeeklySplit.objects.for_user(...)`. Child rows (RoutineDay, RoutineExercise)
walk up to the routine for the same check.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from gymapp.apps.exercises.models import Equipment, Exercise, MuscleGroup
from gymapp.apps.routines.models import (
    Routine,
    RoutineDay,
    RoutineExercise,
    SkippedDay,
    TrainingBlock,
    Weekday,
    WeeklySplit,
)
from gymapp.apps.users.models import TrainingStyle
from gymapp.services import units
from gymapp.services.coaching.blocks import BLOCK_LENGTH_WEEKS, block_status
from gymapp.services.routine_generator import (
    PRESET_LABELS,
    SplitPreset,
    assign_weekly_split,
    generate_routine,
    preview_routine,
)


def _decimal_or_none(raw):
    """A negative target weight would prefill into a session and corrupt
    tonnage; drop negatives (the ORM doesn't run field validators)."""
    if raw in (None, ""):
        return None
    try:
        value = Decimal(raw)
    except (InvalidOperation, TypeError):
        return None
    return value if value >= 0 else None


def _int_or_default(raw, default):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Routine CRUD
# ---------------------------------------------------------------------------


@login_required
@require_GET
def routine_list(request: HttpRequest) -> HttpResponse:
    routines = (
        Routine.objects.for_user(request.user).filter(is_archived=False).order_by("-created_at")
    )
    return render(request, "routines/list.html", {"routines": routines})


@login_required
def routine_create(request: HttpRequest) -> HttpResponse:
    """Two-mode form: manual (just creates an empty routine) or generator.
    On POST, the `mode` field decides which path runs."""
    if request.method == "POST":
        mode = request.POST.get("mode", "manual")
        name = request.POST.get("name", "").strip()
        training_style = request.POST.get("training_style", request.user.profile.training_style)
        if not name:
            return HttpResponseBadRequest("Name is required")

        if mode == "generate":
            preset_raw = request.POST.get("preset", "ppl_6")
            try:
                preset = SplitPreset(preset_raw)
            except ValueError:
                return HttpResponseBadRequest("Invalid preset")
            routine = generate_routine(
                owner=request.user,
                preset=preset,
                training_style=training_style,
                name=name,
            )
            # Schedule it onto the week so the dashboard "Hoy"/"Esta semana"
            # work immediately without a manual trip to the split editor.
            assign_weekly_split(request.user, routine)
            messages.success(
                request,
                "Rutina generada y programada en tu semana. Ajusta los días si quieres.",
            )
        else:
            routine = Routine.objects.create(
                owner=request.user, name=name, training_style=training_style
            )
        return redirect("routines:detail", routine_id=routine.id)

    return render(
        request,
        "routines/create.html",
        {
            "training_styles": TrainingStyle.choices,
            "preset_choices": [
                (p.value, PRESET_LABELS[p]) for p in SplitPreset if p != SplitPreset.CUSTOM
            ],
            "default_style": request.user.profile.training_style,
        },
    )


@login_required
@require_POST
def routine_preview(request: HttpRequest) -> HttpResponse:
    """HTMX: returns a preview block for the chosen preset+style without
    persisting. Used inside the create form when the user is in 'generate'
    mode."""
    preset_raw = request.POST.get("preset", "ppl_6")
    training_style = request.POST.get("training_style", request.user.profile.training_style)
    try:
        preset = SplitPreset(preset_raw)
    except ValueError:
        return HttpResponseBadRequest("Invalid preset")

    days = preview_routine(preset=preset, training_style=training_style)
    return render(
        request,
        "routines/partials/_preview.html",
        {"days": days},
    )


@login_required
@require_GET
def routine_detail(request: HttpRequest, routine_id: int) -> HttpResponse:
    routine = get_object_or_404(
        Routine.objects.for_user(request.user).prefetch_related(
            "days__exercises__exercise__equipment"
        ),
        pk=routine_id,
    )
    from gymapp.services.rehab import avoided_exercise_ids

    visible_exercises = (
        Exercise.objects.visible_to(request.user).select_related("equipment").order_by("name")
    )
    return render(
        request,
        "routines/detail.html",
        {
            "routine": routine,
            "picker_exercises": visible_exercises,
            "equipment_choices": Equipment.objects.order_by("name"),
            "muscle_groups": MuscleGroup.objects.order_by("region", "name"),
            "avoid_ids": avoided_exercise_ids(request.user),
        },
    )


@login_required
def routine_edit(request: HttpRequest, routine_id: int) -> HttpResponse:
    routine = get_object_or_404(Routine.objects.for_user(request.user), pk=routine_id)
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            return HttpResponseBadRequest("Name is required")
        routine.name = name
        routine.training_style = request.POST.get("training_style", routine.training_style)
        routine.notes = request.POST.get("notes", "")
        routine.is_archived = "is_archived" in request.POST
        routine.save()
        return redirect("routines:detail", routine_id=routine.id)
    return render(
        request,
        "routines/edit.html",
        {"routine": routine, "training_styles": TrainingStyle.choices},
    )


@login_required
@require_POST
def routine_delete(request: HttpRequest, routine_id: int) -> HttpResponse:
    routine = get_object_or_404(Routine.objects.for_user(request.user), pk=routine_id)
    routine.delete()
    return redirect("routines:list")


# ---------------------------------------------------------------------------
# RoutineDay
# ---------------------------------------------------------------------------


@login_required
@require_POST
def day_add(request: HttpRequest, routine_id: int) -> HttpResponse:
    """HTMX: add a new RoutineDay to the routine. Returns the new day card."""
    routine = get_object_or_404(Routine.objects.for_user(request.user), pk=routine_id)
    label = request.POST.get("label", "").strip() or f"Día {routine.days.count() + 1}"
    if RoutineDay.objects.filter(routine=routine, label=label).exists():
        return HttpResponseBadRequest("Label already used in this routine")
    day = RoutineDay.objects.create(routine=routine, label=label, ordering=routine.days.count())
    return _render_day_card(request, day)


@login_required
@require_POST
def day_delete(request: HttpRequest, routine_id: int, day_id: int) -> HttpResponse:
    routine = get_object_or_404(Routine.objects.for_user(request.user), pk=routine_id)
    day = get_object_or_404(RoutineDay, pk=day_id, routine=routine)
    day.delete()
    return HttpResponse("", status=200)


# ---------------------------------------------------------------------------
# RoutineExercise
# ---------------------------------------------------------------------------


def _render_day_card(request, day: RoutineDay) -> HttpResponse:
    from gymapp.services.rehab import avoided_exercise_ids

    picker_exercises = (
        Exercise.objects.visible_to(request.user).select_related("equipment").order_by("name")
    )
    return render(
        request,
        "routines/partials/_day_card.html",
        {
            "day": day,
            "routine": day.routine,
            "picker_exercises": picker_exercises,
            "equipment_choices": Equipment.objects.order_by("name"),
            "muscle_groups": MuscleGroup.objects.order_by("region", "name"),
            "avoid_ids": avoided_exercise_ids(request.user),
        },
    )


@login_required
@require_POST
def exercise_add(request: HttpRequest, routine_id: int, day_id: int) -> HttpResponse:
    """HTMX: add a catalogue exercise to a routine day. Returns the day card."""
    routine = get_object_or_404(Routine.objects.for_user(request.user), pk=routine_id)
    day = get_object_or_404(RoutineDay, pk=day_id, routine=routine)

    slug = request.POST.get("slug", "").strip()
    if not slug:
        return HttpResponseBadRequest("Missing slug")
    exercise = get_object_or_404(Exercise.objects.visible_to(request.user), slug=slug)

    style = routine.training_style or request.user.profile.training_style
    is_compound = exercise.category == "compound"
    from gymapp.services.routine_generator import _rep_scheme

    sets, lo, hi = _rep_scheme(style, compound=is_compound)

    RoutineExercise.objects.create(
        routine_day=day,
        exercise=exercise,
        ordering=day.exercises.count(),
        target_sets=sets,
        target_reps_low=lo,
        target_reps_high=hi,
    )
    return _render_day_card(request, day)


@login_required
@require_POST
def exercise_add_custom(request: HttpRequest, routine_id: int, day_id: int) -> HttpResponse:
    """HTMX: create a per-user custom exercise and add it to the day. The new
    exercise is owner-scoped, so it also becomes searchable in future pickers."""
    from gymapp.services.exercise_library import create_custom_exercise
    from gymapp.services.routine_generator import _rep_scheme

    routine = get_object_or_404(Routine.objects.for_user(request.user), pk=routine_id)
    day = get_object_or_404(RoutineDay, pk=day_id, routine=routine)

    try:
        exercise = create_custom_exercise(
            request.user,
            name=request.POST.get("name", ""),
            equipment_slug=request.POST.get("equipment", "").strip(),
            primary_muscle_slugs=[
                s for s in request.POST.getlist("primary_muscles") if s.strip()
            ],
        )
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))

    style = routine.training_style or request.user.profile.training_style
    sets, lo, hi = _rep_scheme(style, compound=exercise.category == "compound")
    RoutineExercise.objects.create(
        routine_day=day,
        exercise=exercise,
        ordering=day.exercises.count(),
        target_sets=sets,
        target_reps_low=lo,
        target_reps_high=hi,
    )
    return _render_day_card(request, day)


@login_required
@require_POST
def exercise_update(
    request: HttpRequest, routine_id: int, day_id: int, rex_id: int
) -> HttpResponse:
    """HTMX: edit target_sets/reps/weight/rest_seconds of one RoutineExercise."""
    routine = get_object_or_404(Routine.objects.for_user(request.user), pk=routine_id)
    day = get_object_or_404(RoutineDay, pk=day_id, routine=routine)
    rex = get_object_or_404(
        RoutineExercise.objects.select_related("exercise__equipment"), pk=rex_id, routine_day=day
    )

    rex.target_sets = max(1, _int_or_default(request.POST.get("target_sets"), rex.target_sets))
    lo = max(1, _int_or_default(request.POST.get("target_reps_low"), rex.target_reps_low))
    hi = max(lo, _int_or_default(request.POST.get("target_reps_high"), rex.target_reps_high))
    rex.target_reps_low = lo
    rex.target_reps_high = hi
    target_weight = _decimal_or_none(request.POST.get("target_weight_kg"))
    rex.target_weight_kg = (
        units.to_kg(target_weight, rex.exercise.effective_weight_unit)
        if target_weight is not None
        else None
    )
    rest = request.POST.get("rest_seconds")
    parsed_rest = _int_or_default(rest, None) if rest else None
    rex.rest_seconds = max(0, parsed_rest) if parsed_rest is not None else None
    rex.notes = request.POST.get("notes", "")[:200]
    rex.save()
    return _render_day_card(request, day)


@login_required
@require_POST
def exercise_delete(
    request: HttpRequest, routine_id: int, day_id: int, rex_id: int
) -> HttpResponse:
    routine = get_object_or_404(Routine.objects.for_user(request.user), pk=routine_id)
    day = get_object_or_404(RoutineDay, pk=day_id, routine=routine)
    rex = get_object_or_404(RoutineExercise, pk=rex_id, routine_day=day)
    rex.delete()
    return _render_day_card(request, day)


@login_required
@require_POST
def exercise_move(
    request: HttpRequest, routine_id: int, day_id: int, rex_id: int
) -> HttpResponse:
    """Reorder a RoutineExercise within its day (bug #4). `direction` = up|down.

    Renumbers all siblings 0..n-1 in the new order, so it works even when legacy
    rows share the default ordering=0 (swapping two values alone wouldn't move them).
    """
    routine = get_object_or_404(Routine.objects.for_user(request.user), pk=routine_id)
    day = get_object_or_404(RoutineDay, pk=day_id, routine=routine)
    rex = get_object_or_404(RoutineExercise, pk=rex_id, routine_day=day)

    siblings = list(day.exercises.all())  # ordered by (ordering, id)
    idx = next((i for i, s in enumerate(siblings) if s.pk == rex.pk), None)
    direction = request.POST.get("direction")
    if idx is not None:
        if direction == "up" and idx > 0:
            siblings[idx - 1], siblings[idx] = siblings[idx], siblings[idx - 1]
        elif direction == "down" and idx < len(siblings) - 1:
            siblings[idx + 1], siblings[idx] = siblings[idx], siblings[idx + 1]
        for position, sibling in enumerate(siblings):
            sibling.ordering = position
        RoutineExercise.objects.bulk_update(siblings, ["ordering"])
    return _render_day_card(request, day)


# ---------------------------------------------------------------------------
# Weekly Split
# ---------------------------------------------------------------------------


@login_required
@require_GET
def weekly_split(request: HttpRequest) -> HttpResponse:
    splits = {
        w.weekday: w
        for w in WeeklySplit.objects.for_user(request.user).select_related("routine_day__routine")
    }
    rows = []
    for wd in range(7):
        rows.append(
            {
                "weekday": wd,
                "label": Weekday(wd).label,
                "split": splits.get(wd),
            }
        )
    # All RoutineDays this user owns, for the select boxes.
    all_days = (
        RoutineDay.objects.filter(routine__owner=request.user)
        .select_related("routine")
        .order_by("routine__name", "ordering")
    )
    # Active routines that actually have days, for the one-click "quick fill".
    routines = [
        r
        for r in Routine.objects.for_user(request.user)
        .filter(is_archived=False)
        .prefetch_related("days")
        .order_by("name")
        if r.days.exists()
    ]
    return render(
        request,
        "routines/weekly_split.html",
        {"rows": rows, "all_days": all_days, "routines": routines},
    )


def _resolve_owned_day(user, raw_day_id: str):
    """Return the user's RoutineDay for an id, or None for blank (rest day)."""
    raw_day_id = (raw_day_id or "").strip()
    if not raw_day_id:
        return None
    return get_object_or_404(RoutineDay, pk=raw_day_id, routine__owner=user)


@login_required
@require_POST
def weekly_split_assign(request: HttpRequest, weekday: int) -> HttpResponse:
    """Assign a single weekday (kept for direct/programmatic use)."""
    if weekday not in range(7):
        return HttpResponseBadRequest("weekday must be 0..6")

    routine_day = _resolve_owned_day(request.user, request.POST.get("routine_day", ""))
    WeeklySplit.objects.update_or_create(
        owner=request.user,
        weekday=weekday,
        defaults={"routine_day": routine_day},
    )
    return redirect("routines:weekly_split")


@login_required
@require_POST
def weekly_split_save(request: HttpRequest) -> HttpResponse:
    """Save the whole week in one submit. The editor posts `weekday_<n>` for
    each of the 7 days, so changing several rows and pressing one button no
    longer loses the unsaved ones."""
    for weekday in range(7):
        routine_day = _resolve_owned_day(request.user, request.POST.get(f"weekday_{weekday}", ""))
        WeeklySplit.objects.update_or_create(
            owner=request.user,
            weekday=weekday,
            defaults={"routine_day": routine_day},
        )
    messages.success(request, "Tu semana quedó guardada.")
    return redirect("routines:weekly_split")


@login_required
@require_POST
def apply_to_week(request: HttpRequest, routine_id: int) -> HttpResponse:
    """Spread one routine's days across the week (Mon-anchored), replacing the
    current schedule. Lets the user program any routine — generated or built by
    hand — into their week with one click."""
    routine = get_object_or_404(
        Routine.objects.for_user(request.user).prefetch_related("days"), pk=routine_id
    )
    if not routine.days.exists():
        messages.error(request, "Esta rutina no tiene días todavía.")
        return redirect("routines:detail", routine_id=routine.id)
    assign_weekly_split(request.user, routine)
    messages.success(request, f"“{routine.name}” quedó programada en tu semana.")
    return redirect("routines:weekly_split")


@login_required
@require_POST
def skip_today_toggle(request: HttpRequest) -> HttpResponse:
    """Toggle a 'no gym today' marker for the current date and return to the
    dashboard, which slides the week's planned workouts forward accordingly."""
    today = timezone.localdate()
    existing = SkippedDay.objects.for_user(request.user).filter(date=today).first()
    if existing:
        existing.delete()
    else:
        SkippedDay.objects.create(owner=request.user, date=today)
    return redirect("dashboard:home")


@login_required
def block(request: HttpRequest) -> HttpResponse:
    """Show the current 6-week block plan, or start a new one."""
    if request.method == "POST":
        style = request.POST.get("training_style") or request.user.profile.training_style
        if style not in TrainingStyle.values:
            return HttpResponseBadRequest("invalid training_style")
        TrainingBlock.objects.create(
            owner=request.user,
            training_style=style,
            started_on=timezone.localdate(),
            length_weeks=BLOCK_LENGTH_WEEKS,
        )
        return redirect("routines:block")

    current = TrainingBlock.objects.for_user(request.user).order_by("-started_on").first()
    status = (
        block_status(current.training_style, current.started_on, timezone.localdate())
        if current
        else None
    )
    return render(
        request,
        "routines/block.html",
        {
            "training_block": current,
            "status": status,
            "training_styles": TrainingStyle.choices,
            "default_style": request.user.profile.training_style,
        },
    )
