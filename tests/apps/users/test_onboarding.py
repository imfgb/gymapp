"""Tests for the onboarding flow + middleware."""

from __future__ import annotations

import pytest
from django.urls import reverse

from gymapp.apps.metrics.models import UserMetricSnapshot
from tests.factories import UserFactory


@pytest.fixture
def fresh_user(db):
    """New user with no onboarded_at flag (will be redirected to /onboarding/)."""
    return UserFactory(email="fresh@example.com", _onboard=False)


@pytest.fixture
def complete_user(db):
    """Default UserFactory already onboards the user via post_generation."""
    return UserFactory(email="complete@example.com")


@pytest.mark.django_db
def test_middleware_redirects_fresh_user_to_onboarding(fresh_user, client):
    client.force_login(fresh_user)
    resp = client.get(reverse("dashboard:home"))
    assert resp.status_code == 302
    assert resp.url == reverse("users:onboarding")


@pytest.mark.django_db
def test_middleware_does_not_redirect_complete_user(complete_user, client):
    client.force_login(complete_user)
    resp = client.get(reverse("dashboard:home"))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_middleware_lets_onboarding_page_through(fresh_user, client):
    """Otherwise we'd have a redirect loop."""
    client.force_login(fresh_user)
    resp = client.get(reverse("users:onboarding"))
    assert resp.status_code == 200
    assert b"Bienvenido" in resp.content


@pytest.mark.django_db
def test_middleware_lets_admin_through(fresh_user, client):
    """Don't block staff from /admin/ just because the personal profile is empty."""
    fresh_user.is_staff = True
    fresh_user.save()
    client.force_login(fresh_user)
    resp = client.get("/admin/")
    assert resp.status_code in (200, 302)  # 302 if redirected within admin, never to onboarding


@pytest.mark.django_db
def test_onboarding_post_persists_profile_and_redirects_home(fresh_user, client):
    client.force_login(fresh_user)
    resp = client.post(
        reverse("users:onboarding"),
        {
            "height_cm": "178",
            "date_of_birth": "1995-05-20",
            "sex": "male",
            "training_style": "powerbuilding",
            "training_goal": "hypertrophy",
            "activity_level": "moderate",
        },
    )
    assert resp.status_code == 302
    assert resp.url == reverse("dashboard:home")
    fresh_user.profile.refresh_from_db()
    assert fresh_user.profile.height_cm == 178
    assert fresh_user.profile.sex == "male"
    assert fresh_user.profile.is_onboarded


@pytest.mark.django_db
def test_onboarding_optional_initial_weight_creates_snapshot(fresh_user, client):
    client.force_login(fresh_user)
    client.post(
        reverse("users:onboarding"),
        {
            "height_cm": "178",
            "date_of_birth": "1995-05-20",
            "sex": "male",
            "weight_kg": "82.5",
        },
    )
    snap = UserMetricSnapshot.objects.get(owner=fresh_user)
    assert float(snap.weight_kg) == 82.5
    assert snap.notes == "Inicial (onboarding)"


@pytest.mark.django_db
def test_onboarding_post_requires_minimum_fields(fresh_user, client):
    client.force_login(fresh_user)
    resp = client.post(reverse("users:onboarding"), {"height_cm": "178", "sex": "male"})
    assert resp.status_code == 400  # missing date_of_birth
    fresh_user.profile.refresh_from_db()
    assert not fresh_user.profile.is_onboarded


@pytest.mark.django_db
def test_onboarding_skip_fills_defaults(fresh_user, client):
    client.force_login(fresh_user)
    resp = client.post(reverse("users:onboarding_skip"))
    assert resp.status_code == 302
    fresh_user.profile.refresh_from_db()
    assert fresh_user.profile.is_onboarded  # height + sex + DOB now populated


@pytest.mark.django_db
def test_onboarded_user_visiting_onboarding_still_allowed(complete_user, client):
    """A user who is already onboarded can re-visit /onboarding/ (no redirect)."""
    client.force_login(complete_user)
    resp = client.get(reverse("users:onboarding"))
    assert resp.status_code == 200
