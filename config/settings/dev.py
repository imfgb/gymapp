"""Local development settings.

Loaded when `DJANGO_SETTINGS_MODULE=config.settings.dev`. Adds debug toolbar
(if installed), prints emails to the console, and is happy with the insecure
default SECRET_KEY from `.env`.
"""
from .base import *  # noqa: F401,F403
from .base import INSTALLED_APPS, MIDDLEWARE

DEBUG = True

# Internal IPs for django-debug-toolbar
INTERNAL_IPS = ["127.0.0.1", "localhost"]

try:
    import debug_toolbar  # noqa: F401

    INSTALLED_APPS += ["debug_toolbar"]
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")
except ImportError:
    pass

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
