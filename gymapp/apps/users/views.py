"""Onboarding view — collects the minimum profile data in one pass."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from gymapp.apps.metrics.models import UserMetricSnapshot
from gymapp.apps.users.models import ActivityLevel, Sex, TrainingGoal, TrainingStyle


@login_required
def onboarding(request: HttpRequest) -> HttpResponse:
    profile = request.user.profile
    if request.method == "POST":
        try:
            profile.height_cm = int(request.POST.get("height_cm") or 0) or None
        except (TypeError, ValueError):
            return HttpResponseBadRequest("invalid height_cm")
        if not profile.height_cm:
            return HttpResponseBadRequest("height_cm required")
        profile.date_of_birth = request.POST.get("date_of_birth") or None
        if not profile.date_of_birth:
            return HttpResponseBadRequest("date_of_birth required")
        sex = request.POST.get("sex") or ""
        if sex not in (Sex.MALE, Sex.FEMALE):
            return HttpResponseBadRequest("sex required")
        profile.sex = sex
        profile.activity_level = request.POST.get("activity_level", profile.activity_level)
        profile.training_style = request.POST.get("training_style", profile.training_style)
        profile.training_goal = request.POST.get("training_goal", profile.training_goal)
        profile.onboarded_at = timezone.now()
        profile.save()

        # Optional initial weight -> first body snapshot.
        raw_weight = request.POST.get("weight_kg")
        if raw_weight:
            try:
                weight = Decimal(raw_weight)
            except (InvalidOperation, TypeError):
                weight = None
            if weight is not None and weight > 0:
                UserMetricSnapshot.objects.create(
                    owner=request.user,
                    measured_at=timezone.now(),
                    weight_kg=weight,
                    notes="Inicial (onboarding)",
                )

        messages.success(request, f"¡Bienvenido{'' if profile.sex != 'female' else 'a'}, ya está listo tu perfil!")
        return redirect("dashboard:home")

    return render(
        request,
        "users/onboarding.html",
        {
            "profile": profile,
            "training_styles": TrainingStyle.choices,
            "training_goals": TrainingGoal.choices,
            "sexes": Sex.choices,
            "activity_levels": ActivityLevel.choices,
        },
    )


@login_required
@require_POST
def onboarding_skip(request: HttpRequest) -> HttpResponse:
    """Escape hatch: mark profile complete with defaults so the user can
    explore the app without filling everything now. They can fill it later
    from /metrics/profile/."""
    profile = request.user.profile
    if not profile.height_cm:
        profile.height_cm = 170
    if not profile.sex:
        profile.sex = Sex.MALE
    if not profile.date_of_birth:
        profile.date_of_birth = timezone.localdate().replace(year=timezone.localdate().year - 30)
    profile.onboarded_at = timezone.now()
    profile.save()
    messages.info(
        request,
        "Saltaste el onboarding con valores por defecto. Edítalos en tu perfil cuando puedas.",
    )
    return redirect("dashboard:home")
