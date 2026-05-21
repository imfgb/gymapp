"""Exercises catalogue.

`MuscleGroup` and `Equipment` are global lookup tables, seeded from
`seeds/exercises.yaml`. `Exercise` is either global (`owner = NULL`, visible to
all users) or per-user (custom exercise the user created). The
`ExerciseAlternative` through-model links exercises that target the same
primary muscle with different equipment — used by the substitution service.

The owner-scoping convention here is slightly looser than `OwnedMixin`: global
exercises must be visible to every user, so we expose
`Exercise.objects.visible_to(user)` instead of plain `.for_user(user)`.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from gymapp.apps.core.models import TimestampedModel


class MuscleRegion(models.TextChoices):
    CHEST = "chest", "Chest"
    BACK = "back", "Back"
    SHOULDERS = "shoulders", "Shoulders"
    ARMS = "arms", "Arms"
    LEGS = "legs", "Legs"
    CORE = "core", "Core"


class ExerciseCategory(models.TextChoices):
    COMPOUND = "compound", "Compound"
    ISOLATION = "isolation", "Isolation"


class MuscleGroup(models.Model):
    slug = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    region = models.CharField(max_length=20, choices=MuscleRegion.choices)

    class Meta:
        ordering = ["region", "name"]

    def __str__(self) -> str:
        return self.name


class Equipment(models.Model):
    slug = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=80)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Equipment"

    def __str__(self) -> str:
        return self.name


class ExerciseQuerySet(models.QuerySet):
    def visible_to(self, user) -> "ExerciseQuerySet":
        """Global rows (owner IS NULL) plus the requesting user's own rows.

        Anonymous users see globals only. Superusers see everything (no extra
        filter — superuser-only admin paths use `.all()` directly).
        """
        if user is None or not user.is_authenticated:
            return self.filter(owner__isnull=True, is_active=True)
        if user.is_superuser:
            return self.all()
        return self.filter(models.Q(owner__isnull=True) | models.Q(owner=user)).filter(
            is_active=True
        )

    def for_user(self, user) -> "ExerciseQuerySet":
        """Only the user's own (custom) exercises. Used by edit/delete views."""
        if user is None or not user.is_authenticated:
            return self.none()
        if user.is_superuser:
            return self.all()
        return self.filter(owner=user)


class Exercise(TimestampedModel):
    slug = models.SlugField(max_length=80)
    name = models.CharField(max_length=120)
    equipment = models.ForeignKey(
        Equipment, on_delete=models.PROTECT, related_name="exercises", db_index=True
    )
    primary_muscles = models.ManyToManyField(MuscleGroup, related_name="primary_for")
    secondary_muscles = models.ManyToManyField(
        MuscleGroup, related_name="secondary_for", blank=True
    )
    category = models.CharField(
        max_length=12, choices=ExerciseCategory.choices, default=ExerciseCategory.COMPOUND
    )
    unilateral = models.BooleanField(default=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="custom_exercises",
        null=True,
        blank=True,
        help_text="NULL = global (seeded). Otherwise the user who created this custom exercise.",
    )
    is_active = models.BooleanField(default=True)
    alternatives = models.ManyToManyField(
        "self",
        through="ExerciseAlternative",
        through_fields=("from_exercise", "to_exercise"),
        symmetrical=False,
        related_name="alternates_of",
        blank=True,
    )

    objects = ExerciseQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "slug"],
                name="exercises_unique_slug_per_owner",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_global(self) -> bool:
        return self.owner_id is None


class ExerciseAlternative(models.Model):
    """Directional: A -> B doesn't imply B -> A. The seed loader writes both
    directions when the YAML defines a pair to be reciprocal."""

    from_exercise = models.ForeignKey(
        Exercise, on_delete=models.CASCADE, related_name="alternative_links_from"
    )
    to_exercise = models.ForeignKey(
        Exercise, on_delete=models.CASCADE, related_name="alternative_links_to"
    )
    reason = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["from_exercise", "to_exercise"],
                name="exercises_unique_alternative_pair",
            ),
            models.CheckConstraint(
                condition=~models.Q(from_exercise=models.F("to_exercise")),
                name="exercises_alternative_not_self",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.from_exercise.slug} -> {self.to_exercise.slug}"
