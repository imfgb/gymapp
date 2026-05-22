"""Smoke tests — confirm settings load, the User factory works, and the
deterministic services return their expected stub shapes.

These exist so the CI pipeline has something green to run before Phase 1 lands.
"""

from __future__ import annotations

import pytest


def test_settings_load():
    from django.conf import settings

    assert settings.AUTH_USER_MODEL == "users.User"
    assert settings.LANGUAGE_CODE == "es-mx"
    assert settings.TIME_ZONE == "America/Mexico_City"


@pytest.mark.django_db
def test_user_factory_creates_user_with_profile():
    from gymapp.apps.users.models import Profile

    from .factories import UserFactory

    user = UserFactory()
    assert user.pk is not None
    assert Profile.objects.filter(user=user).exists()


def test_progression_service_no_history_returns_stub():
    from decimal import Decimal

    from gymapp.services.progression import DeterministicDoubleProgression

    strategy = DeterministicDoubleProgression()
    rec = strategy.recommend(
        last_sets=[],
        target_reps_low=8,
        target_reps_high=12,
        current_weight=Decimal("100"),
        weight_increment_kg=Decimal("2.5"),
    )
    assert rec.weight_kg == Decimal("100")
    assert rec.reps == 8
    assert rec.rationale == "no_history"


@pytest.mark.django_db
def test_substitution_service_returns_empty_without_seed():
    """Without any seeded exercises, substitution falls through to an empty
    list. Real behaviour is covered in tests/services/test_exercise_library.py.
    """
    from gymapp.services.coaching import substitution

    assert substitution.alternatives_for("does-not-exist", ["dumbbell"]) == []
