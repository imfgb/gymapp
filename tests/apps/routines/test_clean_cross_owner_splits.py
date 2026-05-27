"""Tests for the clean_cross_owner_splits management command."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from gymapp.apps.routines.models import Routine, RoutineDay, WeeklySplit
from tests.factories import UserFactory


def _run(*args) -> str:
    """Invoke the command and return its stdout."""
    out = StringIO()
    call_command("clean_cross_owner_splits", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_legit_and_rest_day_rows_are_left_alone():
    alice = UserFactory(email="alice@example.com")
    routine = Routine.objects.create(owner=alice, name="A")
    day = RoutineDay.objects.create(routine=routine, label="Push", ordering=0)
    legit = WeeklySplit.objects.create(owner=alice, weekday=0, routine_day=day)
    rest = WeeklySplit.objects.create(owner=alice, weekday=1, routine_day=None)

    out = _run("--apply")

    legit.refresh_from_db()
    rest.refresh_from_db()
    assert legit.routine_day_id == day.id
    assert rest.routine_day_id is None
    assert "Nothing to do" in out


@pytest.mark.django_db
def test_cross_owner_row_is_nulled_when_apply():
    bob = UserFactory(email="bob@example.com")
    alice = UserFactory(email="alice@example.com")
    bob_routine = Routine.objects.create(owner=bob, name="BobR")
    bob_day = RoutineDay.objects.create(routine=bob_routine, label="BobPush", ordering=0)
    # Alice's split points at bob's day -> the legacy bug.
    stale = WeeklySplit.objects.create(owner=alice, weekday=0, routine_day=bob_day)

    out = _run("--apply")

    stale.refresh_from_db()
    assert stale.routine_day_id is None
    assert "Updated 1 row" in out
    # Bob's RoutineDay itself is untouched (we only null the FK on alice's row).
    assert RoutineDay.objects.filter(id=bob_day.id).exists()


@pytest.mark.django_db
def test_dry_run_does_not_mutate():
    bob = UserFactory(email="bob@example.com")
    alice = UserFactory(email="alice@example.com")
    bob_routine = Routine.objects.create(owner=bob, name="BobR")
    bob_day = RoutineDay.objects.create(routine=bob_routine, label="BobPush", ordering=0)
    stale = WeeklySplit.objects.create(owner=alice, weekday=0, routine_day=bob_day)

    out = _run()  # no --apply

    stale.refresh_from_db()
    assert stale.routine_day_id == bob_day.id  # untouched
    assert "Dry-run only" in out
    assert "1 are cross-owner" in out


@pytest.mark.django_db
def test_idempotent_second_apply_is_noop():
    bob = UserFactory(email="bob@example.com")
    alice = UserFactory(email="alice@example.com")
    bob_routine = Routine.objects.create(owner=bob, name="BobR")
    bob_day = RoutineDay.objects.create(routine=bob_routine, label="BobPush", ordering=0)
    WeeklySplit.objects.create(owner=alice, weekday=0, routine_day=bob_day)

    _run("--apply")
    out_second = _run("--apply")

    assert "Nothing to do" in out_second
