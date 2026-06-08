"""Weight-unit conversion helper (feedback #8).

Weights are stored canonically in kg; an exercise's unit governs only how the
value is entered and displayed. These are pure functions — no DB.
"""

from __future__ import annotations

from decimal import Decimal

from gymapp.services import units


def test_label():
    assert units.label("lb") == "lb"
    assert units.label("kg") == "kg"
    assert units.label(None) == "kg"  # null resolves to kg


def test_to_kg_passthrough_for_kg():
    assert units.to_kg("60", "kg") == Decimal("60.00")
    assert units.to_kg(Decimal("62.5"), "kg") == Decimal("62.50")


def test_to_kg_converts_lb():
    # 100 lb = 45.359237 kg -> 45.36 (2 dp)
    assert units.to_kg("100", "lb") == Decimal("45.36")


def test_to_display_passthrough_for_kg():
    assert units.to_display(Decimal("60.00"), "kg") == Decimal("60.00")


def test_to_display_converts_kg_to_lb_rounded_to_half():
    # 45.36 kg -> ~100.00 lb
    assert units.to_display(Decimal("45.36"), "lb") == Decimal("100.0")
    # 10 kg -> 22.046 lb -> nearest 0.5 -> 22.0
    assert units.to_display(Decimal("10"), "lb") == Decimal("22.0")


def test_lb_round_trip_is_stable():
    # entering 135 lb, storing kg, displaying back must give 135 lb
    kg = units.to_kg("135", "lb")
    assert units.to_display(kg, "lb") == Decimal("135.0")


def test_to_kg_none_unit_treated_as_kg():
    assert units.to_kg("50", None) == Decimal("50.00")
