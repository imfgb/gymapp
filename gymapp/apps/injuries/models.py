"""Injury log + per-injury list of exercises to avoid.

The rehab service (`gymapp.services.rehab`) reads only ACTIVE injuries (those
without `resolved_on`) to decide which exercises to warn about. Resolved
entries stay around as history.
"""

from __future__ import annotations

from django.db import models

from gymapp.apps.core.models import OwnedMixin, OwnerScopedQuerySet, TimestampedModel


class BodyRegion(models.TextChoices):
    SHOULDER = "shoulder", "Hombro"
    ELBOW = "elbow", "Codo"
    WRIST = "wrist", "Muñeca"
    NECK = "neck", "Cuello"
    UPPER_BACK = "upper_back", "Espalda alta"
    LOWER_BACK = "lower_back", "Espalda baja / lumbar"
    HIP = "hip", "Cadera"
    KNEE = "knee", "Rodilla"
    ANKLE = "ankle", "Tobillo"
    CHEST = "chest", "Pecho"
    OTHER = "other", "Otra"


class Severity(models.TextChoices):
    MILD = "mild", "Leve"
    MODERATE = "moderate", "Moderada"
    SEVERE = "severe", "Severa"


class Injury(OwnedMixin, TimestampedModel):
    """One row per logged injury / restriction. Active while `resolved_on` is null."""

    name = models.CharField(max_length=120, help_text="p.ej. Lumbalgia, Impingement hombro derecho.")
    body_region = models.CharField(
        max_length=20, choices=BodyRegion.choices, default=BodyRegion.OTHER
    )
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.MILD)
    started_on = models.DateField(db_index=True)
    resolved_on = models.DateField(null=True, blank=True, db_index=True)
    notes = models.TextField(blank=True, default="")
    avoid_exercises = models.ManyToManyField(
        "exercises.Exercise",
        blank=True,
        related_name="avoided_by_injuries",
        help_text=(
            "Ejercicios que NO se deben hacer mientras la lesión esté activa. "
            "La sesión y los pickers mostrarán una advertencia."
        ),
    )

    objects = OwnerScopedQuerySet.as_manager()

    class Meta:
        ordering = ["-started_on", "name"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(resolved_on__isnull=True)
                    | models.Q(resolved_on__gte=models.F("started_on"))
                ),
                name="injury_resolved_after_started",
            )
        ]

    def __str__(self) -> str:
        marker = " (activa)" if self.is_active else ""
        return f"{self.name}{marker}"

    @property
    def is_active(self) -> bool:
        return self.resolved_on is None
