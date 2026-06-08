"""Template helpers to render a weight in its exercise's unit (feedback #8).

Weight is stored canonically in kg; `in_unit` converts to the exercise's display
unit, `weight_unit_label` gives the 'kg'/'lb' suffix. Pair them:

    {{ set_log.weight_kg|in_unit:exercise|default_if_none:''|unlocalize }}
    {{ exercise|weight_unit_label }}
"""

from __future__ import annotations

from django import template

from gymapp.services import units

register = template.Library()


@register.filter
def in_unit(weight_kg, exercise):
    """kg → the exercise's display unit. None weight → None (blank input)."""
    if weight_kg is None or exercise is None:
        return None
    return units.to_display(weight_kg, exercise.effective_weight_unit)


@register.filter
def weight_unit_label(exercise) -> str:
    return units.label(exercise.effective_weight_unit) if exercise is not None else "kg"
