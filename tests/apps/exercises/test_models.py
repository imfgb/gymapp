"""Tests for `exercises` models.

Cover the bits with non-trivial logic: visible_to scoping, the slug uniqueness
per owner, and the self-alternative check constraint.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError
from django.db.utils import IntegrityError as DBIntegrityError

from gymapp.apps.exercises.models import Exercise, ExerciseAlternative
from tests.factories import EquipmentFactory, ExerciseFactory, UserFactory


@pytest.fixture(autouse=True)
def clean_catalog(db):
    # The 0002_seed_catalog data migration populates 78 exercises; these tests
    # need an empty table to assert exact counts and create specific slugs.
    Exercise.objects.all().delete()


@pytest.mark.django_db
def test_visible_to_returns_globals_and_own_customs():
    alice = UserFactory(email="alice@example.com")
    bob = UserFactory(email="bob@example.com")
    eq = EquipmentFactory()

    global_ex = ExerciseFactory(slug="bench-press", owner=None, equipment=eq)
    alice_custom = ExerciseFactory(slug="alice-sled-push", owner=alice, equipment=eq)
    bob_custom = ExerciseFactory(slug="bob-rope-climb", owner=bob, equipment=eq)

    visible_to_alice = set(Exercise.objects.visible_to(alice).values_list("slug", flat=True))
    assert visible_to_alice == {global_ex.slug, alice_custom.slug}
    assert bob_custom.slug not in visible_to_alice


@pytest.mark.django_db
def test_visible_to_anonymous_returns_only_globals():
    eq = EquipmentFactory()
    ExerciseFactory(slug="bench-press", owner=None, equipment=eq)
    alice = UserFactory(email="alice@example.com")
    ExerciseFactory(slug="alice-thing", owner=alice, equipment=eq)

    slugs = set(Exercise.objects.visible_to(None).values_list("slug", flat=True))
    assert slugs == {"bench-press"}


@pytest.mark.django_db
def test_visible_to_superuser_sees_everything():
    eq = EquipmentFactory()
    alice = UserFactory(email="alice@example.com")
    bob = UserFactory(email="bob@example.com")
    su = UserFactory(email="su@example.com", is_superuser=True, is_staff=True)
    ExerciseFactory(slug="g1", owner=None, equipment=eq)
    ExerciseFactory(slug="a1", owner=alice, equipment=eq)
    ExerciseFactory(slug="b1", owner=bob, equipment=eq)

    assert Exercise.objects.visible_to(su).count() == 3


@pytest.mark.django_db
def test_slug_unique_per_owner():
    """The UniqueConstraint on (owner, slug) enforces no-duplicates per-user.

    Note: SQLite (and PostgreSQL) treat NULLs as distinct in UNIQUE
    constraints, so two `owner=NULL` rows with the same slug do *not* violate.
    Global uniqueness is the seed loader's responsibility (it upserts), not
    the database constraint's.
    """
    eq = EquipmentFactory()
    alice = UserFactory(email="alice@example.com")
    bob = UserFactory(email="bob@example.com")

    ExerciseFactory(slug="bench-press", owner=None, equipment=eq)
    # Same slug, different owner -> allowed.
    alice_one = ExerciseFactory(slug="my-bench", owner=alice, equipment=eq)
    ExerciseFactory(slug="my-bench", owner=bob, equipment=eq)
    assert alice_one.slug == "my-bench"  # sanity

    # Same slug, same non-null owner -> rejected by UniqueConstraint.
    with pytest.raises((IntegrityError, DBIntegrityError)):
        Exercise.objects.create(slug="my-bench", name="Dup", equipment=eq, owner=alice)


@pytest.mark.django_db
def test_exercise_alternative_cannot_self_reference():
    eq = EquipmentFactory()
    ex = ExerciseFactory(slug="bench-press", equipment=eq)
    with pytest.raises((IntegrityError, DBIntegrityError)):
        ExerciseAlternative.objects.create(from_exercise=ex, to_exercise=ex)


@pytest.mark.django_db
def test_is_global_property():
    eq = EquipmentFactory()
    glob = ExerciseFactory(slug="g", owner=None, equipment=eq)
    alice = UserFactory(email="alice@example.com")
    custom = ExerciseFactory(slug="c", owner=alice, equipment=eq)

    assert glob.is_global is True
    assert custom.is_global is False
