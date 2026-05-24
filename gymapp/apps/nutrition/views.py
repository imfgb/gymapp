"""Nutrition page: today's calorie + macro target."""

from __future__ import annotations

from dataclasses import asdict

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from gymapp.apps.nutrition.models import SavedMeal, Supplement
from gymapp.services.nutrition import (
    COMMON_SUPPLEMENTS,
    MEAL_SLOTS,
    clean_food_preferences,
    daily_target_for_user,
    generate_meal,
    grouped_catalog,
)

# Display order for "Mis comidas": breakfast → lunch → dinner → snack.
_SLOT_ORDER = {key: i for i, (key, _, _) in enumerate(MEAL_SLOTS)}


@login_required
def home(request: HttpRequest) -> HttpResponse:
    profile = request.user.profile
    target, missing = daily_target_for_user(request.user)
    # Only today's meals — each day starts fresh, so eaten marks "reset" at
    # midnight without any background job.
    today = timezone.localdate()
    saved_meals = sorted(
        SavedMeal.objects.for_user(request.user).filter(created_at__date=today),
        key=lambda m: (_SLOT_ORDER.get(m.slot, 9), m.created_at),
    )
    return render(
        request,
        "nutrition/home.html",
        {
            "target": target,
            "missing": missing,
            "goal": profile.training_goal,
            "preference_count": len(profile.food_preferences or []),
            "saved_meals": saved_meals,
            "slot_choices": [(key, label) for key, label, _ in MEAL_SLOTS],
            "has_preferences": bool(profile.food_preferences),
            "supplements": Supplement.objects.for_user(request.user),
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
    meal = generate_meal(slot, target, profile.food_preferences)
    SavedMeal.objects.create(
        owner=request.user,
        slot=slot,
        foods=[asdict(i) for i in meal.items],
        calories=meal.calories,
        protein_g=meal.protein_g,
        carbs_g=meal.carbs_g,
        fat_g=meal.fat_g,
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


@login_required
def supplements(request: HttpRequest) -> HttpResponse:
    mine = Supplement.objects.for_user(request.user)
    taken_names = {s.name for s in mine}
    suggestions = [name for name in COMMON_SUPPLEMENTS if name not in taken_names]
    return render(
        request,
        "nutrition/supplements.html",
        {"supplements": mine, "suggestions": suggestions},
    )


@login_required
@require_POST
def supplement_add(request: HttpRequest) -> HttpResponse:
    name = (request.POST.get("name") or "").strip()[:60]
    if name:
        Supplement.objects.get_or_create(owner=request.user, name=name)
    return redirect("nutrition:supplements")


@login_required
@require_POST
def supplement_delete(request: HttpRequest, supp_id: int) -> HttpResponse:
    supp = get_object_or_404(Supplement.objects.for_user(request.user), pk=supp_id)
    supp.delete()
    return redirect("nutrition:supplements")


@login_required
@require_POST
def supplement_take(request: HttpRequest, supp_id: int) -> HttpResponse:
    supp = get_object_or_404(Supplement.objects.for_user(request.user), pk=supp_id)
    supp.last_taken_at = None if supp.taken_today else timezone.now()
    supp.save(update_fields=["last_taken_at", "updated_at"])
    return redirect("nutrition:home")
