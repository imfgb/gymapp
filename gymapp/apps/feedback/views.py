"""Feedback / bug-report views.

`report` accepts a POST from any authenticated user and creates a `BugReport`.
`admin_list` and `admin_action` are gated to superusers — they're the only ones
who can see what users submitted, change status, or delete reports.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .models import BugReport, BugStatus


def _is_superuser(u) -> bool:
    return u.is_authenticated and u.is_superuser


superuser_required = user_passes_test(_is_superuser)


@login_required
@require_POST
def report(request: HttpRequest) -> HttpResponse:
    """Anyone logged in can submit a bug. Redirects back to where they were."""
    subject = (request.POST.get("subject") or "").strip()
    description = (request.POST.get("description") or "").strip()
    if not subject or not description:
        return HttpResponseBadRequest("subject and description required")

    BugReport.objects.create(
        reporter=request.user,
        subject=subject[:200],
        page_area=(request.POST.get("page_area") or "").strip()[:120],
        description=description[:2000],
        page_url=(request.POST.get("page_url") or request.META.get("HTTP_REFERER") or "")[:500],
        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:300],
    )
    # `toast` is rendered bottom-right by base.html — distinct from the top
    # flash messages used elsewhere.
    messages.success(request, "Bug reportado exitosamente!", extra_tags="toast")
    return redirect(request.META.get("HTTP_REFERER") or "dashboard:home")


@login_required
@superuser_required
@require_GET
def admin_list(request: HttpRequest) -> HttpResponse:
    """Superuser-only view of every report, newest first."""
    qs = (
        BugReport.objects.select_related("reporter").order_by("-created_at")
    )
    status_filter = request.GET.get("status")
    if status_filter in BugStatus.values:
        qs = qs.filter(status=status_filter)
    return render(
        request,
        "feedback/admin_list.html",
        {
            "reports": qs,
            "status_choices": BugStatus.choices,
            "status_filter": status_filter or "",
            "counts": {
                "open": BugReport.objects.filter(status=BugStatus.OPEN).count(),
                "triaged": BugReport.objects.filter(status=BugStatus.TRIAGED).count(),
                "resolved": BugReport.objects.filter(status=BugStatus.RESOLVED).count(),
            },
        },
    )


@login_required
@superuser_required
@require_POST
def admin_status(request: HttpRequest, report_id: int) -> HttpResponse:
    report = get_object_or_404(BugReport, pk=report_id)
    new_status = request.POST.get("status", "")
    if new_status not in BugStatus.values:
        return HttpResponseBadRequest("invalid status")
    report.status = new_status
    report.save(update_fields=["status", "updated_at"])
    return redirect("feedback:admin")


@login_required
@superuser_required
@require_POST
def admin_delete(request: HttpRequest, report_id: int) -> HttpResponse:
    get_object_or_404(BugReport, pk=report_id).delete()
    return redirect("feedback:admin")
