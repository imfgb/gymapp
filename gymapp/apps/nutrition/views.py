"""Nutrition page: today's calorie + macro target."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from gymapp.services.nutrition import (
    clean_food_preferences,
    daily_target_for_user,
    grouped_catalog,
)


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
            "preference_count": len(request.user.profile.food_preferences or []),
        },
    )


@login_required
def preferences(request: HttpRequest) -> HttpResponse:
    profile = request.user.profile
    if request.method == "POST":
        profile.food_preferences = clean_food_preferences(request.POST.getlist("food"))
        profile.save(update_fields=["food_preferences", "updated_at"])
        return redirect("nutrition:home")
    return render(
        request,
        "nutrition/preferences.html",
        {"catalog": grouped_catalog(profile.food_preferences)},
    )
