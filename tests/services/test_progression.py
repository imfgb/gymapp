"""Tests for the progression service."""

from __future__ import annotations

from decimal import Decimal

import pytest

from gymapp.apps.routines.models import Routine, RoutineDay, RoutineExercise
from gymapp.apps.users.models import TrainingStyle
from gymapp.services import workouts as workouts_service
from gymapp.services.progression import (
    DeterministicDoubleProgression,
    DeterministicLinearProgression,
    recommend_next,
)
from tests.factories import EquipmentFactory, ExerciseFactory, UserFactory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_set(reps: int | None, weight_kg: Decimal | None = Decimal("80")):
    """Tiny stub — just needs `.reps` and `.weight_kg`."""

    class _FakeSet:
        pass

    s = _FakeSet()
    s.reps = reps
    s.weight_kg = weight_kg
    return s


# ---------------------------------------------------------------------------
# DeterministicLinearProgression unit tests
# ---------------------------------------------------------------------------


class TestLinearProgression:
    strategy = DeterministicLinearProgression()
    INCREMENT = Decimal("2.5")

    def test_no_history_returns_current_weight_and_low_reps(self):
        rec = self.strategy.recommend(
            last_sets=[],
            target_reps_low=5,
            target_reps_high=5,
            current_weight=Decimal("100"),
            weight_increment_kg=self.INCREMENT,
        )
        assert rec.weight_kg == Decimal("100")
        assert rec.reps == 5
        assert rec.rationale == "no_history"

    def test_all_sets_hit_increases_weight(self):
        last = [_make_fake_set(5, Decimal("100"))] * 5
        rec = self.strategy.recommend(
            last_sets=last,
            target_reps_low=5,
            target_reps_high=5,
            current_weight=Decimal("100"),
            weight_increment_kg=self.INCREMENT,
        )
        assert rec.weight_kg == Decimal("102.5")
        assert rec.reps == 5
        assert rec.rationale == "linear_increase"

    def test_one_set_missed_repeats_weight(self):
        last = [_make_fake_set(5), _make_fake_set(4), _make_fake_set(5)]
        rec = self.strategy.recommend(
            last_sets=last,
            target_reps_low=5,
            target_reps_high=5,
            current_weight=Decimal("80"),
            weight_increment_kg=self.INCREMENT,
        )
        assert rec.weight_kg == Decimal("80")
        assert rec.rationale == "repeat_weight"

    def test_sets_with_none_reps_treated_as_missed(self):
        last = [_make_fake_set(None), _make_fake_set(5)]
        rec = self.strategy.recommend(
            last_sets=last,
            target_reps_low=5,
            target_reps_high=5,
            current_weight=Decimal("80"),
            weight_increment_kg=self.INCREMENT,
        )
        assert rec.rationale == "repeat_weight"


# ---------------------------------------------------------------------------
# DeterministicDoubleProgression unit tests
# ---------------------------------------------------------------------------


class TestDoubleProgression:
    strategy = DeterministicDoubleProgression()
    INCREMENT = Decimal("2.5")

    def test_no_history_returns_current_weight_and_low_reps(self):
        rec = self.strategy.recommend(
            last_sets=[],
            target_reps_low=8,
            target_reps_high=12,
            current_weight=Decimal("60"),
            weight_increment_kg=self.INCREMENT,
        )
        assert rec.weight_kg == Decimal("60")
        assert rec.reps == 8
        assert rec.rationale == "no_history"

    def test_all_sets_hit_top_increases_weight_and_resets_reps(self):
        last = [_make_fake_set(12, Decimal("60"))] * 3
        rec = self.strategy.recommend(
            last_sets=last,
            target_reps_low=8,
            target_reps_high=12,
            current_weight=Decimal("60"),
            weight_increment_kg=self.INCREMENT,
        )
        assert rec.weight_kg == Decimal("62.5")
        assert rec.reps == 8
        assert rec.rationale == "double_progression_increase"

    def test_sets_below_top_stay_at_same_weight(self):
        last = [_make_fake_set(10, Decimal("60"))] * 3
        rec = self.strategy.recommend(
            last_sets=last,
            target_reps_low=8,
            target_reps_high=12,
            current_weight=Decimal("60"),
            weight_increment_kg=self.INCREMENT,
        )
        assert rec.weight_kg == Decimal("60")
        assert rec.reps == 10  # average of last session
        assert rec.rationale == "repeat_build_reps"

    def test_rep_recommendation_clamped_to_range(self):
        # Last session averaged 14 reps — should be clamped to target_reps_high
        last = [_make_fake_set(14, Decimal("60"))]
        rec = self.strategy.recommend(
            last_sets=last,
            target_reps_low=8,
            target_reps_high=12,
            current_weight=Decimal("60"),
            weight_increment_kg=self.INCREMENT,
        )
        # 14 >= 12 → all hit top → increase weight
        assert rec.rationale == "double_progression_increase"

    def test_rep_recommendation_clamped_below_range_floor(self):
        # Last session averaged 6 reps — should be clamped to target_reps_low
        last = [_make_fake_set(6, Decimal("60"))]
        rec = self.strategy.recommend(
            last_sets=last,
            target_reps_low=8,
            target_reps_high=12,
            current_weight=Decimal("60"),
            weight_increment_kg=self.INCREMENT,
        )
        assert rec.reps == 8  # clamped up to low
        assert rec.rationale == "repeat_build_reps"


# ---------------------------------------------------------------------------
# recommend_next integration (hits real DB)
# ---------------------------------------------------------------------------


@pytest.fixture
def user_powerlifting(db):
    u = UserFactory(email="plift@example.com")
    u.profile.training_style = TrainingStyle.POWERLIFTING
    u.profile.save()
    return u


@pytest.fixture
def user_bodybuilding(db):
    u = UserFactory(email="bb@example.com")
    u.profile.training_style = TrainingStyle.BODYBUILDING
    u.profile.save()
    return u


@pytest.fixture
def barbell(db):
    return ExerciseFactory(
        slug="barbell-squat",
        equipment=EquipmentFactory(slug="barbell"),
        category="compound",
    )


@pytest.mark.django_db
def test_recommend_next_no_history_returns_prescribed(user_powerlifting, barbell):
    rec = recommend_next(
        user=user_powerlifting,
        exercise=barbell,
        target_reps_low=5,
        target_reps_high=5,
        current_weight=Decimal("120"),
    )
    assert rec.weight_kg == Decimal("120")
    assert rec.reps == 5
    assert rec.rationale == "no_history"


@pytest.mark.django_db
def test_recommend_next_linear_increases_after_successful_session(user_powerlifting, barbell):
    from gymapp.apps.routines.models import Routine, RoutineDay, RoutineExercise

    # Build a completed session where all 5 sets were hit at 5 reps × 120 kg
    routine = Routine.objects.create(owner=user_powerlifting, name="SQ")
    day = RoutineDay.objects.create(routine=routine, label="Squat Day")
    RoutineExercise.objects.create(
        routine_day=day,
        exercise=barbell,
        target_sets=5,
        target_reps_low=5,
        target_reps_high=5,
        target_weight_kg=Decimal("120"),
    )

    session = workouts_service.start_session(user_powerlifting, routine_day=day)
    for s in session.exercise_logs.first().set_logs.all():
        workouts_service.complete_set(s, weight_kg=Decimal("120"), reps=5)
    workouts_service.finish_session(session)

    rec = recommend_next(
        user=user_powerlifting,
        exercise=barbell,
        target_reps_low=5,
        target_reps_high=5,
        current_weight=Decimal("120"),
    )
    assert rec.weight_kg == Decimal("125")  # +5 kg (powerlifting compound increment)
    assert rec.rationale == "linear_increase"


@pytest.mark.django_db
def test_recommend_next_double_progression_increases_after_hitting_top(user_bodybuilding, barbell):
    from gymapp.apps.routines.models import Routine, RoutineDay, RoutineExercise

    routine = Routine.objects.create(owner=user_bodybuilding, name="BB")
    day = RoutineDay.objects.create(routine=routine, label="Push")
    RoutineExercise.objects.create(
        routine_day=day,
        exercise=barbell,
        target_sets=3,
        target_reps_low=8,
        target_reps_high=12,
        target_weight_kg=Decimal("80"),
    )

    session = workouts_service.start_session(user_bodybuilding, routine_day=day)
    for s in session.exercise_logs.first().set_logs.all():
        workouts_service.complete_set(s, weight_kg=Decimal("80"), reps=12)
    workouts_service.finish_session(session)

    rec = recommend_next(
        user=user_bodybuilding,
        exercise=barbell,
        target_reps_low=8,
        target_reps_high=12,
        current_weight=Decimal("80"),
    )
    assert rec.weight_kg == Decimal("82.5")  # +2.5 kg (bodybuilding compound)
    assert rec.reps == 8
    assert rec.rationale == "double_progression_increase"


@pytest.mark.django_db
def test_recommend_next_double_progression_repeats_when_below_top(user_bodybuilding, barbell):
    from gymapp.apps.routines.models import Routine, RoutineDay, RoutineExercise

    routine = Routine.objects.create(owner=user_bodybuilding, name="BB2")
    day = RoutineDay.objects.create(routine=routine, label="Push")
    RoutineExercise.objects.create(
        routine_day=day,
        exercise=barbell,
        target_sets=3,
        target_reps_low=8,
        target_reps_high=12,
        target_weight_kg=Decimal("80"),
    )

    session = workouts_service.start_session(user_bodybuilding, routine_day=day)
    for s in session.exercise_logs.first().set_logs.all():
        workouts_service.complete_set(s, weight_kg=Decimal("80"), reps=10)
    workouts_service.finish_session(session)

    rec = recommend_next(
        user=user_bodybuilding,
        exercise=barbell,
        target_reps_low=8,
        target_reps_high=12,
        current_weight=Decimal("80"),
    )
    assert rec.weight_kg == Decimal("80")  # no increase
    assert rec.reps == 10
    assert rec.rationale == "repeat_build_reps"


@pytest.mark.django_db
def test_start_session_prefills_sets_from_progression(user_powerlifting, barbell):
    """Integration: starting a second session pre-fills weights from the
    progression recommendation, not the routine's prescribed target."""
    routine = Routine.objects.create(owner=user_powerlifting, name="S")
    day = RoutineDay.objects.create(routine=routine, label="Squat")
    RoutineExercise.objects.create(
        routine_day=day,
        exercise=barbell,
        target_sets=3,
        target_reps_low=5,
        target_reps_high=5,
        target_weight_kg=Decimal("100"),
    )

    # Session 1 — complete all working sets successfully
    s1 = workouts_service.start_session(user_powerlifting, routine_day=day)
    for s in s1.exercise_logs.first().set_logs.filter(is_warmup=False):
        workouts_service.complete_set(s, weight_kg=Decimal("100"), reps=5)
    workouts_service.finish_session(s1)

    # Session 2 — working sets should be pre-filled at 105 kg (100 + 5 increment)
    s2 = workouts_service.start_session(user_powerlifting, routine_day=day)
    sets = list(s2.exercise_logs.first().set_logs.filter(is_warmup=False).order_by("ordering"))
    assert all(s.weight_kg == Decimal("105") for s in sets)
    assert all(s.reps == 5 for s in sets)
