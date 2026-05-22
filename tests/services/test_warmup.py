"""Warm-up scheme generation (pure, deterministic)."""

from __future__ import annotations

from decimal import Decimal

from gymapp.services.warmup import warmup_scheme


def _as_floats(scheme):
    return [(float(w), reps) for w, reps in scheme]


def test_no_scheme_without_weight():
    assert warmup_scheme(None) == []
    assert warmup_scheme("") == []


def test_no_scheme_at_or_below_bar():
    assert warmup_scheme(20) == []
    assert warmup_scheme(Decimal("15")) == []


def test_standard_ramp():
    assert _as_floats(warmup_scheme(100)) == [(40.0, 8), (60.0, 5), (80.0, 3)]


def test_weights_rounded_to_plate_increment_and_below_working():
    scheme = warmup_scheme(Decimal("97.5"))
    weights = [w for w, _ in scheme]
    # 0.4/0.6/0.8 of 97.5 = 39/58.5/78 -> round to 2.5: 40, 57.5, 77.5
    assert _as_floats(scheme) == [(40.0, 8), (57.5, 5), (77.5, 3)]
    assert all(w < Decimal("97.5") for w in weights)


def test_light_working_weight_dedupes_to_bar():
    # 25kg: 0.4->10->bar(20); 0.6->15->20 (dup); 0.8->20 (dup) => single bar set
    assert _as_floats(warmup_scheme(25)) == [(20.0, 8)]
