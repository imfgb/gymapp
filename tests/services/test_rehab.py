"""Tests for the rehab service.

Covers `avoided_exercise_ids` and `warnings_for_exercise`. Both are pure
read-only queries scoped via `Injury.objects.for_user`. Test data is built
inline with the existing factories + direct `Injury.objects.create` calls
(there's no `InjuryFactory` yet).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from gymapp.apps.injuries.models import BodyRegion, Injury, MobilityExercise, Severity
from gymapp.services.rehab import (
    avoided_exercise_ids,
    mobility_for_region,
    mobility_for_user,
    suggested_swap,
    warnings_for_exercise,
)
from tests.factories import EquipmentFactory, ExerciseFactory, MuscleGroupFactory, UserFactory


@pytest.fixture
def alice(db):
    return UserFactory(email="alice@example.com")


@pytest.fixture
def bob(db):
    return UserFactory(email="bob@example.com")


def _make_injury(
    owner,
    *,
    name: str = "Lumbalgia",
    body_region: str = BodyRegion.LOWER_BACK,
    severity: str = Severity.MILD,
    started_on=None,
    resolved_on=None,
) -> Injury:
    started_on = started_on or timezone.localdate()
    return Injury.objects.create(
        owner=owner,
        name=name,
        body_region=body_region,
        severity=severity,
        started_on=started_on,
        resolved_on=resolved_on,
    )


# ---------------------------------------------------------------------------
# avoided_exercise_ids
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_avoided_exercise_ids_empty_for_none_user():
    assert avoided_exercise_ids(None) == set()


@pytest.mark.django_db
def test_avoided_exercise_ids_empty_for_anonymous_user():
    assert avoided_exercise_ids(AnonymousUser()) == set()


@pytest.mark.django_db
def test_avoided_exercise_ids_empty_when_user_has_no_injuries(alice):
    assert avoided_exercise_ids(alice) == set()


@pytest.mark.django_db
def test_avoided_exercise_ids_excludes_resolved_injuries(alice):
    today = timezone.localdate()
    ex = ExerciseFactory(slug="deadlift", equipment=EquipmentFactory(slug="barbell"))
    resolved = _make_injury(
        alice,
        name="Vieja lumbalgia",
        started_on=today - timedelta(days=5),
        resolved_on=today,
    )
    resolved.avoid_exercises.add(ex)

    assert avoided_exercise_ids(alice) == set()


@pytest.mark.django_db
def test_avoided_exercise_ids_returns_ids_for_single_active_injury(alice):
    eq = EquipmentFactory(slug="barbell")
    ex1 = ExerciseFactory(slug="deadlift", equipment=eq)
    ex2 = ExerciseFactory(slug="good-morning", equipment=eq)

    injury = _make_injury(alice, name="Lumbalgia")
    injury.avoid_exercises.add(ex1, ex2)

    assert avoided_exercise_ids(alice) == {ex1.id, ex2.id}


@pytest.mark.django_db
def test_avoided_exercise_ids_unions_across_multiple_active_injuries(alice):
    eq = EquipmentFactory(slug="barbell")
    ex1 = ExerciseFactory(slug="deadlift", equipment=eq)
    ex2 = ExerciseFactory(slug="overhead-press", equipment=eq)

    lumbar = _make_injury(alice, name="Lumbalgia", body_region=BodyRegion.LOWER_BACK)
    lumbar.avoid_exercises.add(ex1)
    shoulder = _make_injury(
        alice, name="Impingement hombro", body_region=BodyRegion.SHOULDER
    )
    shoulder.avoid_exercises.add(ex2)

    assert avoided_exercise_ids(alice) == {ex1.id, ex2.id}


@pytest.mark.django_db
def test_avoided_exercise_ids_ignores_injury_with_no_avoid_exercises(alice):
    """An active injury with an empty M2M must not contribute None/0 to the set."""
    _make_injury(alice, name="Lumbalgia leve")  # no avoid_exercises attached

    assert avoided_exercise_ids(alice) == set()


@pytest.mark.django_db
def test_avoided_exercise_ids_is_owner_scoped(alice, bob):
    ex = ExerciseFactory(slug="deadlift", equipment=EquipmentFactory(slug="barbell"))
    bob_injury = _make_injury(bob, name="Lumbalgia de Bob")
    bob_injury.avoid_exercises.add(ex)

    assert avoided_exercise_ids(alice) == set()


# ---------------------------------------------------------------------------
# warnings_for_exercise
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_warnings_for_exercise_empty_for_none_user():
    ex = ExerciseFactory(slug="deadlift", equipment=EquipmentFactory(slug="barbell"))
    assert warnings_for_exercise(ex, None) == []


@pytest.mark.django_db
def test_warnings_for_exercise_empty_for_anonymous_user():
    ex = ExerciseFactory(slug="deadlift", equipment=EquipmentFactory(slug="barbell"))
    assert warnings_for_exercise(ex, AnonymousUser()) == []


@pytest.mark.django_db
def test_warnings_for_exercise_empty_for_none_exercise(alice):
    assert warnings_for_exercise(None, alice) == []


@pytest.mark.django_db
def test_warnings_for_exercise_orders_by_name(alice):
    ex = ExerciseFactory(slug="deadlift", equipment=EquipmentFactory(slug="barbell"))
    z = _make_injury(alice, name="Z-injury")
    z.avoid_exercises.add(ex)
    a = _make_injury(alice, name="A-injury")
    a.avoid_exercises.add(ex)

    result = warnings_for_exercise(ex, alice)
    assert [i.name for i in result] == ["A-injury", "Z-injury"]


@pytest.mark.django_db
def test_warnings_for_exercise_ignores_resolved_injuries(alice):
    today = timezone.localdate()
    ex = ExerciseFactory(slug="deadlift", equipment=EquipmentFactory(slug="barbell"))
    resolved = _make_injury(
        alice,
        name="Lumbalgia vieja",
        started_on=today - timedelta(days=5),
        resolved_on=today,
    )
    resolved.avoid_exercises.add(ex)

    assert warnings_for_exercise(ex, alice) == []


@pytest.mark.django_db
def test_warnings_for_exercise_is_owner_scoped(alice, bob):
    ex = ExerciseFactory(slug="deadlift", equipment=EquipmentFactory(slug="barbell"))
    bob_injury = _make_injury(bob, name="Lumbalgia de Bob")
    bob_injury.avoid_exercises.add(ex)

    assert warnings_for_exercise(ex, alice) == []


# ---------- mobility_for_user / mobility_for_region ----------


@pytest.mark.django_db
def test_mobility_for_user_empty_without_injuries(alice):
    assert mobility_for_user(alice) == []


@pytest.mark.django_db
def test_mobility_for_user_returns_moves_for_injury_region(alice):
    MobilityExercise.objects.create(
        slug="cat-camel-t", name="CatCamelT", body_region="lower_back",
        instructions="...", is_active=True,
    )
    Injury.objects.create(
        owner=alice, name="Lumbalgia",
        body_region="lower_back", started_on=timezone.localdate(),
    )
    out = mobility_for_user(alice, per_region=10)
    assert any(m.slug == "cat-camel-t" for m in out)


@pytest.mark.django_db
def test_mobility_for_user_ignores_resolved_injuries(alice):
    MobilityExercise.objects.create(
        slug="band-x", name="BandX", body_region="shoulder",
        instructions="...", is_active=True,
    )
    Injury.objects.create(
        owner=alice, name="OldShoulder", body_region="shoulder",
        started_on=timezone.localdate() - timedelta(days=30),
        resolved_on=timezone.localdate() - timedelta(days=5),
    )
    out = mobility_for_user(alice)
    assert all(m.slug != "band-x" for m in out)


@pytest.mark.django_db
def test_mobility_for_user_caps_per_region(alice):
    for i in range(5):
        MobilityExercise.objects.create(
            slug=f"mv-{i}", name=f"MoveZ{i}", body_region="hip",
            instructions="...", is_active=True,
        )
    Injury.objects.create(
        owner=alice, name="Hip", body_region="hip", started_on=timezone.localdate(),
    )
    out = mobility_for_user(alice, per_region=2)
    assert len(out) == 2


@pytest.mark.django_db
def test_mobility_for_region_returns_moves_for_that_region():
    MobilityExercise.objects.create(
        slug="m-knee", name="KneeMove", body_region="knee",
        instructions="...", is_active=True,
    )
    out = mobility_for_region("knee")
    assert any(m.slug == "m-knee" for m in out)


# ---------- suggested_swap ----------


@pytest.mark.django_db
def test_suggested_swap_none_when_no_alternatives(alice):
    eq = EquipmentFactory(slug="machine-ss")
    ex = ExerciseFactory(slug="solo-machine", name="Solo", equipment=eq)
    # No other exercises sharing a primary muscle -> no candidates.
    assert suggested_swap(ex, alice) is None


@pytest.mark.django_db
def test_suggested_swap_picks_non_avoided_alternative(alice):
    eq = EquipmentFactory(slug="barbell-ss")
    chest = MuscleGroupFactory(slug="chest-ss", name="Chest-SS", region="chest")
    src = ExerciseFactory(slug="bench-src", name="BenchSrc", equipment=eq)
    src.primary_muscles.add(chest)
    avoided_alt = ExerciseFactory(slug="incline-avoid", name="InclineAvoid", equipment=eq)
    avoided_alt.primary_muscles.add(chest)
    good_alt = ExerciseFactory(slug="dip-ok", name="DipOK", equipment=eq)
    good_alt.primary_muscles.add(chest)

    inj = Injury.objects.create(
        owner=alice, name="Shoulder", body_region="shoulder",
        started_on=timezone.localdate(),
    )
    inj.avoid_exercises.add(src, avoided_alt)

    pick = suggested_swap(src, alice)
    assert pick is not None
    assert pick.id == good_alt.id  # the only non-avoided candidate
