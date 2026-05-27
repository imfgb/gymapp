"""One-time cleanup: null any WeeklySplit row whose routine_day belongs to a
different user.

These rows came from a past bug where `OwnerScopedQuerySet.for_user()`
short-circuited for superusers and let `apply_to_week` save splits pointing
at another user's RoutineDay. The render path already guards against this
(defense-in-depth in dashboard + workouts.start), so users are not
*currently* leaked the other owner's data — but the stale rows still live
in the DB and confuse the split editor.

Idempotent: a second run touches zero rows. Defaults to dry-run for safety;
pass `--apply` to actually write.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from gymapp.apps.routines.models import WeeklySplit


class Command(BaseCommand):
    help = (
        "Find WeeklySplit rows whose routine_day is owned by a different user "
        "and null them. Dry-run by default; use --apply to actually write."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually update rows. Without this, only report what would change.",
        )

    def handle(self, *args, apply: bool = False, **opts) -> None:
        # Walk every assigned row; we need to compare owner_id against
        # routine_day.routine.owner_id.
        with_assignment = (
            WeeklySplit.objects.exclude(routine_day__isnull=True)
            .select_related("routine_day__routine")
        )

        stale_ids: list[int] = []
        for split in with_assignment:
            owner_of_day = split.routine_day.routine.owner_id
            if owner_of_day != split.owner_id:
                stale_ids.append(split.pk)
                self.stdout.write(
                    f"  - split #{split.pk}: owner={split.owner_id} "
                    f"weekday={split.weekday} -> routine_day #{split.routine_day_id} "
                    f"owned by user #{owner_of_day} (CROSS-OWNER)"
                )

        total = with_assignment.count()
        found = len(stale_ids)
        self.stdout.write(
            self.style.NOTICE(
                f"Inspected {total} assigned WeeklySplit rows; {found} are cross-owner."
            )
        )

        if not stale_ids:
            self.stdout.write(self.style.SUCCESS("Nothing to do."))
            return

        if not apply:
            self.stdout.write(
                self.style.WARNING(
                    "Dry-run only. Re-run with --apply to null those routine_day FKs."
                )
            )
            return

        with transaction.atomic():
            updated = WeeklySplit.objects.filter(pk__in=stale_ids).update(routine_day=None)
        self.stdout.write(
            self.style.SUCCESS(f"Updated {updated} row(s) → routine_day=None.")
        )
