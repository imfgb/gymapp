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

# Common supplements offered as quick-add on the supplements page. The user can
# also type a custom one. Just Spanish labels — supplements have no macro math.
COMMON_SUPPLEMENTS: list[str] = [
    "Creatina",
    "Proteína (Whey)",
    "Omega 3",
    "BCAAs",
    "Multivitamínico",
    "Pre-entreno",
    "Cafeína",
    "Vitamina D",
    "Magnesio",
    "Zinc",
    "Beta-alanina",
    "Glutamina",
    "Citrulina",
    "Colágeno",
    "Electrolitos",
    "Ashwagandha",
]

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
    name: str = ""
    note: str = ""


@dataclass(frozen=True)
class MealSlot:
    key: str
    label: str
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    foods: list[str]


@dataclass(frozen=True)
class MealTemplate:
    """A real, curated recipe (a shake, a plate of eggs, a grilled plate…).

    `name` is the dish name and `note` an optional prep hint (e.g. "licúa con
    agua o leche") — both shown to the user so a meal reads like a recipe, not a
    pile of foods. `slots` are the meal slots it fits; each ingredient is
    `(slug, role)` where role is protein/carb/fat (sized to hit that macro) or
    veg (fixed serving). Recipes are hand-curated to stay coherent (no sweet nut
    butter on a steak); variety comes from having many of them.
    """

    name: str
    slots: tuple[str, ...]
    ingredients: tuple[tuple[str, str], ...]
    note: str = ""


_AM = ("breakfast", "snack")
_PM = ("lunch", "dinner")
_B = ("breakfast",)
_S = ("snack",)

# Preparation hints shown under the dish name.
_N_SHAKE = "Licúa con 250 ml de agua o leche."
_N_OATS = "Cocina la avena con agua o leche."
_N_EGGS = "Al gusto: revueltos, estrellados u omelette."
_N_GRILL = "A la plancha o al horno."

# Curated, REAL recipes — each is an actual dish (a shake, a plate of eggs, a
# Mexican antojito, a grilled plate), not a random pile of foods. Ingredients are
# `(slug, role)`: protein/carb/fat are sized to hit that share of the slot's
# macros; veg is a fixed serving. The dish NAME and prep NOTE are shown to the
# user so it reads like a recipe. Coherence is curated by hand; variety comes
# from having many recipes per slot, filtered by the user's liked foods.
MEAL_TEMPLATES: list[MealTemplate] = [
    # ---------- Desayunos: licuados / batidos ----------
    MealTemplate("Licuado de proteína, plátano y avena", _AM,
                 (("whey_isolate", "protein"), ("banana", "carb"), ("oats", "carb")),
                 note=_N_SHAKE),
    MealTemplate("Licuado de proteína con plátano y crema de cacahuate", _AM,
                 (("whey_concentrate", "protein"), ("banana", "carb"), ("peanut_butter", "fat")),
                 note=_N_SHAKE),
    MealTemplate("Licuado de proteína, avena y crema de almendra", _AM,
                 (("whey_isolate", "protein"), ("oats", "carb"), ("almond_butter", "fat")),
                 note=_N_SHAKE),
    MealTemplate("Licuado de caseína con plátano y nueces", _AM,
                 (("casein", "protein"), ("banana", "carb"), ("nuts", "fat")),
                 note=_N_SHAKE),
    # ---------- Desayunos: avena ----------
    MealTemplate("Avena cocida con proteína y plátano", _AM,
                 (("oats", "carb"), ("whey_isolate", "protein"), ("banana", "carb")),
                 note=_N_OATS),
    MealTemplate("Avena con caseína, crema de cacahuate y plátano", _AM,
                 (("oats", "carb"), ("casein", "protein"), ("peanut_butter", "fat"), ("banana", "carb")),
                 note=_N_OATS),
    MealTemplate("Avena con yogur griego y miel", _AM,
                 (("greek_yogurt", "protein"), ("oats", "carb"), ("honey", "carb"))),
    # ---------- Desayunos: yogur ----------
    MealTemplate("Yogur griego con granola y plátano", _AM,
                 (("greek_yogurt", "protein"), ("granola", "carb"), ("banana", "carb"))),
    MealTemplate("Yogur griego con almendras y miel", _AM,
                 (("greek_yogurt", "protein"), ("almonds", "fat"), ("honey", "carb"))),
    MealTemplate("Yogur griego con nueces y plátano", _AM,
                 (("greek_yogurt", "protein"), ("nuts", "fat"), ("banana", "carb"))),
    MealTemplate("Parfait de yogur, granola y crema de almendra", _AM,
                 (("greek_yogurt", "protein"), ("granola", "carb"), ("almond_butter", "fat"))),
    # ---------- Desayunos: hotcakes ----------
    MealTemplate("Hotcakes de avena y plátano", _B,
                 (("oats", "carb"), ("egg_whites", "protein"), ("banana", "carb")),
                 note="Licúa la avena, las claras y el plátano; cocina como hotcakes."),
    MealTemplate("Hotcakes de avena con proteína y crema de cacahuate", _B,
                 (("oats", "carb"), ("whey_concentrate", "protein"), ("peanut_butter", "fat")),
                 note="Licúa avena y proteína, cocina y unta la crema encima."),
    # ---------- Desayunos: huevos ----------
    MealTemplate("Huevos revueltos con frijoles y tortilla", _B,
                 (("eggs", "protein"), ("beans", "carb"), ("tortilla", "carb")),
                 note=_N_EGGS),
    MealTemplate("Huevos a la mexicana con tortilla", _B,
                 (("eggs", "protein"), ("tortilla", "carb"), ("tomato", "veg")),
                 note=_N_EGGS),
    MealTemplate("Omelette de claras con espinaca y queso", _B,
                 (("egg_whites", "protein"), ("whole_wheat_bread", "carb"), ("spinach", "veg"), ("cheese", "fat"))),
    MealTemplate("Huevos estrellados con aguacate y pan integral", _B,
                 (("eggs", "protein"), ("whole_wheat_bread", "carb"), ("avocado", "fat")),
                 note=_N_EGGS),
    MealTemplate("Tacos de huevo con nopales", _B,
                 (("eggs", "protein"), ("tortilla", "carb"), ("nopal", "veg")),
                 note=_N_EGGS),
    MealTemplate("Chilaquiles con huevo y queso", _B,
                 (("eggs", "protein"), ("tortilla", "carb"), ("cheese", "fat"))),
    MealTemplate("Huevos rancheros", _B,
                 (("eggs", "protein"), ("tortilla", "carb"), ("tomato", "veg")),
                 note=_N_EGGS),
    MealTemplate("Burrito de huevo con frijoles", _B,
                 (("eggs", "protein"), ("tortilla", "carb"), ("beans", "carb")),
                 note=_N_EGGS),
    MealTemplate("Molletes con frijol, queso y huevo", _B,
                 (("eggs", "protein"), ("whole_wheat_bread", "carb"), ("beans", "carb"), ("cheese", "fat"))),
    MealTemplate("Sincronizadas de jamón de pavo y queso", _B,
                 (("turkey_ham", "protein"), ("tortilla", "carb"), ("cheese", "fat"))),
    MealTemplate("Sándwich de huevo y aguacate", _B,
                 (("eggs", "protein"), ("whole_wheat_bread", "carb"), ("avocado", "fat")),
                 note=_N_EGGS),
    # ---------- Snacks ----------
    MealTemplate("Yogur griego con granola", _S,
                 (("greek_yogurt", "protein"), ("granola", "carb"))),
    MealTemplate("Yogur griego con almendras", _S,
                 (("greek_yogurt", "protein"), ("almonds", "fat"))),
    MealTemplate("Licuado de proteína con plátano", _S,
                 (("whey_isolate", "protein"), ("banana", "carb")),
                 note=_N_SHAKE),
    MealTemplate("Sándwich de jamón de pavo y queso", _S,
                 (("turkey_ham", "protein"), ("whole_wheat_bread", "carb"), ("cheese", "fat"))),
    MealTemplate("Atún con galletas de arroz", _S,
                 (("tuna", "protein"), ("rice_cakes", "carb"))),
    MealTemplate("Tostadas de arroz con atún y aguacate", _S,
                 (("tuna", "protein"), ("rice_cakes", "carb"), ("avocado", "fat"))),
    MealTemplate("Pudín de caseína con crema de almendra", _S,
                 (("casein", "protein"), ("almond_butter", "fat")),
                 note="Mezcla la caseína con agua y refrigera."),
    MealTemplate("Huevos cocidos con aguacate", _S,
                 (("eggs", "protein"), ("avocado", "fat"))),
    MealTemplate("Plátano con yogur griego y crema de cacahuate", _S,
                 (("greek_yogurt", "protein"), ("banana", "carb"), ("peanut_butter", "fat"))),
    # ---------- Comidas / cenas: pollo ----------
    MealTemplate("Pechuga de pollo a la plancha con arroz y brócoli", _PM,
                 (("chicken", "protein"), ("rice", "carb"), ("broccoli", "veg")),
                 note=_N_GRILL),
    MealTemplate("Pollo al horno con camote y ejotes", _PM,
                 (("chicken", "protein"), ("sweet_potato", "carb"), ("green_beans", "veg")),
                 note=_N_GRILL),
    MealTemplate("Tacos de pollo con nopales", _PM,
                 (("chicken", "protein"), ("tortilla", "carb"), ("nopal", "veg"))),
    MealTemplate("Fajitas de pollo con pimiento", _PM,
                 (("chicken", "protein"), ("tortilla", "carb"), ("pepper", "veg"))),
    MealTemplate("Tinga de pollo con arroz", _PM,
                 (("chicken", "protein"), ("rice", "carb"), ("onion", "veg"))),
    MealTemplate("Bowl de pollo con quinoa y aguacate", _PM,
                 (("chicken", "protein"), ("quinoa", "carb"), ("avocado", "fat"))),
    MealTemplate("Pollo con pasta y champiñón", _PM,
                 (("chicken", "protein"), ("pasta", "carb"), ("mushroom", "veg"))),
    # ---------- Comidas / cenas: res ----------
    MealTemplate("Bistec a la plancha con papa y ejotes", _PM,
                 (("lean_beef", "protein"), ("potato", "carb"), ("green_beans", "veg")),
                 note=_N_GRILL),
    MealTemplate("Tacos de bistec con cebolla", _PM,
                 (("lean_beef", "protein"), ("tortilla", "carb"), ("onion", "veg"))),
    MealTemplate("Bistec con arroz y nopales", _PM,
                 (("lean_beef", "protein"), ("rice", "carb"), ("nopal", "veg"))),
    MealTemplate("Carne molida con arroz y calabacita", _PM,
                 (("ground_beef", "protein"), ("rice", "carb"), ("zucchini", "veg"))),
    MealTemplate("Albóndigas en salsa de jitomate con arroz", _PM,
                 (("ground_beef", "protein"), ("rice", "carb"), ("tomato", "veg"))),
    # ---------- Comidas / cenas: pescado y mariscos ----------
    MealTemplate("Salmón al horno con camote y espárragos", _PM,
                 (("salmon", "protein"), ("sweet_potato", "carb"), ("asparagus", "veg")),
                 note=_N_GRILL),
    MealTemplate("Salmón con arroz integral y brócoli", _PM,
                 (("salmon", "protein"), ("brown_rice", "carb"), ("broccoli", "veg"))),
    MealTemplate("Salmón con puré de papa y espinaca", _PM,
                 (("salmon", "protein"), ("potato", "carb"), ("spinach", "veg"))),
    MealTemplate("Atún con pasta integral y jitomate", _PM,
                 (("tuna", "protein"), ("pasta", "carb"), ("tomato", "veg"))),
    MealTemplate("Ensalada de atún con garbanzos", _PM,
                 (("tuna", "protein"), ("chickpeas", "carb"), ("lettuce", "veg"))),
    MealTemplate("Pescado a la plancha con arroz y ensalada", _PM,
                 (("fish", "protein"), ("rice", "carb"), ("lettuce", "veg")),
                 note=_N_GRILL),
    MealTemplate("Pescado con quinoa y espárragos", _PM,
                 (("fish", "protein"), ("quinoa", "carb"), ("asparagus", "veg"))),
    MealTemplate("Camarones al ajillo con arroz", _PM,
                 (("shrimp", "protein"), ("rice", "carb"), ("pepper", "veg"))),
    MealTemplate("Camarones con pasta y calabacita", _PM,
                 (("shrimp", "protein"), ("pasta", "carb"), ("zucchini", "veg"))),
    MealTemplate("Sardinas con pasta y jitomate", _PM,
                 (("sardines", "protein"), ("pasta", "carb"), ("tomato", "veg"))),
    # ---------- Comidas / cenas: cerdo, pavo, tofu ----------
    MealTemplate("Lomo de cerdo con camote y ejotes", _PM,
                 (("pork", "protein"), ("sweet_potato", "carb"), ("green_beans", "veg")),
                 note=_N_GRILL),
    MealTemplate("Cerdo con arroz y zanahoria", _PM,
                 (("pork", "protein"), ("rice", "carb"), ("carrot", "veg"))),
    MealTemplate("Picadillo de pavo con papa y zanahoria", _PM,
                 (("turkey", "protein"), ("potato", "carb"), ("carrot", "veg"))),
    MealTemplate("Pavo con quinoa y brócoli", _PM,
                 (("turkey", "protein"), ("quinoa", "carb"), ("broccoli", "veg"))),
    MealTemplate("Tofu salteado con arroz y champiñón", _PM,
                 (("tofu", "protein"), ("rice", "carb"), ("mushroom", "veg"))),
    MealTemplate("Curry de tofu con arroz integral", _PM,
                 (("tofu", "protein"), ("brown_rice", "carb"), ("pepper", "veg"))),
]


def eligible_templates(slot_key: str, preferences) -> list[MealTemplate]:
    """Templates that fit the slot and whose protein/carb/fat foods the user likes.

    Vegetables aren't required (they're swappable filler). Returns [] when the
    user's preferences don't fully cover any template for the slot.
    """
    prefs = set(preferences or [])
    out = []
    for tpl in MEAL_TEMPLATES:
        if slot_key not in tpl.slots:
            continue
        mains = [slug for slug, role in tpl.ingredients if role in _CATEGORY_MACRO_INDEX]
        if all(slug in prefs for slug in mains):
            out.append(tpl)
    return out


def _templates_for(slot_key: str, preferences) -> list[MealTemplate]:
    """Preferred templates, falling back to all slot templates if none match."""
    return eligible_templates(slot_key, preferences) or [
        t for t in MEAL_TEMPLATES if slot_key in t.slots
    ]


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


def _scale_template(tpl: MealTemplate, slot_key: str, target: MacroTarget) -> GeneratedMeal:
    """Size a template's ingredients (raw grams) to the slot's macro share.

    Each protein/carb/fat ingredient is sized so its macro hits the slot target;
    when a template has two of a role (e.g. oats + banana) the target is split
    between them. Vegetables get a fixed serving. Macros are summed from the real
    grams so the numbers explain themselves.
    """
    pct = _SLOT_FRACTION.get(slot_key, 0.25)
    macro_target = {
        "protein": target.protein_g * pct,
        "carb": target.carbs_g * pct,
        "fat": target.fat_g * pct,
    }
    counts: dict[str, int] = {}
    for _, role in tpl.ingredients:
        if role in macro_target:
            counts[role] = counts.get(role, 0) + 1

    items: list[MealItem] = []
    for slug, role in tpl.ingredients:
        if role == "veg":
            items.append(_item_from_grams(slug, _VEGETABLE_GRAMS))
            continue
        idx = _CATEGORY_MACRO_INDEX[role]
        share = macro_target[role] / counts[role]
        density = FOOD_MACROS.get(slug, (0, 0, 0))[idx] / 100
        grams = share / density if density else 60
        items.append(_item_from_grams(slug, grams))

    return GeneratedMeal(
        items=items,
        calories=sum(i.calories for i in items),
        protein_g=sum(i.protein_g for i in items),
        carbs_g=sum(i.carbs_g for i in items),
        fat_g=sum(i.fat_g for i in items),
        name=tpl.name,
        note=tpl.note,
    )


def build_meal_plan(target: MacroTarget, preferences=None) -> list[MealSlot]:
    """At-a-glance daily plan: one coherent meal per slot (deterministic pick)."""
    slots: list[MealSlot] = []
    for idx, (key, label, pct) in enumerate(MEAL_SLOTS):
        templates = _templates_for(key, preferences)
        if templates:
            meal = _scale_template(templates[idx % len(templates)], key, target)
            slots.append(
                MealSlot(
                    key=key,
                    label=label,
                    calories=meal.calories,
                    protein_g=meal.protein_g,
                    carbs_g=meal.carbs_g,
                    fat_g=meal.fat_g,
                    foods=[food_label(i.slug) for i in meal.items],
                )
            )
        else:
            slots.append(
                MealSlot(
                    key, label, round(target.calories * pct), round(target.protein_g * pct),
                    round(target.carbs_g * pct), round(target.fat_g * pct), [],
                )
            )
    return slots


def generate_meal(
    slot_key: str, target: MacroTarget, preferences, rng: random.Random | None = None
) -> GeneratedMeal:
    """Pick one real recipe for a slot and scale it to that slot's macro share.

    Randomly (for variety) picks a recipe that fits the slot and whose
    protein/carb/fat foods the user likes (vegetables are part of the recipe),
    falling back to all slot recipes if none match. Returns it with the dish name
    + prep note so the meal reads like a recipe, not a pile of foods.
    """
    chooser = rng or random
    templates = _templates_for(slot_key, preferences)
    if not templates:
        return GeneratedMeal(items=[], calories=0, protein_g=0, carbs_g=0, fat_g=0)
    return _scale_template(chooser.choice(templates), slot_key, target)


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
