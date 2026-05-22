"""PR detection service.

Called from `workouts.finish_session`. Walks all completed working SetLogs in
the session and upserts PRs:
    one row per (owner, exercise, reps); we keep the heaviest weight observed.
"""

from __future__ import annotations

from django.db import transaction


@transaction.atomic
def update_prs_from_session(session) -> list:
    """Returns a list of (PR, was_new_or_improved) tuples for any PR that was
    touched. Idempotent: re-running on a session that already triggered PR
    detection is a no-op when no new heavier weight surfaced."""
    from gymapp.apps.prs.models import PersonalRecord, PRSource

    touched: list = []

    sets = session.exercise_logs.select_related("exercise").prefetch_related("set_logs").all()
    for elog in sets:
        for s in elog.set_logs.all():
            if s.completed_at is None or s.is_warmup:
                continue
            if s.weight_kg is None or s.reps is None:
                continue
            pr, created = PersonalRecord.objects.get_or_create(
                owner_id=session.owner_id,
                exercise_id=elog.exercise_id,
                reps=s.reps,
                defaults={
                    "weight_kg": s.weight_kg,
                    "achieved_at": s.completed_at,
                    "source": PRSource.AUTO,
                    "source_set": s,
                },
            )
            improved = False
            if not created and s.weight_kg > pr.weight_kg:
                pr.weight_kg = s.weight_kg
                pr.achieved_at = s.completed_at
                pr.source = PRSource.AUTO
                pr.source_set = s
                pr.save()
                improved = True
            if created or improved:
                touched.append((pr, created or improved))

    return touched
