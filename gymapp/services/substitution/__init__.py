"""Exercise substitution service.

Phase 1 delegated to `exercise_library.lookup_alternatives` (the curated graph,
unranked). Phase 2 adds deterministic multi-factor scoring so "swap exercise"
returns alternatives ranked best-first.

Scoring factors (all deterministic, no AI):
- **Primary muscle overlap** (Jaccard) — dominant: a good substitute trains the
  same primary mover.
- **Secondary muscle overlap** (Jaccard) — secondary.
- **Cross overlap** — candidate hits the source's primary as a secondary mover
  (or vice versa); a partial match.
- **Curated bonus** — the pair is hand-linked in `ExerciseAlternative`.
- **Equipment** — available (when an inventory is provided) and/or same as source.
- **Same category** — compound↔compound, isolation↔isolation.

A future `LLMSubstitution` can implement the same `SubstitutionStrategy`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from gymapp.services.exercise_library import (
    DeterministicExerciseLibrary,
    ExerciseLibraryStrategy,
)

PRIMARY_WEIGHT = 6.0
SECONDARY_WEIGHT = 2.0
CROSS_WEIGHT = 1.0
CURATED_BONUS = 2.5
EQUIPMENT_AVAILABLE_BONUS = 1.5
SAME_EQUIPMENT_BONUS = 1.0
SAME_CATEGORY_BONUS = 1.0


@dataclass(frozen=True)
class CandidateProfile:
    """The muscle/equipment fingerprint the scorer needs — pure data so the
    ranking logic is testable without the database."""

    slug: str
    name: str
    primary: frozenset[str] = field(default_factory=frozenset)
    secondary: frozenset[str] = field(default_factory=frozenset)
    equipment: str = ""
    category: str = "compound"
    curated: bool = False


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def score_alternative(
    source: CandidateProfile,
    candidate: CandidateProfile,
    available_equipment: set[str] | None = None,
) -> float:
    """Higher is a better substitute for `source`. Deterministic."""
    score = PRIMARY_WEIGHT * _jaccard(source.primary, candidate.primary)
    score += SECONDARY_WEIGHT * _jaccard(source.secondary, candidate.secondary)

    cross = (source.primary & candidate.secondary) | (source.secondary & candidate.primary)
    if source.primary:
        score += CROSS_WEIGHT * len(cross) / len(source.primary)

    if candidate.curated:
        score += CURATED_BONUS
    if available_equipment is not None and candidate.equipment in available_equipment:
        score += EQUIPMENT_AVAILABLE_BONUS
    if candidate.equipment and candidate.equipment == source.equipment:
        score += SAME_EQUIPMENT_BONUS
    if candidate.category == source.category:
        score += SAME_CATEGORY_BONUS

    return round(score, 4)


def rank_alternatives(
    source: CandidateProfile,
    candidates: list[CandidateProfile],
    available_equipment: set[str] | None = None,
) -> list[tuple[CandidateProfile, float]]:
    """Return (candidate, score) pairs sorted best-first, ties broken by name."""
    scored = [(c, score_alternative(source, c, available_equipment)) for c in candidates]
    scored.sort(key=lambda pair: (-pair[1], pair[0].name))
    return scored


def _profile(exercise, *, curated: bool = False) -> CandidateProfile:
    return CandidateProfile(
        slug=exercise.slug,
        name=exercise.name,
        primary=frozenset(m.slug for m in exercise.primary_muscles.all()),
        secondary=frozenset(m.slug for m in exercise.secondary_muscles.all()),
        equipment=exercise.equipment.slug,
        category=exercise.category,
        curated=curated,
    )


def ranked_alternatives(
    source_exercise, *, user=None, available_equipment: set[str] | None = None, limit: int = 8
) -> list:
    """Return up to `limit` `Exercise` objects (each annotated with `.sub_score`)
    that substitute `source_exercise`, ranked best-first.

    Candidate set: exercises visible to `user` that share a primary muscle with
    the source OR are curated alternatives of it. The source itself and inactive
    rows are excluded.
    """
    from django.db.models import Q

    from gymapp.apps.exercises.models import Exercise, ExerciseAlternative

    src = source_exercise
    src_primary_ids = list(src.primary_muscles.values_list("id", flat=True))
    curated_slugs = set(
        ExerciseAlternative.objects.filter(from_exercise=src).values_list(
            "to_exercise__slug", flat=True
        )
    )

    candidates = list(
        Exercise.objects.visible_to(user)
        .filter(Q(primary_muscles__in=src_primary_ids) | Q(slug__in=curated_slugs))
        .exclude(pk=src.pk)
        .distinct()
        .select_related("equipment")
        .prefetch_related("primary_muscles", "secondary_muscles")
    )

    src_profile = _profile(src)
    for ex in candidates:
        ex.sub_score = score_alternative(
            src_profile, _profile(ex, curated=ex.slug in curated_slugs), available_equipment
        )
    candidates.sort(key=lambda e: (-e.sub_score, e.name))
    return candidates[:limit]


class SubstitutionStrategy(Protocol):
    def alternatives_for(self, exercise_slug: str, available_equipment: list[str]) -> list[str]: ...


class DeterministicSubstitution:
    def __init__(self, library: ExerciseLibraryStrategy | None = None) -> None:
        self._library = library or DeterministicExerciseLibrary()

    def alternatives_for(self, exercise_slug: str, available_equipment: list[str]) -> list[str]:
        """Ranked substitute slugs for a global exercise (best-first)."""
        from gymapp.apps.exercises.models import Exercise

        try:
            src = Exercise.objects.get(owner__isnull=True, slug=exercise_slug)
        except Exercise.DoesNotExist:
            return []
        avail = set(available_equipment) if available_equipment else None
        return [ex.slug for ex in ranked_alternatives(src, user=None, available_equipment=avail)]
