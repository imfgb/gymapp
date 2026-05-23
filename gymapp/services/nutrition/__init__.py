"""Nutrition service — Phase 3.

Deterministic daily energy + macro targets:

- **BMR** via Mifflin-St Jeor.
- **TDEE** = BMR × activity factor (selectable per user).
- **Calorie target** = TDEE × a goal multiplier (cut / bulk / recomp / …).
- **Macros** protein-first by bodyweight, fat floor by bodyweight, carbs fill
  the remaining calories.

`recommend()` is the AI seam (Protocol): a future `LLMStrategy` can replace the
deterministic implementation without touching `daily_target_for_user` or the
views. No AI in MVP (CLAUDE.md §15).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from django.utils import timezone

# Standard Harris/Mifflin activity multipliers.
ACTIVITY_FACTORS: dict[str, float] = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}
DEFAULT_ACTIVITY_FACTOR = ACTIVITY_FACTORS["moderate"]

# Calorie adjustment relative to maintenance (TDEE), keyed by training goal.
GOAL_CALORIE_MULTIPLIER: dict[str, float] = {
    "cut": 0.80,
    "bulk": 1.10,
    "hypertrophy": 1.10,
    "strength": 1.05,
    "recomposition": 1.00,
    "maintain": 1.00,
}

PROTEIN_G_PER_KG = 2.0
PROTEIN_G_PER_KG_CUT = 2.2  # higher on a deficit to spare lean mass
FAT_G_PER_KG = 0.8

# Curated food catalogue: English slug (domain) → Spanish label (UI). Grouped by
# macro role so the meal-slot scaffolding can pull a protein + carb + veg + fat
# from the user's liked items. Preferences are stored on `Profile` as a flat
# list of these slugs (no DB catalogue needed for a deterministic stub plan).
FOOD_CATALOG: dict[str, list[tuple[str, str]]] = {
    "protein": [
        # whole-food animal
        ("chicken", "Pollo"),
        ("beef", "Res"),
        ("lean_beef", "Bistec magro"),
        ("ground_beef", "Carne molida magra"),
        ("eggs", "Huevo"),
        ("egg_whites", "Claras de huevo"),
        ("fish", "Pescado"),
        ("salmon", "Salmón"),
        ("tuna", "Atún"),
        ("sardines", "Sardinas"),
        ("pork", "Cerdo"),
        ("turkey", "Pavo"),
        ("turkey_ham", "Jamón de pavo"),
        ("shrimp", "Camarón"),
        ("greek_yogurt", "Yogur griego"),
        ("cottage_cheese", "Requesón"),
        # supplements
        ("whey", "Proteína whey"),
        ("whey_concentrate", "Whey concentrada"),
        ("whey_isolate", "Whey aislada"),
        ("casein", "Caseína"),
        # plant-based
        ("tofu", "Tofu"),
        ("tempeh", "Tempeh"),
        ("seitan", "Seitán"),
        ("edamame", "Edamame"),
        ("soy_protein", "Proteína de soya"),
        ("pea_protein", "Proteína de chícharo"),
    ],
    "carb": [
        ("rice", "Arroz"),
        ("brown_rice", "Arroz integral"),
        ("oats", "Avena"),
        ("potato", "Papa"),
        ("sweet_potato", "Camote"),
        ("pasta", "Pasta"),
        ("bread", "Pan"),
        ("whole_wheat_bread", "Pan integral"),
        ("tortilla", "Tortilla"),
        ("corn", "Elote"),
        ("beans", "Frijoles"),
        ("lentils", "Lentejas"),
        ("chickpeas", "Garbanzos"),
        ("quinoa", "Quinoa"),
        ("fruit", "Fruta"),
        ("banana", "Plátano"),
        ("rice_cakes", "Tortitas de arroz"),
        ("granola", "Granola"),
        ("honey", "Miel"),
    ],
    "vegetable": [
        ("broccoli", "Brócoli"),
        ("spinach", "Espinaca"),
        ("kale", "Kale"),
        ("lettuce", "Lechuga"),
        ("tomato", "Jitomate"),
        ("carrot", "Zanahoria"),
        ("zucchini", "Calabacita"),
        ("pepper", "Pimiento"),
        ("cucumber", "Pepino"),
        ("onion", "Cebolla"),
        ("mushroom", "Champiñón"),
        ("green_beans", "Ejotes"),
        ("asparagus", "Espárragos"),
        ("nopal", "Nopal"),
    ],
    "fat": [
        ("avocado", "Aguacate"),
        ("olive_oil", "Aceite de oliva"),
        ("coconut_oil", "Aceite de coco"),
        ("nuts", "Nueces"),
        ("walnuts", "Nueces de Castilla"),
        ("almonds", "Almendras"),
        ("peanut_butter", "Crema de cacahuate"),
        ("almond_butter", "Crema de almendra"),
        ("chia", "Chía"),
        ("flax", "Linaza"),
        ("cheese", "Queso"),
        ("dark_chocolate", "Chocolate amargo"),
        ("egg_yolk", "Yema de huevo"),
    ],
}

FOOD_CATEGORY_LABELS: dict[str, str] = {
    "protein": "Proteínas",
    "carb": "Carbohidratos",
    "vegetable": "Verduras",
    "fat": "Grasas",
}

_FOOD_LABELS: dict[str, str] = {
    slug: label for items in FOOD_CATALOG.values() for slug, label in items
}


def all_food_slugs() -> set[str]:
    return set(_FOOD_LABELS)


def food_label(slug: str) -> str:
    return _FOOD_LABELS.get(slug, slug)


def grouped_catalog(selected: list[str] | None = None) -> list[dict]:
    """Catalogue grouped by category for rendering, marking selected items."""
    chosen = set(selected or [])
    return [
        {
            "key": key,
            "label": FOOD_CATEGORY_LABELS[key],
            "items": [
                {"slug": slug, "label": label, "selected": slug in chosen}
                for slug, label in items
            ],
        }
        for key, items in FOOD_CATALOG.items()
    ]


def clean_food_preferences(slugs) -> list[str]:
    """Keep only known slugs, deduped, in catalogue order."""
    chosen = set(slugs or [])
    return [slug for slug in _FOOD_LABELS if slug in chosen]


# Daily target split across four meal slots (fractions sum to 1.0).
MEAL_SLOTS: list[tuple[str, str, float]] = [
    ("breakfast", "Desayuno", 0.25),
    ("lunch", "Comida", 0.35),
    ("dinner", "Cena", 0.30),
    ("snack", "Snack", 0.10),
]

# Which food categories each slot suggests, drawn from the user's preferences.
SLOT_COMPONENTS: dict[str, tuple[str, ...]] = {
    "breakfast": ("protein", "carb", "fat"),
    "lunch": ("protein", "carb", "vegetable"),
    "dinner": ("protein", "vegetable", "fat"),
    "snack": ("protein", "carb"),
}


@dataclass(frozen=True)
class MealSlot:
    key: str
    label: str
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    foods: list[str]


def _preferences_by_category(preferences) -> dict[str, list[str]]:
    chosen = set(preferences or [])
    return {
        cat: [slug for slug, _ in items if slug in chosen]
        for cat, items in FOOD_CATALOG.items()
    }


def build_meal_plan(target: MacroTarget, preferences=None) -> list[MealSlot]:
    """Split a daily `MacroTarget` into four slots and suggest foods per slot.

    Foods are rotated through the user's liked items per category (by slot
    index) so slots differ; a category with no liked items contributes nothing.
    Deterministic stub — no AI (CLAUDE.md §15).
    """
    by_cat = _preferences_by_category(preferences)
    slots: list[MealSlot] = []
    for idx, (key, label, pct) in enumerate(MEAL_SLOTS):
        foods: list[str] = []
        for cat in SLOT_COMPONENTS[key]:
            liked = by_cat.get(cat) or []
            if liked:
                foods.append(food_label(liked[idx % len(liked)]))
        slots.append(
            MealSlot(
                key=key,
                label=label,
                calories=round(target.calories * pct),
                protein_g=round(target.protein_g * pct),
                carbs_g=round(target.carbs_g * pct),
                fat_g=round(target.fat_g * pct),
                foods=foods,
            )
        )
    return slots


_SLOT_FRACTION = {key: pct for key, _, pct in MEAL_SLOTS}
_SLOT_LABEL = {key: label for key, label, _ in MEAL_SLOTS}


def slot_label(slot_key: str) -> str:
    return _SLOT_LABEL.get(slot_key, slot_key)


def generate_meal(
    slot_key: str, target: MacroTarget, preferences, rng: random.Random | None = None
) -> tuple[list[str], MacroTarget]:
    """Pick one concrete meal for a slot from the user's liked foods.

    Unlike `build_meal_plan` (which rotates deterministically for the at-a-glance
    plan), this samples randomly within each category so pressing "generar otra"
    yields variety. Returns (food_slugs, macro_split_for_this_slot).
    """
    chooser = rng or random
    by_cat = _preferences_by_category(preferences)
    pct = _SLOT_FRACTION.get(slot_key, 0.25)
    foods: list[str] = []
    for cat in SLOT_COMPONENTS.get(slot_key, ()):
        liked = by_cat.get(cat) or []
        if liked:
            foods.append(chooser.choice(liked))
    macros = MacroTarget(
        calories=round(target.calories * pct),
        protein_g=round(target.protein_g * pct),
        carbs_g=round(target.carbs_g * pct),
        fat_g=round(target.fat_g * pct),
    )
    return foods, macros


@dataclass(frozen=True)
class MacroTarget:
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int


def bmr_mifflin_st_jeor(weight_kg: float, height_cm: float, age: int, sex: str) -> float:
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + (5 if sex == "male" else -161)


class NutritionStrategy(Protocol):
    def recommend(
        self,
        weight_kg: float,
        height_cm: float,
        age: int,
        sex: str,
        activity_factor: float,
        goal: str,
    ) -> MacroTarget: ...


class DeterministicNutrition:
    """Formula-based targets. No history, no AI."""

    def recommend(
        self,
        weight_kg: float,
        height_cm: float,
        age: int,
        sex: str,
        activity_factor: float,
        goal: str,
    ) -> MacroTarget:
        w = float(weight_kg)
        bmr = bmr_mifflin_st_jeor(w, float(height_cm), int(age), sex)
        tdee = bmr * float(activity_factor)
        calories = tdee * GOAL_CALORIE_MULTIPLIER.get(goal, 1.0)

        protein_per_kg = PROTEIN_G_PER_KG_CUT if goal == "cut" else PROTEIN_G_PER_KG
        protein_g = round(protein_per_kg * w)
        fat_g = round(FAT_G_PER_KG * w)
        remaining_cal = calories - protein_g * 4 - fat_g * 9
        carbs_g = max(0, round(remaining_cal / 4))

        return MacroTarget(
            calories=round(calories),
            protein_g=protein_g,
            carbs_g=carbs_g,
            fat_g=fat_g,
        )


def age_from_dob(dob: date, today: date | None = None) -> int:
    today = today or timezone.localdate()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def daily_target_for_user(user) -> tuple[MacroTarget | None, list[str]]:
    """Resolve a user's inputs into a daily target.

    Bodyweight comes from the latest `UserMetricSnapshot`; height / DOB / sex
    from `Profile`. Returns `(target, [])` when complete, or `(None, missing)`
    where `missing` lists the field keys still needed so the view can prompt.
    """
    from gymapp.apps.metrics.models import UserMetricSnapshot

    profile = user.profile
    latest = (
        UserMetricSnapshot.objects.filter(owner=user).order_by("-measured_at").first()
    )
    weight = latest.weight_kg if latest else None

    missing: list[str] = []
    if weight is None:
        missing.append("weight")
    if profile.height_cm is None:
        missing.append("height")
    if profile.date_of_birth is None:
        missing.append("date_of_birth")
    if not profile.sex:
        missing.append("sex")
    if missing:
        return None, missing

    factor = ACTIVITY_FACTORS.get(profile.activity_level, DEFAULT_ACTIVITY_FACTOR)
    target = DeterministicNutrition().recommend(
        weight_kg=weight,
        height_cm=profile.height_cm,
        age=age_from_dob(profile.date_of_birth),
        sex=profile.sex,
        activity_factor=factor,
        goal=profile.training_goal,
    )
    return target, []
