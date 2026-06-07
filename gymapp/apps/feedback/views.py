"""Feedback / bug-report views.

`report` accepts a POST from any authenticated user and creates a `BugReport`.
`admin_list` / `admin_status` / `admin_delete` are gated to superusers — they're
the only ones who can see what users submitted, change status, or delete reports.

The `api_*` views are a token-authenticated JSON API (bearer `FEEDBACK_API_TOKEN`)
used by the admin's triage-automation skills to read open bugs and update status
over HTTPS against production. See `DECISIONS.md` for the csrf-exempt ADR.
"""

from __future__ import annotations

import hmac
import json
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
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


# ---------------------------------------------------------------------------
# Token-authenticated JSON API (admin triage automation)
# ---------------------------------------------------------------------------


def _bug_to_dict(b: BugReport) -> dict:
    return {
        "id": b.pk,
        "subject": b.subject,
        "description": b.description,
        "page_area": b.page_area,
        "page_url": b.page_url,
        "reporter_email": b.reporter.email if b.reporter else None,
        "status": b.status,
        "created_at": b.created_at.isoformat(),
    }


def _api_token_required(view):
    """Gate a view behind the `FEEDBACK_API_TOKEN` bearer token.

    503 when no token is configured (so an empty env var can never become an
    open door); 401 on a missing or wrong token. Constant-time comparison.
    """

    @wraps(view)
    def wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        configured = getattr(settings, "FEEDBACK_API_TOKEN", "") or ""
        if not configured:
            return JsonResponse({"detail": "API token not configured"}, status=503)
        header = request.META.get("HTTP_AUTHORIZATION", "")
        prefix = "Bearer "
        if not header.startswith(prefix):
            return JsonResponse({"detail": "missing bearer token"}, status=401)
        provided = header[len(prefix) :]
        if not hmac.compare_digest(provided, configured):
            return JsonResponse({"detail": "invalid token"}, status=401)
        return view(request, *args, **kwargs)

    return wrapped


@csrf_exempt
@_api_token_required
@require_GET
def api_bugs(request: HttpRequest) -> HttpResponse:
    """List bug reports as JSON. Optional `?status=` filter (validated)."""
    qs = BugReport.objects.select_related("reporter").order_by("created_at")
    status_filter = request.GET.get("status")
    if status_filter:
        if status_filter not in BugStatus.values:
            return JsonResponse({"detail": "invalid status"}, status=400)
        qs = qs.filter(status=status_filter)
    return JsonResponse({"bugs": [_bug_to_dict(b) for b in qs]})


@csrf_exempt
@_api_token_required
@require_POST
def api_bug_status(request: HttpRequest, report_id: int) -> HttpResponse:
    """Update a report's status from a JSON body `{"status": ...}`."""
    report = get_object_or_404(BugReport, pk=report_id)
    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "invalid JSON"}, status=400)
    new_status = payload.get("status", "")
    if new_status not in BugStatus.values:
        return JsonResponse({"detail": "invalid status"}, status=400)
    report.status = new_status
    report.save(update_fields=["status", "updated_at"])
    return JsonResponse({"bug": _bug_to_dict(report)})
