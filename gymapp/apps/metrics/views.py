"""Metrics views: list snapshots, add new, edit profile baseline."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from datetime import timedelta

from gymapp.apps.exercises.models import MuscleGroup
from gymapp.apps.metrics.models import (
    FatigueAdjustment,
    MonthlyGoal,
    ReadinessSnapshot,
    UserMetricSnapshot,
)
from gymapp.services.fatigue import daily_advice, fatigue_table
from gymapp.services.goals import monthly_goal_progress
from gymapp.services.rehab import mobility_for_user


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
    snapshots = list(
        UserMetricSnapshot.objects.for_user(request.user).order_by("-measured_at")
    )
    height_cm = getattr(request.user.profile, "height_cm", None)
    rows = [{"snap": s, "bmi": s.bmi_for(height_cm)} for s in snapshots]
    return render(request, "metrics/list.html", {"rows": rows, "height_cm": height_cm})


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
            muscle_pct=_decimal_or_none(request.POST.get("muscle_pct")),
            visceral_fat=_decimal_or_none(request.POST.get("visceral_fat")),
            notes=request.POST.get("notes", "").strip(),
        )
        return redirect("metrics:list")
    return render(request, "metrics/create.html", {})


@login_required
def snapshot_edit(request: HttpRequest, snapshot_id: int) -> HttpResponse:
    snap = get_object_or_404(UserMetricSnapshot.objects.for_user(request.user), pk=snapshot_id)
    if request.method == "POST":
        weight = _decimal_or_none(request.POST.get("weight_kg"))
        if weight is None:
            return HttpResponseBadRequest("weight_kg required")
        snap.weight_kg = weight
        snap.body_fat_pct = _decimal_or_none(request.POST.get("body_fat_pct"))
        snap.muscle_pct = _decimal_or_none(request.POST.get("muscle_pct"))
        snap.visceral_fat = _decimal_or_none(request.POST.get("visceral_fat"))
        snap.notes = request.POST.get("notes", "").strip()
        snap.save()
        return redirect("metrics:list")
    return render(request, "metrics/edit.html", {"snap": snap})


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
        goal.target_bodyweight_kg = _decimal_or_none(request.POST.get("target_bodyweight_kg"))
        goal.save()
        return redirect("metrics:goals")
    return render(
        request,
        "metrics/goals.html",
        {"goal": goal, "progress": monthly_goal_progress(goal), "today": today},
    )


# ---------------------------------------------------------------------------
# Recovery / fatigue / readiness
# ---------------------------------------------------------------------------


def _clamp_1_5(raw, fallback: int = 3) -> int:
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return fallback
    return max(1, min(5, v))


@login_required
def recovery_home(request: HttpRequest) -> HttpResponse:
    today = timezone.localdate()
    advice = daily_advice(request.user, today)
    rows = fatigue_table(request.user, today)
    # Map muscle slug -> human name for the UI.
    muscle_labels = {m.slug: m.name for m in MuscleGroup.objects.all()}
    table = [
        {
            "muscle": r.muscle,
            "label": muscle_labels.get(r.muscle, r.muscle),
            "score": round(r.score, 1),
            "raw_sets": r.raw_sets,
            "pct": min(100, int(round(r.score / 15.0 * 100))),
        }
        for r in rows
    ]
    today_snap = ReadinessSnapshot.objects.for_user(request.user).filter(date=today).first()
    recent_snaps = (
        ReadinessSnapshot.objects.for_user(request.user)
        .filter(date__gte=today - timedelta(days=7), date__lte=today)
        .order_by("-date")
    )
    return render(
        request,
        "metrics/recovery.html",
        {
            "today": today,
            "advice": advice,
            "table": table,
            "today_snap": today_snap,
            "recent_snaps": recent_snaps,
            "mobility": mobility_for_user(request.user, per_region=2),
        },
    )


@login_required
def readiness_checkin(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    today = timezone.localdate()
    ReadinessSnapshot.objects.update_or_create(
        owner=request.user,
        date=today,
        defaults={
            "sleep_quality": _clamp_1_5(request.POST.get("sleep_quality")),
            "stress_level": _clamp_1_5(request.POST.get("stress_level")),
            "soreness_overall": _clamp_1_5(request.POST.get("soreness_overall")),
            "notes": request.POST.get("notes", "")[:200],
        },
    )
    nxt = request.POST.get("next") or "metrics:recovery"
    return redirect(nxt) if nxt.startswith("/") else redirect(nxt)


@login_required
def fatigue_adjust(request: HttpRequest, muscle_slug: str) -> HttpResponse:
    """Stack a +/- override on today's computed fatigue for one muscle.

    POST body: `delta=<float>`. A `delta=0` (or missing) removes any existing
    adjustment for today + muscle, so the user can "reset" back to the math.
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    today = timezone.localdate()
    raw = request.POST.get("delta", "0")
    try:
        delta = float(raw)
    except (TypeError, ValueError):
        return HttpResponseBadRequest("invalid delta")

    if delta == 0:
        FatigueAdjustment.objects.for_user(request.user).filter(
            date=today, muscle_slug=muscle_slug
        ).delete()
    else:
        existing = (
            FatigueAdjustment.objects.for_user(request.user)
            .filter(date=today, muscle_slug=muscle_slug)
            .first()
        )
        new_delta = (float(existing.delta) if existing else 0.0) + delta
        FatigueAdjustment.objects.update_or_create(
            owner=request.user,
            date=today,
            muscle_slug=muscle_slug,
            defaults={"delta": new_delta},
        )
    return redirect("metrics:recovery")
