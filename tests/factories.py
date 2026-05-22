"""factory-boy factories. Grow as models land."""

from __future__ import annotations

import factory
from django.contrib.auth import get_user_model

from gymapp.apps.exercises.models import Equipment, Exercise, MuscleGroup


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = get_user_model()
        django_get_or_create = ("email",)

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    is_active = True


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
