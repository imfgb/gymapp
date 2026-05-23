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
        ("whey_concentrate", "Whey concentrada"),
        ("whey_isolate", "Whey aislada"),
        ("casein", "Caseína"),
        ("tofu", "Tofu"),
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
        ("banana", "Plátano"),
        ("rice_cakes", "Tortitas de arroz"),
        ("granola", "Granola"),
        ("honey", "Miel"),
    ],
    "vegetable": [
        ("broccoli", "Brócoli"),
        ("spinach", "Espinaca"),
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
        ("almonds", "Almendras"),
        ("peanut_butter", "Crema de cacahuate"),
        ("almond_butter", "Crema de almendra"),
        ("cheese", "Queso"),
        ("dark_chocolate", "Chocolate amargo"),
    ],
}

# Macros per 100 g, RAW/DRY weight (protein, carbs, fat). Approximate reference
# values — enough to size portions and explain a meal's macros. Grains/legumes
# are dry; meats/veg are raw; powders are per 100 g of powder.
FOOD_MACROS: dict[str, tuple[float, float, float]] = {
    # protein
    "chicken": (31, 0, 3.6),
    "beef": (26, 0, 15),
    "lean_beef": (27, 0, 8),
    "ground_beef": (20, 0, 10),
    "eggs": (13, 1, 11),
    "egg_whites": (11, 1, 0),
    "fish": (20, 0, 2),
    "salmon": (20, 0, 13),
    "tuna": (26, 0, 1),
    "sardines": (25, 0, 11),
    "pork": (21, 0, 6),
    "turkey": (29, 0, 1),
    "turkey_ham": (17, 2, 3),
    "shrimp": (20, 0, 1),
    "greek_yogurt": (10, 4, 0.4),
    "whey_concentrate": (75, 10, 6),
    "whey_isolate": (90, 2, 1),
    "casein": (78, 8, 2),
    "tofu": (12, 2, 7),
    # carb
    "rice": (7, 80, 1),
    "brown_rice": (7, 76, 3),
    "oats": (13, 67, 7),
    "potato": (2, 17, 0),
    "sweet_potato": (2, 20, 0),
    "pasta": (12, 75, 1.5),
    "bread": (9, 49, 3),
    "whole_wheat_bread": (12, 43, 3),
    "tortilla": (6, 45, 2),
    "corn": (3, 19, 1),
    "beans": (21, 63, 1),
    "lentils": (25, 60, 1),
    "chickpeas": (19, 61, 6),
    "quinoa": (14, 64, 6),
    "banana": (1, 23, 0),
    "rice_cakes": (8, 82, 3),
    "granola": (10, 64, 15),
    "honey": (0, 82, 0),
    # vegetable
    "broccoli": (3, 7, 0),
    "spinach": (3, 4, 0),
    "lettuce": (1, 3, 0),
    "tomato": (1, 4, 0),
    "carrot": (1, 10, 0),
    "zucchini": (1, 3, 0),
    "pepper": (1, 6, 0),
    "cucumber": (1, 4, 0),
    "onion": (1, 9, 0),
    "mushroom": (3, 3, 0),
    "green_beans": (2, 7, 0),
    "asparagus": (2, 4, 0),
    "nopal": (1, 3, 0),
    # fat
    "avocado": (2, 9, 15),
    "olive_oil": (0, 0, 100),
    "coconut_oil": (0, 0, 100),
    "nuts": (15, 20, 55),
    "almonds": (21, 22, 49),
    "peanut_butter": (25, 20, 50),
    "almond_butter": (21, 19, 55),
    "cheese": (25, 1, 33),
    "dark_chocolate": (8, 46, 43),
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


_CATEGORY_MACRO_INDEX = {"protein": 0, "carb": 1, "fat": 2}
_VEGETABLE_GRAMS = 120


@dataclass(frozen=True)
class MealItem:
    slug: str
    grams: int
    protein_g: int
    carbs_g: int
    fat_g: int
    calories: int


@dataclass(frozen=True)
class GeneratedMeal:
    items: list[MealItem]
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int


def _item_from_grams(slug: str, grams: float) -> MealItem:
    p100, c100, f100 = FOOD_MACROS.get(slug, (0, 0, 0))
    g = max(5, min(500, int(round(grams / 5) * 5)))  # snap to 5 g, clamp
    p, c, f = g * p100 / 100, g * c100 / 100, g * f100 / 100
    return MealItem(
        slug=slug,
        grams=g,
        protein_g=round(p),
        carbs_g=round(c),
        fat_g=round(f),
        calories=round(p * 4 + c * 4 + f * 9),
    )


def generate_meal(
    slot_key: str, target: MacroTarget, preferences, rng: random.Random | None = None
) -> GeneratedMeal:
    """Build one concrete meal for a slot from the user's liked foods.

    Picks a food per slot category (randomly, so "generar otra" varies), sizes
    each in **raw grams** so its namesake macro hits this slot's share of the
    daily target (protein source → protein, carb → carbs, fat → fat; vegetables
    get a fixed serving). The meal's macros are then summed from those grams, so
    grams and macros are always consistent and self-explanatory.
    """
    chooser = rng or random
    by_cat = _preferences_by_category(preferences)
    pct = _SLOT_FRACTION.get(slot_key, 0.25)
    macro_target = (target.protein_g * pct, target.carbs_g * pct, target.fat_g * pct)

    items: list[MealItem] = []
    for cat in SLOT_COMPONENTS.get(slot_key, ()):
        liked = by_cat.get(cat) or []
        if not liked:
            continue
        slug = chooser.choice(liked)
        if cat == "vegetable":
            items.append(_item_from_grams(slug, _VEGETABLE_GRAMS))
            continue
        idx = _CATEGORY_MACRO_INDEX[cat]
        density = FOOD_MACROS.get(slug, (0, 0, 0))[idx] / 100
        grams = macro_target[idx] / density if density else 100
        items.append(_item_from_grams(slug, grams))

    return GeneratedMeal(
        items=items,
        calories=sum(i.calories for i in items),
        protein_g=sum(i.protein_g for i in items),
        carbs_g=sum(i.carbs_g for i in items),
        fat_g=sum(i.fat_g for i in items),
    )


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
