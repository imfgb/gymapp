"""Regression tests for OwnerScopedQuerySet.for_user().

A past bug let `for_user(superuser)` return EVERY user's rows on regular pages
(dashboard, routines, metrics, PRs). Superuser-sees-all belongs in `/admin`
only (via OwnerScopedAdmin), not in the app's data-reading code path.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from gymapp.apps.metrics.models import UserMetricSnapshot
from gymapp.apps.routines.models import Routine
from tests.factories import UserFactory


@pytest.mark.django_db
def test_for_user_does_not_leak_across_users_for_superuser():
    superuser = UserFactory(email="su@example.com", is_superuser=True, is_staff=True)
    bob = UserFactory(email="bob@example.com")
    Routine.objects.create(owner=bob, name="Bob's routine")

    # Even though superuser is_superuser=True, for_user must NOT return bob's row.
    assert list(Routine.objects.for_user(superuser)) == []
    assert Routine.objects.for_user(bob).count() == 1


@pytest.mark.django_db
def test_dashboard_does_not_show_other_users_data_to_superuser(client):
    superuser = UserFactory(email="su@example.com", is_superuser=True, is_staff=True)
    bob = UserFactory(email="bob@example.com")
    Routine.objects.create(owner=bob, name="BobSecretRoutine")
    from django.utils import timezone
    UserMetricSnapshot.objects.create(owner=bob, weight_kg=99, measured_at=timezone.now())

    client.force_login(superuser)
    resp = client.get(reverse("dashboard:home"))
    assert resp.status_code == 200
    # Bob's data must not appear on the superuser's dashboard.
    assert b"BobSecretRoutine" not in resp.content

    resp_routines = client.get(reverse("routines:list"))
    assert b"BobSecretRoutine" not in resp_routines.content

    resp_metrics = client.get(reverse("metrics:list"))
    # Superuser is isolated -> metrics table is empty.
    assert "Aún no has registrado mediciones".encode() in resp_metrics.content
    assert b"99.0 kg" not in resp_metrics.content
    assert b"99 kg" not in resp_metrics.content


@pytest.mark.django_db
def test_dashboard_ignores_stale_split_pointing_at_other_user_day(client):
    """If a (legacy) WeeklySplit row points at another user's RoutineDay, the
    dashboard must treat that slot as a rest day, never render the other user's
    routine name."""
    from gymapp.apps.routines.models import RoutineDay, WeeklySplit

    me = UserFactory(email="me@example.com")
    other = UserFactory(email="other@example.com")
    other_routine = Routine.objects.create(owner=other, name="OtherSecretRoutine")
    other_day = RoutineDay.objects.create(routine=other_routine, label="OtherSecretDay", ordering=0)
    # Stale cross-owner assignment that should NOT be shown to `me`.
    WeeklySplit.objects.create(owner=me, weekday=0, routine_day=other_day)

    client.force_login(me)
    resp = client.get(reverse("dashboard:home"))
    assert resp.status_code == 200
    assert b"OtherSecretRoutine" not in resp.content
    assert b"OtherSecretDay" not in resp.content


@pytest.mark.django_db
def test_for_user_returns_empty_for_anonymous():
    from django.contrib.auth.models import AnonymousUser

    bob = UserFactory(email="bob@example.com")
    Routine.objects.create(owner=bob, name="X")

    assert Routine.objects.for_user(AnonymousUser()).count() == 0
    assert Routine.objects.for_user(None).count() == 0


# ---------------------------------------------------------------------------
# Regression: every public app page must not leak another user's data,
# regardless of whether the viewer is a superuser. One test per app surface.
# ---------------------------------------------------------------------------


def _make_bob_with_workout_data():
    """Build a fully-populated bob: routine + day + finished session + set + PR
    + body snapshot + meal + supplement. Returns bob and a few identifying
    strings that must NEVER appear in another user's response."""
    from datetime import timedelta

    from django.utils import timezone

    from gymapp.apps.exercises.models import Equipment, Exercise, MuscleGroup
    from gymapp.apps.metrics.models import UserMetricSnapshot
    from gymapp.apps.nutrition.models import SavedMeal, Supplement
    from gymapp.apps.prs.models import PersonalRecord
    from gymapp.apps.routines.models import Routine, RoutineDay
    from gymapp.apps.workouts.models import ExerciseLog, SetLog, WorkoutSession, WorkoutStatus

    bob = UserFactory(email="bob.privacy@example.com")
    equipment, _ = Equipment.objects.get_or_create(slug="barbell-priv", defaults={"name": "Barbell-Priv"})
    muscle, _ = MuscleGroup.objects.get_or_create(slug="chest", defaults={"name": "Chest", "region": "chest"})
    exercise, _ = Exercise.objects.get_or_create(
        slug="bench-priv",
        defaults={"name": "BobBenchPriv", "equipment": equipment, "category": "compound"},
    )
    exercise.primary_muscles.add(muscle)

    routine = Routine.objects.create(owner=bob, name="BobSecretRoutine")
    day = RoutineDay.objects.create(routine=routine, label="BobSecretDay", ordering=0)
    session = WorkoutSession.objects.create(
        owner=bob,
        status=WorkoutStatus.FINISHED,
        started_at=timezone.now() - timedelta(hours=2),
        finished_at=timezone.now() - timedelta(hours=1),
        source_routine_day=day,
        notes="BobSecretNotes",
    )
    elog = ExerciseLog.objects.create(session=session, exercise=exercise, ordering=0)
    SetLog.objects.create(
        exercise_log=elog, ordering=0, weight_kg=137, reps=3, is_warmup=False,
        completed_at=timezone.now() - timedelta(hours=1),
    )
    PersonalRecord.objects.create(
        owner=bob, exercise=exercise, reps=3, weight_kg=137, achieved_at=timezone.now()
    )
    UserMetricSnapshot.objects.create(
        owner=bob, weight_kg=137, measured_at=timezone.now(), notes="BobSecretMeasurement",
    )
    SavedMeal.objects.create(
        owner=bob, slot="breakfast", name="BobSecretMeal", calories=500,
        protein_g=30, carbs_g=50, fat_g=15,
    )
    Supplement.objects.create(owner=bob, name="BobSecretSupp")

    # Strings whose appearance in any other user's response = a leak.
    fingerprints = [
        b"BobSecretRoutine", b"BobSecretDay", b"BobSecretNotes",
        b"BobBenchPriv", b"BobSecretMeasurement", b"BobSecretMeal", b"BobSecretSupp",
    ]
    return bob, fingerprints


def _assert_no_bob_anywhere(client, fingerprints):
    """Every read-view page returns 200 without any of bob's identifying strings."""
    pages = [
        reverse("dashboard:home"),
        reverse("dashboard:progress"),
        reverse("workouts:history"),
        reverse("routines:list"),
        reverse("routines:weekly_split"),
        reverse("metrics:list"),
        reverse("metrics:recovery"),
        reverse("prs:list"),
        reverse("nutrition:home"),
        reverse("nutrition:supplements"),
    ]
    for url in pages:
        resp = client.get(url)
        assert resp.status_code == 200, f"{url} returned {resp.status_code}"
        for fp in fingerprints:
            assert fp not in resp.content, f"{url} leaked {fp!r}"


@pytest.mark.django_db
def test_no_leak_to_other_normal_user(client):
    """A plain second user must never see bob's data on any page."""
    bob, fingerprints = _make_bob_with_workout_data()
    alice = UserFactory(email="alice.privacy@example.com")
    client.force_login(alice)
    _assert_no_bob_anywhere(client, fingerprints)


@pytest.mark.django_db
def test_no_leak_to_superuser_on_regular_pages(client):
    """Superuser must NOT see other users' data on the regular app pages —
    only /admin/ has that privilege (via OwnerScopedAdmin)."""
    bob, fingerprints = _make_bob_with_workout_data()
    superuser = UserFactory(
        email="super.privacy@example.com", is_superuser=True, is_staff=True
    )
    client.force_login(superuser)
    _assert_no_bob_anywhere(client, fingerprints)


@pytest.mark.django_db
def test_session_detail_404s_when_cross_user(client):
    """Directly hitting another user's session URL must 404, not render."""
    bob, _ = _make_bob_with_workout_data()
    from gymapp.apps.workouts.models import WorkoutSession

    bob_session = WorkoutSession.objects.get(owner=bob)
    alice = UserFactory(email="alice.session@example.com")
    client.force_login(alice)
    resp = client.get(reverse("workouts:session", args=[bob_session.id]))
    assert resp.status_code == 404


@pytest.mark.django_db
def test_pr_detail_404s_when_cross_user(client):
    """PRs are looked up via exercise slug, but the PR list inside must be
    owner-scoped — bob's PR row must not show up in alice's view."""
    bob, _ = _make_bob_with_workout_data()
    alice = UserFactory(email="alice.pr@example.com")
    client.force_login(alice)
    # bench-priv is bob's exercise (global slug); alice can hit /prs/<slug>/
    # but the PR rows must be empty for her.
    resp = client.get(reverse("prs:detail", args=["bench-priv"]))
    assert resp.status_code == 200
    assert b"BobBenchPriv" in resp.content  # exercise name from global catalogue is fine
    # But bob's specific PR (3 reps @ 137 kg) must not show.
    assert b"137" not in resp.content


@pytest.mark.django_db
def test_meal_delete_404s_when_cross_user(client):
    """POST to delete bob's meal as alice -> 404, not a silent deletion."""
    from gymapp.apps.nutrition.models import SavedMeal

    bob, _ = _make_bob_with_workout_data()
    bob_meal = SavedMeal.objects.get(owner=bob)
    alice = UserFactory(email="alice.meal@example.com")
    client.force_login(alice)
    resp = client.post(reverse("nutrition:meal_delete", args=[bob_meal.id]))
    assert resp.status_code == 404
    # And bob's meal still exists.
    assert SavedMeal.objects.filter(id=bob_meal.id).exists()


@pytest.mark.django_db
def test_supplement_take_404s_when_cross_user(client):
    """Same shape for supplements: alice can't mutate bob's supplement state."""
    from gymapp.apps.nutrition.models import Supplement

    bob, _ = _make_bob_with_workout_data()
    bob_supp = Supplement.objects.get(owner=bob)
    alice = UserFactory(email="alice.supp@example.com")
    client.force_login(alice)
    resp = client.post(reverse("nutrition:supplement_take", args=[bob_supp.id]))
    assert resp.status_code == 404


@pytest.mark.django_db
def test_routine_apply_to_week_404s_when_cross_user(client):
    """Alice can't program bob's routine onto her own week (the legacy bug
    that made another user's routine pop up in quick-fill must stay closed)."""
    bob, _ = _make_bob_with_workout_data()
    from gymapp.apps.routines.models import Routine

    bob_routine = Routine.objects.get(owner=bob, name="BobSecretRoutine")
    alice = UserFactory(email="alice.routine@example.com")
    client.force_login(alice)
    resp = client.post(reverse("routines:apply_to_week", args=[bob_routine.id]))
    assert resp.status_code == 404
