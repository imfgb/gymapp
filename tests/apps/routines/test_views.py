"""Smoke tests for the routine CRUD views."""

from __future__ import annotations

import re

import pytest
from django.urls import reverse

from gymapp.apps.exercises.models import Exercise
from gymapp.apps.routines.models import Routine, RoutineDay, RoutineExercise, WeeklySplit
from tests.factories import EquipmentFactory, ExerciseFactory, UserFactory


@pytest.fixture
def alice(db):
    return UserFactory(email="alice@example.com")


@pytest.mark.django_db
def test_routine_list_renders_empty(client, alice):
    client.force_login(alice)
    resp = client.get(reverse("routines:list"))
    assert resp.status_code == 200
    assert "Aún no tienes rutinas".encode() in resp.content


@pytest.mark.django_db
def test_routine_create_manual_redirects_to_detail(client, alice):
    client.force_login(alice)
    resp = client.post(
        reverse("routines:create"),
        data={"name": "My Routine", "training_style": "powerbuilding", "mode": "manual"},
    )
    routine = Routine.objects.for_user(alice).get(name="My Routine")
    assert resp.status_code == 302
    assert resp.url == reverse("routines:detail", args=[routine.id])
    assert routine.days.count() == 0


@pytest.mark.django_db
def test_routine_create_generator_populates_days(client, alice):
    client.force_login(alice)
    resp = client.post(
        reverse("routines:create"),
        data={
            "name": "Gen PPL",
            "training_style": "powerbuilding",
            "mode": "generate",
            "preset": "ppl_3",
        },
    )
    routine = Routine.objects.for_user(alice).get(name="Gen PPL")
    assert resp.status_code == 302
    assert routine.days.count() == 3
    # Each generated day should have at least one exercise from the seed.
    for day in routine.days.all():
        assert day.exercises.count() >= 1


@pytest.mark.django_db
def test_routine_preview_returns_html_fragment(client, alice):
    client.force_login(alice)
    resp = client.post(
        reverse("routines:preview"),
        data={"preset": "ppl_3", "training_style": "powerbuilding"},
    )
    assert resp.status_code == 200
    assert b"Push" in resp.content


@pytest.mark.django_db
def test_routine_detail_isolated_per_owner(client, alice):
    bob = UserFactory(email="bob@example.com")
    bobs = Routine.objects.create(owner=bob, name="Bob's")
    client.force_login(alice)
    resp = client.get(reverse("routines:detail", args=[bobs.id]))
    assert resp.status_code == 404


@pytest.mark.django_db
def test_routine_delete_removes_routine(client, alice):
    r = Routine.objects.create(owner=alice, name="Goner")
    client.force_login(alice)
    resp = client.post(reverse("routines:delete", args=[r.id]))
    assert resp.status_code == 302
    assert not Routine.objects.filter(id=r.id).exists()


@pytest.mark.django_db
def test_day_add_returns_card_partial(client, alice):
    r = Routine.objects.create(owner=alice, name="R")
    client.force_login(alice)
    resp = client.post(reverse("routines:day_add", args=[r.id]), data={"label": "Push A"})
    assert resp.status_code == 200
    assert b"Push A" in resp.content
    assert RoutineDay.objects.filter(routine=r).count() == 1


@pytest.mark.django_db
def test_exercise_add_custom_creates_searchable_exercise(client, alice):
    """Creating a custom exercise from the routine editor adds it to the day and
    makes it an owner-scoped Exercise (searchable later)."""
    EquipmentFactory(slug="barbell", name="Barbell")
    r = Routine.objects.create(owner=alice, name="R", training_style=alice.profile.training_style)
    day = RoutineDay.objects.create(routine=r, label="Push A", ordering=0)
    client.force_login(alice)

    resp = client.post(
        reverse("routines:exercise_add_custom", args=[r.id, day.id]),
        data={"name": "Hip Thrust", "equipment": "barbell"},
    )

    assert resp.status_code == 200
    ex = Exercise.objects.get(owner=alice, slug="hip-thrust")
    assert ex.name == "Hip Thrust"
    assert day.exercises.filter(exercise=ex).exists()
    assert b"Hip Thrust" in resp.content


@pytest.mark.django_db
def test_exercise_add_custom_rejects_blank_name(client, alice):
    EquipmentFactory(slug="barbell", name="Barbell")
    r = Routine.objects.create(owner=alice, name="R")
    day = RoutineDay.objects.create(routine=r, label="Push A", ordering=0)
    client.force_login(alice)

    resp = client.post(
        reverse("routines:exercise_add_custom", args=[r.id, day.id]),
        data={"name": "  ", "equipment": "barbell"},
    )

    assert resp.status_code == 400


@pytest.mark.django_db
def test_day_add_rejects_duplicate_label(client, alice):
    r = Routine.objects.create(owner=alice, name="R")
    RoutineDay.objects.create(routine=r, label="Push A", ordering=0)
    client.force_login(alice)
    resp = client.post(reverse("routines:day_add", args=[r.id]), data={"label": "Push A"})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_editor_autosave_does_not_reswap_the_day_card(client, alice):
    """bug #11: the inline auto-save must NOT re-render the whole day card.

    Re-swapping on every `change` reverted a field the user was mid-editing
    (e.g. cleared to retype) back to its old value. The auto-save form now
    saves silently (`hx-swap="none"`).
    """
    r = Routine.objects.create(owner=alice, name="R", training_style=alice.profile.training_style)
    day = RoutineDay.objects.create(routine=r, label="Push A", ordering=0)
    RoutineExercise.objects.create(
        routine_day=day,
        exercise=ExerciseFactory(),
        ordering=0,
        target_sets=3,
        target_reps_low=8,
        target_reps_high=12,
    )
    client.force_login(alice)
    content = client.get(reverse("routines:detail", args=[r.id])).content.decode()

    # The change-triggered auto-save <form ...> opening tag must swap nothing.
    match = re.search(r'<form\b[^>]*hx-trigger="change delay:400ms"[^>]*>', content)
    assert match, "auto-save form not found on the editor page"
    form_tag = match.group(0)
    assert 'hx-swap="none"' in form_tag
    assert "outerHTML" not in form_tag  # would re-render the card and revert edits


@pytest.mark.django_db
def test_exercise_update_persists_and_renders_weight_with_period(client, alice):
    """Editing the weight must save it and re-render it with a period decimal
    separator. Under the es-mx locale a Decimal renders as '60,00', which an
    <input type="number"> rejects and blanks — so the value must be unlocalized."""
    r = Routine.objects.create(owner=alice, name="R", training_style=alice.profile.training_style)
    day = RoutineDay.objects.create(routine=r, label="Push A", ordering=0)
    rex = RoutineExercise.objects.create(
        routine_day=day,
        exercise=ExerciseFactory(),
        ordering=0,
        target_sets=3,
        target_reps_low=8,
        target_reps_high=12,
    )
    client.force_login(alice)

    resp = client.post(
        reverse("routines:exercise_update", args=[r.id, day.id, rex.id]),
        data={
            "target_sets": "3",
            "target_reps_low": "8",
            "target_reps_high": "12",
            "target_weight_kg": "60",
            "rest_seconds": "",
        },
    )

    assert resp.status_code == 200
    rex.refresh_from_db()
    assert rex.target_weight_kg == 60
    content = resp.content.decode()
    assert 'value="60.00"' in content
    assert "60,00" not in content


@pytest.mark.django_db
def test_exercise_update_drops_negative_weight_and_clamps_rest(client, alice):
    """A negative target weight would prefill into a session and corrupt
    tonnage; a negative rest timer is nonsense. Both are sanitised."""
    r = Routine.objects.create(owner=alice, name="R", training_style=alice.profile.training_style)
    day = RoutineDay.objects.create(routine=r, label="Push A", ordering=0)
    rex = RoutineExercise.objects.create(
        routine_day=day,
        exercise=ExerciseFactory(),
        ordering=0,
        target_sets=3,
        target_reps_low=8,
        target_reps_high=12,
    )
    client.force_login(alice)

    resp = client.post(
        reverse("routines:exercise_update", args=[r.id, day.id, rex.id]),
        data={
            "target_sets": "3",
            "target_reps_low": "8",
            "target_reps_high": "12",
            "target_weight_kg": "-60",
            "rest_seconds": "-30",
        },
    )

    assert resp.status_code == 200
    rex.refresh_from_db()
    assert rex.target_weight_kg is None  # negative dropped
    assert rex.rest_seconds == 0  # clamped, not negative


@pytest.mark.django_db
def test_weekly_split_empty_state_without_routines(client, alice):
    client.force_login(alice)
    resp = client.get(reverse("routines:weekly_split"))
    assert resp.status_code == 200
    assert b"Crea una rutina" in resp.content


@pytest.mark.django_db
def test_weekly_split_renders_7_weekday_selects(client, alice):
    r = Routine.objects.create(owner=alice, name="R")
    RoutineDay.objects.create(routine=r, label="Push A", ordering=0)
    client.force_login(alice)
    resp = client.get(reverse("routines:weekly_split"))
    assert resp.status_code == 200
    # One bulk form with a select per weekday (weekday_0 .. weekday_6).
    for wd in range(7):
        assert f'name="weekday_{wd}"'.encode() in resp.content


@pytest.mark.django_db
def test_weekly_split_save_persists_whole_week(client, alice):
    r = Routine.objects.create(owner=alice, name="R")
    push = RoutineDay.objects.create(routine=r, label="Push", ordering=0)
    pull = RoutineDay.objects.create(routine=r, label="Pull", ordering=1)
    client.force_login(alice)
    resp = client.post(
        reverse("routines:weekly_split_save"),
        data={
            "weekday_0": str(push.id),
            "weekday_2": str(pull.id),
            # the rest left blank -> rest days
        },
    )
    assert resp.status_code == 302
    assert WeeklySplit.objects.get(owner=alice, weekday=0).routine_day_id == push.id
    assert WeeklySplit.objects.get(owner=alice, weekday=2).routine_day_id == pull.id
    assert WeeklySplit.objects.get(owner=alice, weekday=1).routine_day_id is None


@pytest.mark.django_db
def test_generate_routine_auto_schedules_week(client, alice):
    """Generating a 3-day routine fills the week (Mon/Wed/Fri) so the dashboard
    shows 'today' without a manual split assignment."""
    client.force_login(alice)
    client.post(
        reverse("routines:create"),
        data={
            "name": "Auto PPL",
            "training_style": "powerbuilding",
            "mode": "generate",
            "preset": "ppl_3",
        },
    )
    routine = Routine.objects.for_user(alice).get(name="Auto PPL")
    days = list(routine.days.order_by("ordering"))
    assert WeeklySplit.objects.get(owner=alice, weekday=0).routine_day_id == days[0].id
    assert WeeklySplit.objects.get(owner=alice, weekday=2).routine_day_id == days[1].id
    assert WeeklySplit.objects.get(owner=alice, weekday=4).routine_day_id == days[2].id
    # Tuesday is a rest day.
    assert WeeklySplit.objects.get(owner=alice, weekday=1).routine_day_id is None


@pytest.mark.django_db
def test_apply_to_week_programs_routine(client, alice):
    r = Routine.objects.create(owner=alice, name="Mi rutina")
    d0 = RoutineDay.objects.create(routine=r, label="A", ordering=0)
    d1 = RoutineDay.objects.create(routine=r, label="B", ordering=1)
    client.force_login(alice)
    resp = client.post(reverse("routines:apply_to_week", args=[r.id]))
    assert resp.status_code == 302
    assert resp.url == reverse("routines:weekly_split")
    # 2 days -> Monday + Thursday.
    assert WeeklySplit.objects.get(owner=alice, weekday=0).routine_day_id == d0.id
    assert WeeklySplit.objects.get(owner=alice, weekday=3).routine_day_id == d1.id


@pytest.mark.django_db
def test_apply_to_week_replaces_previous_schedule(client, alice):
    old = Routine.objects.create(owner=alice, name="Vieja")
    old_day = RoutineDay.objects.create(routine=old, label="Old", ordering=0)
    WeeklySplit.objects.create(owner=alice, weekday=6, routine_day=old_day)

    new = Routine.objects.create(owner=alice, name="Nueva")
    new_day = RoutineDay.objects.create(routine=new, label="New", ordering=0)
    client.force_login(alice)
    client.post(reverse("routines:apply_to_week", args=[new.id]))
    # 1 day -> Monday; the old Sunday assignment is cleared.
    assert WeeklySplit.objects.get(owner=alice, weekday=0).routine_day_id == new_day.id
    assert WeeklySplit.objects.get(owner=alice, weekday=6).routine_day_id is None


@pytest.mark.django_db
def test_weekly_split_assign_persists(client, alice):
    r = Routine.objects.create(owner=alice, name="R")
    day = RoutineDay.objects.create(routine=r, label="Push A", ordering=0)
    client.force_login(alice)
    resp = client.post(
        reverse("routines:weekly_split_assign", args=[1]),
        data={"routine_day": str(day.id)},
    )
    assert resp.status_code == 302
    split = WeeklySplit.objects.get(owner=alice, weekday=1)
    assert split.routine_day_id == day.id


@pytest.mark.django_db
def test_weekly_split_assign_rest_day_clears(client, alice):
    r = Routine.objects.create(owner=alice, name="R")
    day = RoutineDay.objects.create(routine=r, label="Push A", ordering=0)
    WeeklySplit.objects.create(owner=alice, weekday=1, routine_day=day)
    client.force_login(alice)
    resp = client.post(
        reverse("routines:weekly_split_assign", args=[1]),
        data={"routine_day": ""},
    )
    assert resp.status_code == 302
    split = WeeklySplit.objects.get(owner=alice, weekday=1)
    assert split.routine_day_id is None


def _mk_rex(day, slug, **kw):
    return RoutineExercise.objects.create(
        routine_day=day,
        exercise=ExerciseFactory(slug=slug),
        target_sets=3,
        target_reps_low=8,
        target_reps_high=12,
        **kw,
    )


@pytest.mark.django_db
def test_exercise_move_reorders_within_day(client, alice):
    """bug #4: ↑/↓ reorder a RoutineExercise within its day."""
    r = Routine.objects.create(owner=alice, name="R", training_style=alice.profile.training_style)
    day = RoutineDay.objects.create(routine=r, label="Push", ordering=0)
    a = _mk_rex(day, "a", ordering=0)
    _mk_rex(day, "b", ordering=1)
    c = _mk_rex(day, "c", ordering=2)
    client.force_login(alice)

    def order():
        return list(day.exercises.values_list("exercise__slug", flat=True))

    assert order() == ["a", "b", "c"]
    client.post(reverse("routines:exercise_move", args=[r.id, day.id, c.id]), {"direction": "up"})
    assert order() == ["a", "c", "b"]
    # moving the first one up is a no-op
    client.post(reverse("routines:exercise_move", args=[r.id, day.id, a.id]), {"direction": "up"})
    assert order() == ["a", "c", "b"]
    client.post(reverse("routines:exercise_move", args=[r.id, day.id, a.id]), {"direction": "down"})
    assert order() == ["c", "a", "b"]


@pytest.mark.django_db
def test_exercise_move_renumbers_when_orderings_collide(client, alice):
    """Legacy rows can all share ordering=0; moving must still reorder them
    (renumber, not just swap two equal values)."""
    r = Routine.objects.create(owner=alice, name="R", training_style=alice.profile.training_style)
    day = RoutineDay.objects.create(routine=r, label="Push", ordering=0)
    _mk_rex(day, "a", ordering=0)
    b = _mk_rex(day, "b", ordering=0)
    client.force_login(alice)

    client.post(reverse("routines:exercise_move", args=[r.id, day.id, b.id]), {"direction": "up"})
    assert list(day.exercises.values_list("exercise__slug", flat=True)) == ["b", "a"]
