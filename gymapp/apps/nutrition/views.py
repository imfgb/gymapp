"""Nutrition page: today's calorie + macro target."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from gymapp.apps.nutrition.models import SavedMeal
from gymapp.services.nutrition import (
    MEAL_SLOTS,
    build_meal_plan,
    clean_food_preferences,
    daily_target_for_user,
    generate_meal,
    grouped_catalog,
)


@login_required
def home(request: HttpRequest) -> HttpResponse:
    profile = request.user.profile
    target, missing = daily_target_for_user(request.user)
    meal_plan = build_meal_plan(target, profile.food_preferences) if target else []
    saved_meals = list(SavedMeal.objects.for_user(request.user)[:20])
    return render(
        request,
        "nutrition/home.html",
        {
            "target": target,
            "missing": missing,
            "goal": profile.training_goal,
            "preference_count": len(profile.food_preferences or []),
            "meal_plan": meal_plan,
            "saved_meals": saved_meals,
            "slot_choices": [(key, label) for key, label, _ in MEAL_SLOTS],
            "has_preferences": bool(profile.food_preferences),
        },
    )


@login_required
@require_POST
def generate_meal_view(request: HttpRequest) -> HttpResponse:
    profile = request.user.profile
    target, _ = daily_target_for_user(request.user)
    if target is None:
        return HttpResponseBadRequest("Completa tu perfil para generar comidas.")
    slot = request.POST.get("slot")
    if slot not in SavedMeal.Slot.values:
        return HttpResponseBadRequest("slot inválido")
    foods, macros = generate_meal(slot, target, profile.food_preferences)
    SavedMeal.objects.create(
        owner=request.user,
        slot=slot,
        foods=foods,
        calories=macros.calories,
        protein_g=macros.protein_g,
        carbs_g=macros.carbs_g,
        fat_g=macros.fat_g,
    )
    return redirect("nutrition:home")


@login_required
@require_POST
def meal_mark_done(request: HttpRequest, meal_id: int) -> HttpResponse:
    meal = get_object_or_404(SavedMeal.objects.for_user(request.user), pk=meal_id)
    meal.eaten_at = None if meal.eaten_at else timezone.now()
    meal.save(update_fields=["eaten_at", "updated_at"])
    return redirect("nutrition:home")


@login_required
@require_POST
def meal_delete(request: HttpRequest, meal_id: int) -> HttpResponse:
    meal = get_object_or_404(SavedMeal.objects.for_user(request.user), pk=meal_id)
    meal.delete()
    return redirect("nutrition:home")


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
