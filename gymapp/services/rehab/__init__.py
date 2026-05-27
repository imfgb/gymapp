"""Rehab / prevention service.

Reads the user's ACTIVE injuries (`resolved_on` is null) and exposes:

- `avoided_exercise_ids(user)`: a set of exercise IDs the user has flagged as
  unsafe across all their active injuries. Cheap to compute, safe to call in
  request handlers (small queryset).
- `warnings_for_exercise(exercise, user)`: the list of active injuries that
  specifically warn against that exercise — used to render the warning banner
  on the workout exercise card.

Both are deterministic and read-only. Owner-scoped via `Injury.objects.for_user`.
"""

from __future__ import annotations

from gymapp.apps.injuries.models import Injury, MobilityExercise


def _active_for_user(user):
    return Injury.objects.for_user(user).filter(resolved_on__isnull=True)


def avoided_exercise_ids(user) -> set[int]:
    """All exercise IDs the user has flagged across any active injury."""
    if user is None or not user.is_authenticated:
        return set()
    return set(
        _active_for_user(user)
        .values_list("avoid_exercises", flat=True)
        # Some injuries have no exercises attached -> None comes back from the
        # M2M reverse and would pollute the set.
        .exclude(avoid_exercises__isnull=True)
    )


def warnings_for_exercise(exercise, user) -> list[Injury]:
    """All active injuries that warn against this specific exercise."""
    if user is None or not user.is_authenticated or exercise is None:
        return []
    return list(
        _active_for_user(user).filter(avoid_exercises=exercise).order_by("name")
    )


def mobility_for_user(user, *, per_region: int = 2) -> list:
    """Suggested mobility moves grouped by the user's ACTIVE injury regions.

    Returns at most `per_region` mobility exercises per region the user has
    flagged. Empty list when the user has no active injuries.
    """
    if user is None or not user.is_authenticated:
        return []
    regions = list(_active_for_user(user).values_list("body_region", flat=True).distinct())
    if not regions:
        return []
    moves: list = []
    seen_ids: set[int] = set()
    for region in regions:
        for m in (
            MobilityExercise.objects.filter(body_region=region, is_active=True).order_by("name")[:per_region]
        ):
            if m.id in seen_ids:
                continue
            seen_ids.add(m.id)
            moves.append(m)
    return moves


def mobility_for_region(body_region: str, *, limit: int = 5) -> list:
    """All mobility moves for one body region (for the injury detail page)."""
    return list(
        MobilityExercise.objects.filter(body_region=body_region, is_active=True)
        .order_by("name")[:limit]
    )


def suggested_swap(exercise, user):
    """Return one Exercise to suggest swapping `exercise` for, picked from
    `ranked_alternatives` minus the user's avoid list. None if no candidate."""
    if user is None or not user.is_authenticated or exercise is None:
        return None
    from gymapp.services.substitution import ranked_alternatives

    avoid = avoided_exercise_ids(user)
    for alt in ranked_alternatives(exercise, user=user, limit=10):
        if alt.id not in avoid:
            return alt
    return None


__all__ = [
    "avoided_exercise_ids",
    "warnings_for_exercise",
    "mobility_for_user",
    "mobility_for_region",
    "suggested_swap",
]
