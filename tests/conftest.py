"""Pytest fixtures shared across the suite."""

from __future__ import annotations

import pytest


@pytest.fixture
def user(db, django_user_model):
    return django_user_model.objects.create_user(
        email="alice@example.com",
        password="not-secret-for-tests",
    )


@pytest.fixture
def other_user(db, django_user_model):
    return django_user_model.objects.create_user(
        email="bob@example.com",
        password="not-secret-for-tests",
    )


@pytest.fixture
def clean_catalog(db):
    """Wipe the seeded exercise catalogue so a test controls it exactly."""
    from gymapp.apps.exercises.models import (
        Equipment,
        Exercise,
        ExerciseAlternative,
        MuscleGroup,
    )

    ExerciseAlternative.objects.all().delete()
    Exercise.objects.all().delete()
    MuscleGroup.objects.all().delete()
    Equipment.objects.all().delete()
