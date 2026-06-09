"""Weight-unit conversion (feedback #8).

Lifted weight is stored canonically in **kg**; an exercise's `weight_unit`
(kg/lb) governs only input and display. These helpers are the single place that
converts, so aggregations (tonnage, PRs) never have to think about units.

1 lb = 0.45359237 kg (exact). Stored kg keeps 2 dp; displayed lb rounds to the
nearest 0.5 lb — gym weights aren't finer, and it keeps round-trips stable.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

KG = "kg"
LB = "lb"

KG_PER_LB = Decimal("0.45359237")
LB_PER_KG = Decimal("1") / KG_PER_LB

_CENT = Decimal("0.01")
_HALF = Decimal("0.5")


def label(unit: str | None) -> str:
    """Display label; a null/unknown unit resolves to kg."""
    return LB if unit == LB else KG


def other_unit(unit: str | None) -> str:
    """The opposite unit — for the kg⇄lb toggle."""
    return KG if unit == LB else LB


def to_kg(value, unit: str | None) -> Decimal:
    """Convert a user-entered `value` in `unit` to canonical kg (2 dp)."""
    amount = Decimal(value)
    kg = amount * KG_PER_LB if unit == LB else amount
    return kg.quantize(_CENT, rounding=ROUND_HALF_UP)


def to_display(weight_kg, unit: str | None) -> Decimal:
    """Convert canonical kg to the exercise's display unit.

    kg → 2 dp; lb → nearest 0.5 lb.
    """
    kg = Decimal(weight_kg)
    if unit == LB:
        lb = kg * LB_PER_KG
        return (lb / _HALF).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * _HALF
    return kg.quantize(_CENT, rounding=ROUND_HALF_UP)
