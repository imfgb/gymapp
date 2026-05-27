"""factory-boy factories. Grow as models land."""

from __future__ import annotations

import factory
from django.contrib.auth import get_user_model

from gymapp.apps.exercises.models import Equipment, Exercise, MuscleGroup


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = get_user_model()
        django_get_or_create = ("email",)
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    is_active = True

    @factory.post_generation
    def _onboard(obj, create, extracted, **kwargs):
        """Mark the test user as already-onboarded so OnboardingMiddleware
        doesn't redirect every request. Pass `_onboard=False` to opt out
        (e.g. onboarding-flow tests that need a fresh profile)."""
        if not create:
            return
        if extracted is False:
            obj.profile.height_cm = None
            obj.profile.sex = ""
            obj.profile.date_of_birth = None
            obj.profile.onboarded_at = None
            obj.profile.save()
            return
        from datetime import date
        from django.utils import timezone

        prof = obj.profile
        if not prof.height_cm:
            prof.height_cm = 175
        if not prof.sex:
            prof.sex = "male"
        if not prof.date_of_birth:
            prof.date_of_birth = date(1990, 1, 1)
        prof.onboarded_at = timezone.now()
        prof.save()


class MuscleGroupFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MuscleGroup
        django_get_or_create = ("slug",)

    slug = factory.Sequence(lambda n: f"muscle-{n}")
    name = factory.LazyAttribute(lambda o: o.slug.replace("-", " ").title())
    region = "chest"


class EquipmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Equipment
        django_get_or_create = ("slug",)

    slug = factory.Sequence(lambda n: f"equipment-{n}")
    name = factory.LazyAttribute(lambda o: o.slug.replace("-", " ").title())


class ExerciseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Exercise
        django_get_or_create = ("slug", "owner")

    slug = factory.Sequence(lambda n: f"exercise-{n}")
    name = factory.LazyAttribute(lambda o: o.slug.replace("-", " ").title())
    equipment = factory.SubFactory(EquipmentFactory)
    owner = None
    category = "compound"
    unilateral = False
    is_active = True
