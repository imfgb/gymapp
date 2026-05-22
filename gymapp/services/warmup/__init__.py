"""Warm-up set generation.

Deterministic ramp toward a working weight. No AI: a fixed percentage ladder,
rounded to the plate increment, floored at the empty bar, and never at or above
the working weight. A future `LLMWarmup` could implement the same `Strategy`.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

BAR_WEIGHT_KG = Decimal("20")
PLATE_INCREMENT_KG = Decimal("2.5")

# (fraction of working weight, reps). Lighter, higher-rep first.
_RAMP: tuple[tuple[Decimal, int], ...] = (
    (Decimal("0.40"), 8),
    (Decimal("0.60"), 5),
    (Decimal("0.80"), 3),
)


def _round_to(value: Decimal, increment: Decimal) -> Decimal:
    return (value / increment).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * increment


def warmup_scheme(
    working_weight_kg,
    *,
    bar_weight: Decimal = BAR_WEIGHT_KG,
    increment: Decimal = PLATE_INCREMENT_KG,
) -> list[tuple[Decimal, int]]:
    """Return `(weight_kg, reps)` warm-up sets for a top working weight.

    Empty when the working weight is unknown or at/below the bar (nothing
    meaningful to ramp through). Weights are rounded to `increment`, never below
    `bar_weight`, never at/above the working weight, and de-duplicated.
    """
    if working_weight_kg in (None, ""):
        return []
    working = Decimal(str(working_weight_kg))
    if working <= bar_weight:
        return []

    sets: list[tuple[Decimal, int]] = []
    seen: set[Decimal] = set()
    for fraction, reps in _RAMP:
        weight = _round_to(max(bar_weight, working * fraction), increment)
        if weight >= working or weight in seen:
            continue
        seen.add(weight)
        sets.append((weight, reps))
    return sets


class WarmupStrategy(Protocol):
    def scheme(self, working_weight_kg) -> list[tuple[Decimal, int]]: ...


class DeterministicWarmup:
    def scheme(self, working_weight_kg) -> list[tuple[Decimal, int]]:
        return warmup_scheme(working_weight_kg)
