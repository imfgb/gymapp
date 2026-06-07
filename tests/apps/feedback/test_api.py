"""Token-authenticated JSON API for bug triage (admin automation).

The API lets the orchestrator/executor skills read open bugs and update status
over HTTPS against production, gated by a single bearer token (`FEEDBACK_API_TOKEN`).
"""

from __future__ import annotations

import json

import pytest
from django.urls import reverse

from gymapp.apps.feedback.models import BugReport, BugStatus
from tests.factories import UserFactory

TOKEN = "test-token-abc123"  # noqa: S105 — test fixture, not a real secret


@pytest.fixture
def reporter(db):
    return UserFactory(email="reporter.api@example.com")


@pytest.fixture
def bugs(reporter):
    open1 = BugReport.objects.create(
        reporter=reporter, subject="Bug abierto 1", description="algo falla"
    )
    open2 = BugReport.objects.create(
        reporter=reporter, subject="Bug abierto 2", description="otra cosa"
    )
    BugReport.objects.create(
        reporter=reporter,
        subject="Ya resuelto",
        description="cerrado",
        status=BugStatus.RESOLVED,
    )
    return {"open1": open1, "open2": open2}


def auth(token=TOKEN):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


# ---------------- GET list: auth gating ----------------


@pytest.mark.django_db
def test_list_returns_503_when_token_not_configured(client, settings, bugs):
    settings.FEEDBACK_API_TOKEN = ""
    resp = client.get(reverse("feedback:api_bugs"), **auth())
    assert resp.status_code == 503


@pytest.mark.django_db
def test_list_rejects_missing_token(client, settings, bugs):
    settings.FEEDBACK_API_TOKEN = TOKEN
    resp = client.get(reverse("feedback:api_bugs"))
    assert resp.status_code == 401


@pytest.mark.django_db
def test_list_rejects_wrong_token(client, settings, bugs):
    settings.FEEDBACK_API_TOKEN = TOKEN
    resp = client.get(reverse("feedback:api_bugs"), **auth("nope"))
    assert resp.status_code == 401


@pytest.mark.django_db
def test_list_rejects_non_bearer_header(client, settings, bugs):
    settings.FEEDBACK_API_TOKEN = TOKEN
    resp = client.get(
        reverse("feedback:api_bugs"), HTTP_AUTHORIZATION=f"Token {TOKEN}"
    )
    assert resp.status_code == 401


# ---------------- GET list: behaviour ----------------


@pytest.mark.django_db
def test_list_open_bugs_with_valid_token(client, settings, bugs):
    settings.FEEDBACK_API_TOKEN = TOKEN
    resp = client.get(
        reverse("feedback:api_bugs"), {"status": "open"}, **auth()
    )
    assert resp.status_code == 200
    data = json.loads(resp.content)
    subjects = {b["subject"] for b in data["bugs"]}
    assert subjects == {"Bug abierto 1", "Bug abierto 2"}
    # shape
    one = data["bugs"][0]
    for key in (
        "id",
        "subject",
        "description",
        "page_area",
        "page_url",
        "reporter_email",
        "status",
        "created_at",
    ):
        assert key in one
    assert one["reporter_email"] == "reporter.api@example.com"


@pytest.mark.django_db
def test_list_without_filter_returns_all(client, settings, bugs):
    settings.FEEDBACK_API_TOKEN = TOKEN
    resp = client.get(reverse("feedback:api_bugs"), **auth())
    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert len(data["bugs"]) == 3  # 2 open + 1 resolved


@pytest.mark.django_db
def test_list_rejects_invalid_status_filter(client, settings, bugs):
    settings.FEEDBACK_API_TOKEN = TOKEN
    resp = client.get(reverse("feedback:api_bugs"), {"status": "bogus"}, **auth())
    assert resp.status_code == 400


# ---------------- POST status ----------------


@pytest.mark.django_db
def test_post_updates_status(client, settings, bugs):
    settings.FEEDBACK_API_TOKEN = TOKEN
    bug = bugs["open1"]
    resp = client.post(
        reverse("feedback:api_bug_status", args=[bug.pk]),
        data=json.dumps({"status": "triaged"}),
        content_type="application/json",
        **auth(),
    )
    assert resp.status_code == 200
    bug.refresh_from_db()
    assert bug.status == BugStatus.TRIAGED
    assert json.loads(resp.content)["bug"]["status"] == "triaged"


@pytest.mark.django_db
def test_post_rejects_invalid_status(client, settings, bugs):
    settings.FEEDBACK_API_TOKEN = TOKEN
    bug = bugs["open1"]
    resp = client.post(
        reverse("feedback:api_bug_status", args=[bug.pk]),
        data=json.dumps({"status": "wat"}),
        content_type="application/json",
        **auth(),
    )
    assert resp.status_code == 400
    bug.refresh_from_db()
    assert bug.status == BugStatus.OPEN  # unchanged


@pytest.mark.django_db
def test_post_requires_token(client, settings, bugs):
    settings.FEEDBACK_API_TOKEN = TOKEN
    resp = client.post(
        reverse("feedback:api_bug_status", args=[bugs["open1"].pk]),
        data=json.dumps({"status": "triaged"}),
        content_type="application/json",
    )
    assert resp.status_code == 401


@pytest.mark.django_db
def test_post_404_for_unknown_id(client, settings, bugs):
    settings.FEEDBACK_API_TOKEN = TOKEN
    resp = client.post(
        reverse("feedback:api_bug_status", args=[999999]),
        data=json.dumps({"status": "triaged"}),
        content_type="application/json",
        **auth(),
    )
    assert resp.status_code == 404
