"""Smoke tests for the routine CRUD views."""
from __future__ import annotations

import pytest
from django.urls import reverse

from gymapp.apps.routines.models import Routine, RoutineDay, WeeklySplit

from tests.factories import UserFactory


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
def test_day_add_rejects_duplicate_label(client, alice):
    r = Routine.objects.create(owner=alice, name="R")
    RoutineDay.objects.create(routine=r, label="Push A", ordering=0)
    client.force_login(alice)
    resp = client.post(reverse("routines:day_add", args=[r.id]), data={"label": "Push A"})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_weekly_split_renders_7_rows(client, alice):
    client.force_login(alice)
    resp = client.get(reverse("routines:weekly_split"))
    assert resp.status_code == 200
    # Spanish weekday labels — at least Monday and Sunday should be present.
    assert b"Monday" in resp.content or b"Lunes" in resp.content
    # 7 forms, one per weekday.
    assert resp.content.count(b'<form method="post"') >= 7


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
