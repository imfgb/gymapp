"""Tests for the routine generator service.

Generator picks alphabetically the first global exercise per (muscle, category)
slot. These tests rely on the seeded catalogue (78 exercises) — they do NOT
wipe it. The picks are checked by structure (X days, Y exercises per day,
right rep ranges) rather than specific exercise names, since those depend on
the seed's alphabetic ordering and are brittle to seed edits.
"""

from __future__ import annotations

import pytest

from gymapp.apps.routines.models import Routine, RoutineDay, WeeklySplit
from gymapp.services.routine_generator import (
    PRESET_LABELS,
    PRESETS,
    WEEKDAY_PATTERNS,
    DayPlan,
    SplitPreset,
    _rep_scheme,
    assign_weekly_split,
    generate_routine,
    preview_routine,
)
from tests.factories import UserFactory


@pytest.fixture
def alice(db):
    return UserFactory(email="alice@example.com")


@pytest.mark.django_db
def test_assign_weekly_split_distributes_and_clears(alice):
    r = Routine.objects.create(owner=alice, name="R")
    days = [RoutineDay.objects.create(routine=r, label=f"D{i}", ordering=i) for i in range(3)]
    # Pre-existing assignment that should be cleared on reschedule.
    WeeklySplit.objects.create(owner=alice, weekday=6, routine_day=days[0])

    assign_weekly_split(alice, r)

    expected = dict(zip(WEEKDAY_PATTERNS[3], days, strict=True))  # Mon/Wed/Fri
    for wd in range(7):
        split = WeeklySplit.objects.get(owner=alice, weekday=wd)
        assert split.routine_day_id == (expected[wd].id if wd in expected else None)


@pytest.mark.django_db
def test_assign_weekly_split_noop_without_days(alice):
    r = Routine.objects.create(owner=alice, name="Empty")
    assign_weekly_split(alice, r)
    assert WeeklySplit.objects.filter(owner=alice).count() == 0


def test_rep_scheme_per_style():
    assert _rep_scheme("powerlifting", compound=True) == (5, 3, 5)
    assert _rep_scheme("bodybuilding", compound=True) == (4, 8, 12)
    assert _rep_scheme("powerbuilding", compound=True) == (4, 5, 8)
    assert _rep_scheme("powerlifting", compound=False) == (3, 8, 12)
    assert _rep_scheme("bodybuilding", compound=False) == (3, 10, 15)
    # Unknown style falls through to powerbuilding defaults.
    assert _rep_scheme("anything-else", compound=True) == (4, 5, 8)


def test_every_preset_has_a_label_and_days():
    for preset in SplitPreset:
        if preset == SplitPreset.CUSTOM:
            continue
        assert preset in PRESET_LABELS
        assert len(PRESETS[preset]) >= 1
        for day in PRESETS[preset]:
            assert day.label
            assert day.muscle_focus


@pytest.mark.django_db
def test_generate_ppl_6_creates_six_days(alice):
    r = generate_routine(
        owner=alice,
        preset=SplitPreset.PPL_6,
        training_style="powerbuilding",
        name="PPL test",
    )
    assert isinstance(r, Routine)
    assert r.owner_id == alice.id
    assert r.name == "PPL test"
    assert r.days.count() == 6
    # Each day should have at least one exercise (the seed covers every
    # muscle slug used by the preset).
    for day in r.days.all():
        assert day.exercises.count() >= 1


@pytest.mark.django_db
def test_generate_powerlifting_uses_low_rep_scheme_on_compounds(alice):
    r = generate_routine(
        owner=alice,
        preset=SplitPreset.UPPER_LOWER_4,
        training_style="powerlifting",
        name="UL",
    )
    # The first exercise of any day is always a compound (compounds=2 by
    # default for these presets).
    first_day = r.days.order_by("ordering").first()
    first_ex = first_day.exercises.order_by("ordering").first()
    assert first_ex.target_sets == 5
    assert first_ex.target_reps_low == 3
    assert first_ex.target_reps_high == 5


@pytest.mark.django_db
def test_generate_rejects_custom_without_days(alice):
    with pytest.raises(ValueError):
        generate_routine(
            owner=alice,
            preset=SplitPreset.CUSTOM,
            training_style="powerbuilding",
            name="X",
        )


@pytest.mark.django_db
def test_generate_with_custom_days(alice):
    custom = [
        DayPlan("Brazos", ["biceps", "triceps"], compounds=0),
        DayPlan("Pierna", ["quads", "hamstrings"], compounds=2),
    ]
    r = generate_routine(
        owner=alice,
        preset=SplitPreset.CUSTOM,
        training_style="bodybuilding",
        name="Custom",
        custom_days=custom,
    )
    assert r.days.count() == 2
    arm_day = r.days.get(label="Brazos")
    # compounds=0 means no compounds picked; only isolations for biceps + triceps.
    assert all(rex.exercise.category == "isolation" for rex in arm_day.exercises.all())


@pytest.mark.django_db
def test_preview_does_not_persist(alice):
    days = preview_routine(preset=SplitPreset.PPL_3, training_style="powerbuilding")
    assert len(days) == 3
    for day in days:
        assert day.label
        # exercises are tuples of (name, sets, lo, hi)
        for name, sets, lo, hi in day.exercises:
            assert isinstance(name, str)
            assert sets > 0 and lo > 0 and hi >= lo
    # Nothing should have been written to the DB.
    assert Routine.objects.for_user(alice).count() == 0


@pytest.mark.django_db
def test_generate_picks_no_exercise_twice_in_a_day(alice):
    r = generate_routine(
        owner=alice,
        preset=SplitPreset.PPL_6,
        training_style="powerbuilding",
        name="Dedup",
    )
    for day in r.days.all():
        slugs = list(day.exercises.values_list("exercise__slug", flat=True))
        assert len(slugs) == len(set(slugs)), f"Day {day.label} has dups: {slugs}"


@pytest.mark.django_db
def test_generated_routine_is_isolated_per_user(alice):
    bob = UserFactory(email="bob@example.com")
    generate_routine(
        owner=alice,
        preset=SplitPreset.PPL_3,
        training_style="powerbuilding",
        name="Alice's",
    )
    generate_routine(
        owner=bob,
        preset=SplitPreset.PPL_3,
        training_style="bodybuilding",
        name="Bob's",
    )
    assert Routine.objects.for_user(alice).count() == 1
    assert Routine.objects.for_user(bob).count() == 1
    assert RoutineDay.objects.filter(routine__owner=alice).count() == 3
    assert RoutineDay.objects.filter(routine__owner=bob).count() == 3
