"""Onboarding middleware.

Redirects an authenticated user to `/onboarding/` until they fill the minimum
profile (height + sex + DOB). Lets `/admin`, `/auth`, static and the onboarding
flow itself through.

Designed to be cheap: one ORM hit per request (a Profile fetch), only when
the user is already authenticated.
"""

from __future__ import annotations

from django.shortcuts import redirect
from django.urls import reverse

# Always allow these URL prefixes through, even for incomplete profiles —
# otherwise the user can never reach the onboarding page or log out.
_ALLOWED_PREFIXES = (
    "/admin",
    "/auth",
    "/static",
    "/__debug__",
    "/onboarding",
    "/favicon",
)


class OnboardingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and not any(request.path.startswith(p) for p in _ALLOWED_PREFIXES)
        ):
            profile = getattr(user, "profile", None)
            if profile is not None and profile.onboarded_at is None:
                return redirect(reverse("users:onboarding"))
        return self.get_response(request)
