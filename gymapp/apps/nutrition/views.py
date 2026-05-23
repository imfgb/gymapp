"""Nutrition page: today's calorie + macro target."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from gymapp.services.nutrition import (
    build_meal_plan,
    clean_food_preferences,
    daily_target_for_user,
    grouped_catalog,
)


@login_required
def home(request: HttpRequest) -> HttpResponse:
    profile = request.user.profile
    target, missing = daily_target_for_user(request.user)
    meal_plan = build_meal_plan(target, profile.food_preferences) if target else []
    return render(
        request,
        "nutrition/home.html",
        {
            "target": target,
            "missing": missing,
            "goal": profile.training_goal,
            "preference_count": len(profile.food_preferences or []),
            "meal_plan": meal_plan,
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
