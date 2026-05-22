"""Substitution scoring: pure ranking logic + DB-backed candidate selection."""

from __future__ import annotations

import pytest

from gymapp.apps.exercises.models import ExerciseAlternative
from gymapp.services.substitution import (
    CandidateProfile,
    rank_alternatives,
    ranked_alternatives,
    score_alternative,
)
from tests.factories import EquipmentFactory, ExerciseFactory, MuscleGroupFactory


def _p(slug, *, primary=(), secondary=(), equipment="barbell", category="compound", curated=False):
    return CandidateProfile(
        slug=slug,
        name=slug,
        primary=frozenset(primary),
        secondary=frozenset(secondary),
        equipment=equipment,
        category=category,
        curated=curated,
    )


def test_same_primary_outranks_partial_overlap():
    src = _p("bench", primary=["chest"], secondary=["triceps"])
    strong = _p("db-bench", primary=["chest"], secondary=["triceps"], equipment="dumbbell", curated=True)
    weak = _p("fly", primary=["chest"], equipment="cable", category="isolation")

    ranked = rank_alternatives(src, [weak, strong])

    assert [c.slug for c, _ in ranked] == ["db-bench", "fly"]
    assert score_alternative(src, strong) > score_alternative(src, weak)


def test_curated_and_available_equipment_add_score():
    src = _p("a", primary=["x"])
    curated = _p("b", primary=["x"], equipment="dumbbell", curated=True)
    plain = _p("c", primary=["x"], equipment="dumbbell")

    assert score_alternative(src, curated) > score_alternative(src, plain)
    assert score_alternative(src, plain, available_equipment={"dumbbell"}) > score_alternative(
        src, plain
    )


def test_no_primary_overlap_scores_low():
    src = _p("bench", primary=["chest"])
    unrelated = _p("curl", primary=["biceps"], equipment="dumbbell", category="isolation")
    assert score_alternative(src, unrelated) == 0.0


@pytest.mark.django_db
def test_ranked_alternatives_orders_and_excludes_source(clean_catalog):
    chest = MuscleGroupFactory(slug="chest")
    triceps = MuscleGroupFactory(slug="triceps")
    bar = EquipmentFactory(slug="barbell")
    dumbbell = EquipmentFactory(slug="dumbbell")
    cable = EquipmentFactory(slug="cable")

    bench = ExerciseFactory(slug="bench", name="Bench", equipment=bar, category="compound")
    bench.primary_muscles.set([chest])
    bench.secondary_muscles.set([triceps])

    db_bench = ExerciseFactory(slug="db-bench", name="DB Bench", equipment=dumbbell, category="compound")
    db_bench.primary_muscles.set([chest])
    db_bench.secondary_muscles.set([triceps])

    fly = ExerciseFactory(slug="fly", name="Fly", equipment=cable, category="isolation")
    fly.primary_muscles.set([chest])

    ExerciseAlternative.objects.create(from_exercise=bench, to_exercise=db_bench)

    ranked = ranked_alternatives(bench, user=None)
    slugs = [e.slug for e in ranked]

    assert "bench" not in slugs  # source excluded
    assert slugs[0] == "db-bench"  # curated + full muscle/category match wins
    assert "fly" in slugs
    assert ranked[0].sub_score > 0
