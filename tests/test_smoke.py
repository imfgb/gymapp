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


def test_progression_service_repeats_last_history():
    from gymapp.services.coaching import SetRecommendation, progression

    rec = progression.recommend_next(
        "bench-press",
        history=[SetRecommendation(weight_kg=100.0, reps=5)],
    )
    assert rec.weight_kg == 100.0
    assert rec.reps == 5
    assert rec.rationale == "repeat_last"


def test_substitution_service_returns_empty_in_phase_0():
    from gymapp.services.coaching import substitution

    assert substitution.alternatives_for("bench-press", ["dumbbell"]) == []
