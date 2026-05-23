"""Metrics views: list snapshots, add new, edit profile baseline."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from gymapp.apps.metrics.models import MonthlyGoal, UserMetricSnapshot
from gymapp.services.goals import monthly_goal_progress


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
        return int(Decimal(raw))
    except (InvalidOperation, TypeError, ValueError):
        return None


@login_required
@require_GET
def snapshot_list(request: HttpRequest) -> HttpResponse:
    snapshots = UserMetricSnapshot.objects.for_user(request.user).order_by("-measured_at")
    return render(request, "metrics/list.html", {"snapshots": snapshots})


@login_required
def snapshot_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        weight = _decimal_or_none(request.POST.get("weight_kg"))
        if weight is None:
            return HttpResponseBadRequest("weight_kg required")
        UserMetricSnapshot.objects.create(
            owner=request.user,
            measured_at=timezone.now(),
            weight_kg=weight,
            body_fat_pct=_decimal_or_none(request.POST.get("body_fat_pct")),
            notes=request.POST.get("notes", "").strip(),
        )
        return redirect("metrics:list")
    return render(request, "metrics/create.html", {})


@login_required
def snapshot_delete(request: HttpRequest, snapshot_id: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    snapshot = get_object_or_404(UserMetricSnapshot.objects.for_user(request.user), pk=snapshot_id)
    snapshot.delete()
    return redirect("metrics:list")


@login_required
def profile_edit(request: HttpRequest) -> HttpResponse:
    profile = request.user.profile
    if request.method == "POST":
        height = request.POST.get("height_cm")
        dob = request.POST.get("date_of_birth")
        try:
            profile.height_cm = int(height) if height else None
        except ValueError:
            return HttpResponseBadRequest("invalid height_cm")
        profile.date_of_birth = dob or None
        profile.sex = request.POST.get("sex") or ""
        profile.activity_level = request.POST.get("activity_level", profile.activity_level)
        profile.training_style = request.POST.get("training_style", profile.training_style)
        profile.training_goal = request.POST.get("training_goal", profile.training_goal)
        try:
            profile.default_rest_seconds = int(
                request.POST.get("default_rest_seconds") or profile.default_rest_seconds
            )
        except ValueError:
            return HttpResponseBadRequest("invalid default_rest_seconds")
        profile.save()
        return redirect("metrics:profile")
    from gymapp.apps.users.models import ActivityLevel, Sex, TrainingGoal, TrainingStyle

    return render(
        request,
        "metrics/profile.html",
        {
            "profile": profile,
            "training_styles": TrainingStyle.choices,
            "training_goals": TrainingGoal.choices,
            "sexes": Sex.choices,
            "activity_levels": ActivityLevel.choices,
        },
    )


@login_required
def goal_edit(request: HttpRequest) -> HttpResponse:
    """Upsert the current month's goal and show progress against it."""
    today = timezone.localdate()
    goal, _ = MonthlyGoal.objects.get_or_create(
        owner=request.user, year=today.year, month=today.month
    )
    if request.method == "POST":
        goal.target_sessions = _int_or_none(request.POST.get("target_sessions"))
        goal.target_volume_kg = _decimal_or_none(request.POST.get("target_volume_kg"))
        goal.target_bodyweight_kg = _decimal_or_none(request.POST.get("target_bodyweight_kg"))
        goal.save()
        return redirect("metrics:goals")
    return render(
        request,
        "metrics/goals.html",
        {"goal": goal, "progress": monthly_goal_progress(goal), "today": today},
    )
