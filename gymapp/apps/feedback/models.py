"""User-submitted bug reports.

Any authenticated user can submit one via the floating button in `base.html`.
Only superusers can read them on `/feedback/admin/`. The PII risk here is
small (subject + description text + page URL + user-agent string) but enough
to justify keeping it gated.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from gymapp.apps.core.models import TimestampedModel


class BugStatus(models.TextChoices):
    OPEN = "open", "Abierto"
    TRIAGED = "triaged", "En revisión"
    RESOLVED = "resolved", "Resuelto"


class BugReport(TimestampedModel):
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="bug_reports",
    )
    subject = models.CharField(max_length=200)
    page_area = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Optional — which part of the app, in the reporter's words.",
    )
    description = models.TextField(max_length=2000)
    page_url = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="URL the user was on when they clicked the bug button.",
    )
    user_agent = models.CharField(max_length=300, blank=True, default="")
    status = models.CharField(
        max_length=10, choices=BugStatus.choices, default=BugStatus.OPEN, db_index=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        who = self.reporter.email if self.reporter else "(deleted user)"
        return f"#{self.pk} {self.subject[:60]} — {who}"
