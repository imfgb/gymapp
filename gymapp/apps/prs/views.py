"""PRs views: list, per-exercise detail, manual edit/create."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from gymapp.apps.exercises.models import Exercise
from gymapp.apps.prs.models import PersonalRecord, PRSource
from gymapp.services import units


@login_required
@require_GET
def pr_list(request: HttpRequest) -> HttpResponse:
    prs = (
        PersonalRecord.objects.for_user(request.user)
        .select_related("exercise")
        .order_by("exercise__name", "reps")
    )
    # group by exercise for the template
    grouped: dict = {}
    for pr in prs:
        grouped.setdefault(pr.exercise, []).append(pr)
    return render(request, "prs/list.html", {"grouped": grouped.items()})


@login_required
@require_GET
def pr_detail(request: HttpRequest, slug: str) -> HttpResponse:
    exercise = get_object_or_404(Exercise.objects.visible_to(request.user), slug=slug)
    prs = PersonalRecord.objects.for_user(request.user).filter(exercise=exercise).order_by("reps")
    return render(request, "prs/detail.html", {"exercise": exercise, "prs": prs})


@login_required
def pr_edit(request: HttpRequest, pr_id: int) -> HttpResponse:
    pr = get_object_or_404(PersonalRecord.objects.for_user(request.user), pk=pr_id)
    if request.method == "POST":
        try:
            pr.weight_kg = units.to_kg(Decimal(request.POST["weight_kg"]), pr.exercise.effective_weight_unit)
            pr.reps = int(request.POST["reps"])
        except (KeyError, ValueError, InvalidOperation):
            return HttpResponseBadRequest("Invalid weight/reps")
        pr.source = PRSource.MANUAL
        pr.source_set = None
        pr.achieved_at = timezone.now()
        pr.save()
        return redirect("prs:detail", slug=pr.exercise.slug)
    return render(request, "prs/edit.html", {"pr": pr})


@login_required
def pr_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        try:
            exercise = Exercise.objects.visible_to(request.user).get(slug=request.POST["exercise"])
            weight_kg = units.to_kg(Decimal(request.POST["weight_kg"]), exercise.effective_weight_unit)
            reps = int(request.POST["reps"])
        except (KeyError, ValueError, InvalidOperation, Exercise.DoesNotExist):
            return HttpResponseBadRequest("Invalid input")
        pr, _ = PersonalRecord.objects.update_or_create(
            owner=request.user,
            exercise=exercise,
            reps=reps,
            defaults={
                "weight_kg": weight_kg,
                "source": PRSource.MANUAL,
                "source_set": None,
                "achieved_at": timezone.now(),
            },
        )
        return redirect("prs:detail", slug=pr.exercise.slug)

    exercises = Exercise.objects.visible_to(request.user).order_by("name")
    return render(request, "prs/create.html", {"exercises": exercises})


@login_required
@require_POST
def pr_delete(request: HttpRequest, pr_id: int) -> HttpResponse:
    pr = get_object_or_404(PersonalRecord.objects.for_user(request.user), pk=pr_id)
    exercise_slug = pr.exercise.slug
    pr.delete()
    return redirect("prs:detail", slug=exercise_slug)
