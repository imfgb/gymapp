"""Production settings (Railway).

DEBUG is forced off. Security headers / HSTS / cookie flags are enabled.
Sentry is wired only when SENTRY_DSN is present so dev/test never accidentally
sends events.
"""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

# Railway hosts. The platform's deploy healthcheck calls the app with
# `Host: healthcheck.railway.app` and the generated public domain lives under
# `*.up.railway.app`; trust the whole `railway.app` space so the healthcheck and
# the generated domain work with no manual ALLOWED_HOSTS config. A custom domain
# can still be added via DJANGO_ALLOWED_HOSTS.
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[]) + [
    ".railway.app",
    "localhost",
    "127.0.0.1",
]

# Trust the Railway proxy's HTTPS termination.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30  # 30 days; raise to 1y after first stable deploy
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# CSRF trusted origins — set via env so adding a custom domain doesn't require a
# deploy. The Railway-generated domain is trusted automatically.
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[]) + [
    "https://*.railway.app",
]

# ---------------------------------------------------------------------------
# Sentry — optional. Skips initialization if DSN isn't set.
# ---------------------------------------------------------------------------
SENTRY_DSN = env.str("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.0,  # no perf monitoring on free tier
        send_default_pii=False,
        environment=env.str("SENTRY_ENVIRONMENT", default="prod"),
    )
