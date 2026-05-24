"""Tests for the deterministic meal-plan builder."""

from __future__ import annotations

import random

from gymapp.services.nutrition import (
    FOOD_MACROS,
    MEAL_TEMPLATES,
    MacroTarget,
    MealTemplate,
    build_meal_plan,
    eligible_templates,
    generate_meal,
)

TARGET = MacroTarget(calories=2000, protein_g=160, carbs_g=200, fat_g=60)

# Sweet-only fats must never land on a savory plate (no "steak + peanut butter").
_SWEET_ONLY_FATS = {"peanut_butter", "almond_butter", "dark_chocolate"}
_SAVORY_PROTEIN_SLUGS = {
    "chicken", "beef", "lean_beef", "ground_beef", "fish", "salmon", "tuna",
    "sardines", "pork", "turkey", "shrimp",
}


def test_four_slots_in_order():
    plan = build_meal_plan(TARGET, [])
    assert [s.label for s in plan] == ["Desayuno", "Comida", "Cena", "Snack"]


def test_every_slot_gets_a_coherent_meal_even_without_prefs():
    # With no preferences we fall back to slot templates (never an empty plate).
    plan = build_meal_plan(TARGET, [])
    assert all(s.foods for s in plan)
    assert all(s.calories > 0 for s in plan)


def test_plan_meals_come_from_real_templates():
    template_food_labels = set()
    for tpl in MEAL_TEMPLATES:
        for slug, _ in tpl.ingredients:
            from gymapp.services.nutrition import food_label

            template_food_labels.add(food_label(slug))
    plan = build_meal_plan(TARGET, [])
    for slot in plan:
        for food in slot.foods:
            assert food in template_food_labels


def test_all_template_ingredients_have_macros():
    # every template ingredient must exist in FOOD_MACROS (no orphan slugs)
    for tpl in MEAL_TEMPLATES:
        for slug, _ in tpl.ingredients:
            assert slug in FOOD_MACROS, f"{slug} missing from FOOD_MACROS"


def test_templates_are_well_formed():
    for tpl in MEAL_TEMPLATES:
        assert isinstance(tpl, MealTemplate)
        assert tpl.slots  # fits at least one slot
        roles = {role for _, role in tpl.ingredients}
        assert roles <= {"protein", "carb", "fat", "veg"}
        # a real meal has a protein anchor
        assert any(role == "protein" for _, role in tpl.ingredients)


def test_preferences_select_a_matching_template():
    # liking exactly the "Pollo, arroz y brócoli" mains makes lunch use it
    prefs = ["chicken", "rice"]  # broccoli is veg → not required
    plan = {s.key: s for s in build_meal_plan(TARGET, prefs)}
    assert "Pollo" in plan["lunch"].foods
    assert "Arroz" in plan["lunch"].foods


def test_recipe_library_has_real_variety_per_slot():
    breakfasts = [t for t in MEAL_TEMPLATES if "breakfast" in t.slots]
    lunches = [t for t in MEAL_TEMPLATES if "lunch" in t.slots]
    snacks = [t for t in MEAL_TEMPLATES if "snack" in t.slots]
    assert len(breakfasts) >= 12
    assert len(lunches) >= 20
    assert len(snacks) >= 10


def test_every_recipe_has_a_real_name():
    for tpl in MEAL_TEMPLATES:
        assert tpl.name and len(tpl.name) > 4  # a dish name, not a slug pile


def test_savory_plates_never_use_sweet_fats():
    # the whole point of recipes: no incoherent combos (e.g. steak + peanut butter)
    for tpl in MEAL_TEMPLATES:
        if "lunch" not in tpl.slots and "dinner" not in tpl.slots:
            continue
        slugs = {slug for slug, _ in tpl.ingredients}
        assert not (slugs & _SWEET_ONLY_FATS)


def test_sweet_breakfasts_never_use_savory_meats():
    for tpl in MEAL_TEMPLATES:
        slugs = {slug for slug, _ in tpl.ingredients}
        if slugs & _SWEET_ONLY_FATS:  # a sweet meal
            assert not (slugs & _SAVORY_PROTEIN_SLUGS)


def test_breakfast_generation_is_varied_with_rich_prefs():
    prefs = [
        "whey_isolate", "whey_concentrate", "casein", "greek_yogurt",
        "oats", "banana", "granola", "peanut_butter", "almonds", "nuts",
    ]
    assert len(eligible_templates("breakfast", prefs)) >= 5
    seen = set()
    for s in range(30):
        meal = generate_meal("breakfast", TARGET, prefs, rng=random.Random(s))  # noqa: S311
        seen.add(tuple(sorted(i.slug for i in meal.items)))
    assert len(seen) >= 5  # not "always the same breakfast"


def test_generated_meal_carries_recipe_name_and_prep_note():
    # the shake recipe has a prep note ("licúa con agua o leche")
    meal = generate_meal(
        "breakfast", TARGET, ["whey_isolate", "banana", "oats"], rng=random.Random(0)  # noqa: S311
    )
    assert meal.name
    assert meal.note  # both eligible breakfasts here carry a prep note
