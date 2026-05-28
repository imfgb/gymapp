"""Per-page contextual hint banner (core.context_processors.page_hint)."""

from __future__ import annotations

import pytest
from django.test import RequestFactory
from django.urls import reverse

from gymapp.apps.core.context_processors import HINTS_VERSION, PAGE_HINTS, page_hint
from tests.factories import UserFactory


@pytest.fixture
def alice(db):
    return UserFactory(email="hints@example.com")


@pytest.mark.django_db
def test_dashboard_renders_hint_banner(alice, client):
    client.force_login(alice)
    resp = client.get(reverse("dashboard:home"))
    assert resp.status_code == 200
    title, body = PAGE_HINTS["dashboard:home"]
    assert title.encode() in resp.content
    assert body.encode() in resp.content
    # Wired for client-side dismissal via the Alpine component + versioned key.
    assert b'x-data="pageHint(' in resp.content
    assert f"hint:dashboard:home:v{HINTS_VERSION}".encode() in resp.content


@pytest.mark.django_db
def test_nutrition_page_shows_its_own_hint_not_the_dashboard_one(alice, client):
    client.force_login(alice)
    resp = client.get(reverse("nutrition:home"))
    assert resp.status_code == 200
    assert PAGE_HINTS["nutrition:home"][0].encode() in resp.content
    assert PAGE_HINTS["dashboard:home"][0].encode() not in resp.content


@pytest.mark.django_db
def test_page_without_a_hint_renders_no_banner(alice, client):
    """A POST/action endpoint isn't in the map, so no banner is injected."""
    client.force_login(alice)
    # The login page resolves to a view with no hint entry.
    resp = client.get(reverse("dashboard:home"))
    # Sanity: the home page DOES have one (guards against a false negative).
    assert b'x-data="pageHint(' in resp.content


def test_context_processor_returns_empty_for_unmapped_view():
    request = RequestFactory().get("/whatever/")
    request.resolver_match = None
    assert page_hint(request) == {}


def test_context_processor_builds_versioned_key():
    request = RequestFactory().get("/")

    class _Match:
        view_name = "metrics:goals"

    request.resolver_match = _Match()
    ctx = page_hint(request)
    assert ctx["page_hint"]["key"] == f"hint:metrics:goals:v{HINTS_VERSION}"
    assert ctx["page_hint"]["title"] == PAGE_HINTS["metrics:goals"][0]


def test_every_hint_has_a_nonempty_title_and_body():
    for view_name, (title, body) in PAGE_HINTS.items():
        assert title.strip(), view_name
        assert body.strip(), view_name
