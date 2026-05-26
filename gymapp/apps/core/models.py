"""Shared model primitives.

`TimestampedModel` and `OwnedMixin` are abstract — concrete apps subclass them.
`OwnerScopedQuerySet` is the canonical way to filter user-owned data; views
*must* call `.for_user(request.user)`. A missing scope call is a security bug
(see plan §9 Security & Privacy).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class TimestampedModel(models.Model):
    """Adds `created_at` / `updated_at` to any model that inherits it."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class OwnerScopedQuerySet(models.QuerySet):
    """Returns only rows owned by the given user — always, including superusers.

    `/admin` uses `OwnerScopedAdmin` directly (which has its own superuser-sees-all
    short-circuit), so a superuser who wants to inspect another user's data goes
    there. Outside `/admin`, every user — superuser included — sees only their
    own rows. A previous superuser bypass here leaked other users' routines,
    metrics, PRs etc. into the superuser's personal dashboard.
    """

    def for_user(self, user) -> OwnerScopedQuerySet:
        if user is None or not user.is_authenticated:
            return self.none()
        return self.filter(owner=user)


class OwnedMixin(models.Model):
    """Adds an `owner` FK to the project's User model.

    Concrete models override `objects` if they need a different manager but
    `OwnerScopedQuerySet.as_manager()` is the default.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    objects = OwnerScopedQuerySet.as_manager()

    class Meta:
        abstract = True
