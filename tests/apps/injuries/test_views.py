"""CRUD + UI-integration tests for the injuries app."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from gymapp.apps.exercises.models import Equipment, Exercise
from gymapp.apps.injuries.models import Injury
from tests.factories import UserFactory


@pytest.fixture
def alice(db):
    return UserFactory(email="alice.inj@example.com")


@pytest.fixture
def bench(db):
    eq, _ = Equipment.objects.get_or_create(slug="barbell-inj", defaults={"name": "Barbell-Inj"})
    return Exercise.objects.create(
        slug="bench-inj", name="Bench-Inj", equipment=eq, category="compound"
    )


@pytest.mark.django_db
def test_list_renders_active_and_resolved_sections(alice, bench, client):
    Injury.objects.create(owner=alice, name="ActiveLumbar", started_on=timezone.localdate())
    Injury.objects.create(
        owner=alice,
        name="HealedShoulder",
        started_on=timezone.localdate() - timedelta(days=30),
        resolved_on=timezone.localdate() - timedelta(days=5),
    )
    client.force_login(alice)
    resp = client.get(reverse("injuries:list"))
    assert resp.status_code == 200
    assert b"ActiveLumbar" in resp.content
    assert b"HealedShoulder" in resp.content


@pytest.mark.django_db
def test_create_persists_and_redirects_to_edit(alice, client):
    client.force_login(alice)
    resp = client.post(
        reverse("injuries:create"),
        {
            "name": "Lumbalgia",
            "body_region": "lower_back",
            "severity": "moderate",
            "started_on": timezone.localdate().isoformat(),
            "notes": "después de PR de peso muerto",
        },
    )
    assert resp.status_code == 302
    inj = Injury.objects.get(owner=alice, name="Lumbalgia")
    assert resp.url == reverse("injuries:edit", args=[inj.id])
    assert inj.is_active
    assert inj.body_region == "lower_back"


@pytest.mark.django_db
def test_toggle_marks_resolved_then_active_again(alice, client):
    inj = Injury.objects.create(owner=alice, name="X", started_on=timezone.localdate())
    client.force_login(alice)
    client.post(reverse("injuries:toggle", args=[inj.id]))
    inj.refresh_from_db()
    assert not inj.is_active
    client.post(reverse("injuries:toggle", args=[inj.id]))
    inj.refresh_from_db()
    assert inj.is_active


@pytest.mark.django_db
def test_delete_removes(alice, client):
    inj = Injury.objects.create(owner=alice, name="X", started_on=timezone.localdate())
    client.force_login(alice)
    client.post(reverse("injuries:delete", args=[inj.id]))
    assert not Injury.objects.filter(id=inj.id).exists()


@pytest.mark.django_db
def test_avoid_add_and_remove(alice, bench, client):
    inj = Injury.objects.create(owner=alice, name="X", started_on=timezone.localdate())
    client.force_login(alice)
    client.post(reverse("injuries:avoid_add", args=[inj.id]), {"slug": bench.slug})
    assert bench in inj.avoid_exercises.all()
    client.post(reverse("injuries:avoid_remove", args=[inj.id, bench.id]))
    assert bench not in inj.avoid_exercises.all()


@pytest.mark.django_db
def test_cannot_edit_other_users_injury(alice, client):
    bob = UserFactory(email="bob.inj@example.com")
    bobs = Injury.objects.create(owner=bob, name="BobsBack", started_on=timezone.localdate())
    client.force_login(alice)
    resp = client.get(reverse("injuries:edit", args=[bobs.id]))
    assert resp.status_code == 404
    resp2 = client.post(reverse("injuries:delete", args=[bobs.id]))
    assert resp2.status_code == 404
    assert Injury.objects.filter(id=bobs.id).exists()


@pytest.mark.django_db
def test_avoid_add_rejects_unknown_exercise(alice, client):
    inj = Injury.objects.create(owner=alice, name="X", started_on=timezone.localdate())
    client.force_login(alice)
    resp = client.post(
        reverse("injuries:avoid_add", args=[inj.id]), {"slug": "does-not-exist-zzz"}
    )
    assert resp.status_code == 404


# ---------- UI integration ----------


@pytest.mark.django_db
def test_workout_session_page_shows_warning_for_avoided_exercise(alice, bench, client):
    from gymapp.apps.workouts.models import ExerciseLog, WorkoutSession, WorkoutStatus

    inj = Injury.objects.create(
        owner=alice, name="ActiveBack", started_on=timezone.localdate()
    )
    inj.avoid_exercises.add(bench)

    sess = WorkoutSession.objects.create(
        owner=alice, status=WorkoutStatus.IN_PROGRESS, started_at=timezone.now()
    )
    ExerciseLog.objects.create(session=sess, exercise=bench, ordering=0)
    client.force_login(alice)
    resp = client.get(reverse("workouts:session", args=[sess.id]))
    assert resp.status_code == 200
    assert b"Te recomendamos evitar este ejercicio" in resp.content


@pytest.mark.django_db
def test_workout_session_page_no_warning_when_injury_resolved(alice, bench, client):
    from gymapp.apps.workouts.models import ExerciseLog, WorkoutSession, WorkoutStatus

    inj = Injury.objects.create(
        owner=alice,
        name="HealedBack",
        started_on=timezone.localdate() - timedelta(days=30),
        resolved_on=timezone.localdate() - timedelta(days=5),
    )
    inj.avoid_exercises.add(bench)
    sess = WorkoutSession.objects.create(
        owner=alice, status=WorkoutStatus.IN_PROGRESS, started_at=timezone.now()
    )
    ExerciseLog.objects.create(session=sess, exercise=bench, ordering=0)
    client.force_login(alice)
    resp = client.get(reverse("workouts:session", args=[sess.id]))
    assert b"Te recomendamos evitar este ejercicio" not in resp.content


@pytest.mark.django_db
def test_workout_session_picker_shows_block_badge_for_avoided(alice, bench, client):
    from gymapp.apps.workouts.models import WorkoutSession, WorkoutStatus

    inj = Injury.objects.create(
        owner=alice, name="ActiveBack", started_on=timezone.localdate()
    )
    inj.avoid_exercises.add(bench)
    sess = WorkoutSession.objects.create(
        owner=alice, status=WorkoutStatus.IN_PROGRESS, started_at=timezone.now()
    )
    client.force_login(alice)
    resp = client.get(reverse("workouts:session", args=[sess.id]))
    # The 🚫 emoji should appear in the picker section before bench's name.
    assert "🚫".encode() in resp.content
