"""Feedback / bug-report tests: per-user reporting + superuser-only admin."""

from __future__ import annotations

import pytest
from django.urls import reverse

from gymapp.apps.feedback.models import BugReport, BugStatus
from tests.factories import UserFactory


@pytest.fixture
def alice(db):
    return UserFactory(email="alice.fb@example.com")


@pytest.fixture
def superuser(db):
    return UserFactory(email="su.fb@example.com", is_superuser=True, is_staff=True)


# ---------------- report (POST) ----------------


@pytest.mark.django_db
def test_authenticated_user_can_report_a_bug(alice, client):
    client.force_login(alice)
    resp = client.post(
        reverse("feedback:report"),
        {
            "subject": "No me deja iniciar",
            "page_area": "Entrenamiento",
            "description": "Le pico Iniciar y no pasa nada.",
            "page_url": "/workouts/start/",
        },
        HTTP_REFERER="/",
    )
    assert resp.status_code == 302  # redirected back
    assert resp.url == "/"
    report = BugReport.objects.get(subject="No me deja iniciar")
    assert report.reporter == alice
    assert report.page_area == "Entrenamiento"
    assert report.page_url == "/workouts/start/"
    assert report.status == BugStatus.OPEN


@pytest.mark.django_db
def test_report_falls_back_to_referer_when_page_url_missing(alice, client):
    client.force_login(alice)
    client.post(
        reverse("feedback:report"),
        {"subject": "s", "description": "d"},
        HTTP_REFERER="/metrics/recuperacion/",
    )
    report = BugReport.objects.get(subject="s")
    assert report.page_url == "/metrics/recuperacion/"


@pytest.mark.django_db
def test_report_requires_subject_and_description(alice, client):
    client.force_login(alice)
    resp = client.post(reverse("feedback:report"), {"subject": "only subject"})
    assert resp.status_code == 400
    assert BugReport.objects.count() == 0


@pytest.mark.django_db
def test_report_requires_login(client):
    resp = client.post(
        reverse("feedback:report"),
        {"subject": "s", "description": "d"},
    )
    assert resp.status_code == 302
    assert "/auth/login" in resp.url
    assert BugReport.objects.count() == 0


# ---------------- admin list (superuser only) ----------------


@pytest.mark.django_db
def test_admin_list_403_for_normal_user(alice, client):
    client.force_login(alice)
    resp = client.get(reverse("feedback:admin"))
    # user_passes_test redirects to login by default.
    assert resp.status_code == 302
    assert "/auth/login" in resp.url


@pytest.mark.django_db
def test_admin_list_shows_all_users_reports_to_superuser(alice, superuser, client):
    BugReport.objects.create(reporter=alice, subject="AliceBug", description="x")
    BugReport.objects.create(reporter=superuser, subject="MyOwnBug", description="x")
    client.force_login(superuser)
    resp = client.get(reverse("feedback:admin"))
    assert resp.status_code == 200
    assert b"AliceBug" in resp.content
    assert b"MyOwnBug" in resp.content
    assert b"alice.fb@example.com" in resp.content  # reporter shown


@pytest.mark.django_db
def test_admin_list_filters_by_status(alice, superuser, client):
    BugReport.objects.create(reporter=alice, subject="OpenOne", description="x")
    BugReport.objects.create(
        reporter=alice, subject="ResolvedOne", description="x", status=BugStatus.RESOLVED
    )
    client.force_login(superuser)
    resp = client.get(reverse("feedback:admin") + "?status=resolved")
    assert b"ResolvedOne" in resp.content
    assert b"OpenOne" not in resp.content


@pytest.mark.django_db
def test_admin_status_change(alice, superuser, client):
    report = BugReport.objects.create(reporter=alice, subject="X", description="y")
    client.force_login(superuser)
    resp = client.post(reverse("feedback:admin_status", args=[report.id]), {"status": "triaged"})
    assert resp.status_code == 302
    report.refresh_from_db()
    assert report.status == BugStatus.TRIAGED


@pytest.mark.django_db
def test_admin_status_rejects_invalid_value(alice, superuser, client):
    report = BugReport.objects.create(reporter=alice, subject="X", description="y")
    client.force_login(superuser)
    resp = client.post(reverse("feedback:admin_status", args=[report.id]), {"status": "nope"})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_admin_status_blocked_for_normal_user(alice, client):
    report = BugReport.objects.create(reporter=alice, subject="X", description="y")
    client.force_login(alice)
    resp = client.post(reverse("feedback:admin_status", args=[report.id]), {"status": "triaged"})
    assert resp.status_code == 302
    assert "/auth/login" in resp.url
    report.refresh_from_db()
    assert report.status == BugStatus.OPEN  # unchanged


@pytest.mark.django_db
def test_admin_delete_blocked_for_normal_user(alice, client):
    report = BugReport.objects.create(reporter=alice, subject="X", description="y")
    client.force_login(alice)
    resp = client.post(reverse("feedback:admin_delete", args=[report.id]))
    assert resp.status_code == 302
    assert BugReport.objects.filter(pk=report.id).exists()


@pytest.mark.django_db
def test_admin_delete_works_for_superuser(alice, superuser, client):
    report = BugReport.objects.create(reporter=alice, subject="X", description="y")
    client.force_login(superuser)
    resp = client.post(reverse("feedback:admin_delete", args=[report.id]))
    assert resp.status_code == 302
    assert not BugReport.objects.filter(pk=report.id).exists()


# ---------------- floating button surfaces ----------------


@pytest.mark.django_db
def test_floating_bug_button_present_on_dashboard(alice, client):
    client.force_login(alice)
    resp = client.get(reverse("dashboard:home"))
    assert resp.status_code == 200
    assert b"Reportar un bug" in resp.content


@pytest.mark.django_db
def test_bugs_nav_link_visible_only_to_superuser(alice, superuser, client):
    client.force_login(alice)
    assert b"\xf0\x9f\x90\x9b Bugs" not in client.get(reverse("dashboard:home")).content  # 🐛 Bugs
    client.force_login(superuser)
    assert b"\xf0\x9f\x90\x9b Bugs" in client.get(reverse("dashboard:home")).content


@pytest.mark.django_db
def test_toast_renders_bottom_right_after_successful_report(alice, client):
    client.force_login(alice)
    # `follow=True` renders the redirected dashboard page — the messages framework
    # surfaces the toast there (and consumes it, so a subsequent GET won't see it).
    resp = client.post(
        reverse("feedback:report"),
        {"subject": "s", "description": "d"},
        HTTP_REFERER="/",
        follow=True,
    )
    assert resp.status_code == 200
    assert b"Bug reportado exitosamente" in resp.content
    # Regression: the surrounding {% if messages %} block must not leak its own
    # template comments — a multi-line {# … #} renders as literal text.
    assert b"{#" not in resp.content
