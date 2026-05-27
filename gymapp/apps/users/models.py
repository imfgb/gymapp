"""User & Profile.

Email is the unique identifier (the brief says invite-only via /admin and no
public signup, so email-as-username is the natural fit). A `Profile` is
auto-created on `User` save via a post_save signal (see `signals.py`).

Training-style and training-goal choices live here rather than in `routines`
because they describe the user, not a particular plan.
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager


class TrainingStyle(models.TextChoices):
    BODYBUILDING = "bodybuilding", "Bodybuilding"
    POWERLIFTING = "powerlifting", "Powerlifting"
    POWERBUILDING = "powerbuilding", "Powerbuilding"


class TrainingGoal(models.TextChoices):
    HYPERTROPHY = "hypertrophy", "Hypertrophy"
    STRENGTH = "strength", "Strength"
    RECOMPOSITION = "recomposition", "Recomposition"
    CUT = "cut", "Cut"
    BULK = "bulk", "Bulk"
    MAINTAIN = "maintain", "Maintain"


class Sex(models.TextChoices):
    MALE = "male", "Male"
    FEMALE = "female", "Female"


class ActivityLevel(models.TextChoices):
    """Mapped to a TDEE multiplier in `gymapp.services.nutrition`."""

    SEDENTARY = "sedentary", "Sedentary"
    LIGHT = "light", "Lightly active"
    MODERATE = "moderate", "Moderately active"
    ACTIVE = "active", "Active"
    VERY_ACTIVE = "very_active", "Very active"


class User(AbstractUser):
    """Custom user: email as username, no first/last name required."""

    username = None
    email = models.EmailField("email address", unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self) -> str:
        return self.email


class Profile(models.Model):
    """Per-user training & body baseline. Body composition snapshots live in
    `metrics.UserMetricSnapshot`; this model holds the time-invariant values
    (height, DOB) and the user's coaching preferences."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")

    # Baseline body data — height & date_of_birth don't really change.
    height_cm = models.PositiveSmallIntegerField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=6, choices=Sex.choices, blank=True, default="")
    activity_level = models.CharField(
        max_length=12,
        choices=ActivityLevel.choices,
        default=ActivityLevel.MODERATE,
    )
    # Liked-food slugs from gymapp.services.nutrition.FOOD_CATALOG. Drives the
    # meal-slot scaffolding (Phase 3 meal-slots).
    food_preferences = models.JSONField(default=list, blank=True)

    # Coaching prefs
    training_style = models.CharField(
        max_length=20,
        choices=TrainingStyle.choices,
        default=TrainingStyle.POWERBUILDING,
    )
    training_goal = models.CharField(
        max_length=20,
        choices=TrainingGoal.choices,
        default=TrainingGoal.HYPERTROPHY,
    )
    default_rest_seconds = models.PositiveSmallIntegerField(default=120)

    # When True, the next login forces a password change. Set on admin-created accounts.
    must_change_password = models.BooleanField(default=False)

    # Set the first time the user completes (or explicitly skips) onboarding.
    # The middleware only redirects to /onboarding/ while this is null, so
    # later editing your profile to null out a field doesn't re-trigger it.
    onboarded_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Profile"
        verbose_name_plural = "Profiles"

    def __str__(self) -> str:
        return f"Profile<{self.user.email}>"

    @property
    def is_onboarded(self) -> bool:
        """Sticky flag — once the user has finished (or skipped) onboarding
        we never redirect them there again, even if they later clear fields."""
        return self.onboarded_at is not None
