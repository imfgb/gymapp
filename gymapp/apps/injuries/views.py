"""Injuries CRUD + avoid-list management."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from gymapp.apps.exercises.models import Exercise
from gymapp.apps.injuries.models import BodyRegion, Injury, Severity


def _parse_date_or_today(raw):
    if not raw:
        return timezone.localdate()
    try:
        return timezone.datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return timezone.localdate()


def _parse_date_or_none(raw):
    if not raw:
        return None
    try:
        return timezone.datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


@login_required
@require_GET
def injury_list(request: HttpRequest) -> HttpResponse:
    qs = Injury.objects.for_user(request.user).prefetch_related("avoid_exercises__equipment")
    active = [i for i in qs if i.is_active]
    resolved = [i for i in qs if not i.is_active]
    return render(
        request,
        "injuries/list.html",
        {"active": active, "resolved": resolved},
    )


@login_required
def injury_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            return HttpResponseBadRequest("name required")
        injury = Injury.objects.create(
            owner=request.user,
            name=name[:120],
            body_region=request.POST.get("body_region", BodyRegion.OTHER),
            severity=request.POST.get("severity", Severity.MILD),
            started_on=_parse_date_or_today(request.POST.get("started_on")),
            resolved_on=_parse_date_or_none(request.POST.get("resolved_on")),
            notes=request.POST.get("notes", "")[:2000],
        )
        messages.success(request, f"Lesión “{injury.name}” registrada.")
        return redirect("injuries:edit", injury_id=injury.id)
    return render(
        request,
        "injuries/form.html",
        {
            "injury": None,
            "body_regions": BodyRegion.choices,
            "severities": Severity.choices,
            "today": timezone.localdate(),
        },
    )


@login_required
def injury_edit(request: HttpRequest, injury_id: int) -> HttpResponse:
    injury = get_object_or_404(Injury.objects.for_user(request.user), pk=injury_id)
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            return HttpResponseBadRequest("name required")
        injury.name = name[:120]
        injury.body_region = request.POST.get("body_region", injury.body_region)
        injury.severity = request.POST.get("severity", injury.severity)
        injury.started_on = _parse_date_or_today(request.POST.get("started_on"))
        injury.resolved_on = _parse_date_or_none(request.POST.get("resolved_on"))
        injury.notes = request.POST.get("notes", "")[:2000]
        injury.save()
        messages.success(request, "Lesión actualizada.")
        return redirect("injuries:edit", injury_id=injury.id)

    from gymapp.services.rehab import mobility_for_region

    visible_exercises = (
        Exercise.objects.visible_to(request.user)
        .select_related("equipment")
        .order_by("name")
    )
    return render(
        request,
        "injuries/form.html",
        {
            "injury": injury,
            "body_regions": BodyRegion.choices,
            "severities": Severity.choices,
            "today": timezone.localdate(),
            "all_exercises": visible_exercises,
            "avoid_ids": set(injury.avoid_exercises.values_list("id", flat=True)),
            "mobility_for_region": mobility_for_region(injury.body_region, limit=4),
        },
    )


@login_required
@require_POST
def injury_toggle_resolved(request: HttpRequest, injury_id: int) -> HttpResponse:
    injury = get_object_or_404(Injury.objects.for_user(request.user), pk=injury_id)
    if injury.is_active:
        injury.resolved_on = timezone.localdate()
        msg = "Marcada como resuelta."
    else:
        injury.resolved_on = None
        msg = "Marcada como activa otra vez."
    injury.save()
    messages.success(request, msg)
    return redirect("injuries:list")


@login_required
@require_POST
def injury_delete(request: HttpRequest, injury_id: int) -> HttpResponse:
    injury = get_object_or_404(Injury.objects.for_user(request.user), pk=injury_id)
    injury.delete()
    messages.success(request, "Lesión borrada.")
    return redirect("injuries:list")


@login_required
@require_POST
def avoid_add(request: HttpRequest, injury_id: int) -> HttpResponse:
    """Add one exercise to this injury's avoid list (by slug)."""
    injury = get_object_or_404(Injury.objects.for_user(request.user), pk=injury_id)
    slug = request.POST.get("slug", "").strip()
    if not slug:
        return HttpResponseBadRequest("slug required")
    exercise = get_object_or_404(Exercise.objects.visible_to(request.user), slug=slug)
    injury.avoid_exercises.add(exercise)
    return redirect("injuries:edit", injury_id=injury.id)


@login_required
@require_POST
def avoid_remove(request: HttpRequest, injury_id: int, exercise_id: int) -> HttpResponse:
    injury = get_object_or_404(Injury.objects.for_user(request.user), pk=injury_id)
    exercise = get_object_or_404(Exercise.objects.visible_to(request.user), pk=exercise_id)
    injury.avoid_exercises.remove(exercise)
    return redirect("injuries:edit", injury_id=injury.id)
