"""6-week training-block templates (Phase 5).

A block overlays periodization guidance on top of the user's existing routine:
each week has a focus + intensity/volume cue, with the last week a deload. The
plan is a deterministic constant per training style — no rows per week. The
"current week" is derived from the block's `started_on` vs today, so blocks
advance by the calendar (no jobs).

Spanish guidance text lives here (UI surface), English style keys (domain),
matching the convention used by `services.nutrition.FOOD_CATALOG`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

BLOCK_LENGTH_WEEKS = 6


@dataclass(frozen=True)
class BlockWeek:
    week: int
    title: str
    detail: str
    is_deload: bool


_BODYBUILDING: list[BlockWeek] = [
    BlockWeek(1, "Acumulación", "Volumen base. RPE 7 (deja ~3 reps en reserva).", False),
    BlockWeek(2, "Acumulación", "Añade 1 serie por grupo. RPE 7-8.", False),
    BlockWeek(3, "Acumulación", "Añade 1 serie más. RPE 8 (~2 en reserva).", False),
    BlockWeek(4, "Intensificación", "Mantén volumen, sube carga. RPE 8-9.", False),
    BlockWeek(5, "Pico", "Volumen alto, cerca del fallo. RPE 9.", False),
    BlockWeek(6, "Descarga", "~50% del volumen, RPE 6. Recupera para el próximo bloque.", True),
]

_POWERLIFTING: list[BlockWeek] = [
    BlockWeek(1, "Volumen", "70-75% 1RM. Series de 5. RPE 7.", False),
    BlockWeek(2, "Volumen", "75-80%. Series de 4-5. RPE 7-8.", False),
    BlockWeek(3, "Fuerza", "80-85%. Series de 3. RPE 8.", False),
    BlockWeek(4, "Fuerza", "85-90%. Series de 2-3. RPE 8-9.", False),
    BlockWeek(5, "Pico", "90-95%. Singles/dobles. RPE 9.", False),
    BlockWeek(6, "Descarga", "60%. Técnica, poco volumen.", True),
]

_POWERBUILDING: list[BlockWeek] = [
    BlockWeek(1, "Acumulación", "Compuestos 75% + accesorios RPE 7.", False),
    BlockWeek(2, "Acumulación", "+1 serie de accesorios. Compuestos 77-80%.", False),
    BlockWeek(3, "Intensificación", "Compuestos 80-85%. Accesorios RPE 8.", False),
    BlockWeek(4, "Intensificación", "Compuestos 85-87%. Mantén accesorios.", False),
    BlockWeek(5, "Pico", "Compuestos 88-92%. Accesorios cerca del fallo.", False),
    BlockWeek(6, "Descarga", "~50-60% en todo. RPE 6.", True),
]

BLOCK_TEMPLATES: dict[str, list[BlockWeek]] = {
    "bodybuilding": _BODYBUILDING,
    "powerlifting": _POWERLIFTING,
    "powerbuilding": _POWERBUILDING,
}


def block_template(training_style: str) -> list[BlockWeek]:
    return BLOCK_TEMPLATES.get(training_style, _POWERBUILDING)


def current_week_index(started_on: date, today: date, length: int = BLOCK_LENGTH_WEEKS) -> int:
    """1-based week number. May exceed `length` → the block is finished."""
    return max(1, (today - started_on).days // 7 + 1)


@dataclass(frozen=True)
class BlockStatus:
    week_index: int          # 1-based; capped at length for display
    is_finished: bool
    current: BlockWeek | None
    weeks: list[BlockWeek]


def block_status(training_style: str, started_on: date, today: date, length: int = BLOCK_LENGTH_WEEKS) -> BlockStatus:
    weeks = block_template(training_style)[:length]
    raw = current_week_index(started_on, today, length)
    finished = raw > length
    idx = min(raw, length)
    current = None if finished else weeks[idx - 1]
    return BlockStatus(week_index=idx, is_finished=finished, current=current, weeks=weeks)
