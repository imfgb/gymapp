"""Nutrition page: today's calorie + macro target."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from gymapp.services.nutrition import daily_target_for_user


@login_required
def home(request: HttpRequest) -> HttpResponse:
    target, missing = daily_target_for_user(request.user)
    return render(
        request,
        "nutrition/home.html",
        {
            "target": target,
            "missing": missing,
            "goal": request.user.profile.training_goal,
        },
    )
