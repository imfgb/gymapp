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

from gymapp.apps.injuries.models import Injury


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


__all__ = ["avoided_exercise_ids", "warnings_for_exercise"]
