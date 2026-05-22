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
    # Start collapsed: the expanded panel docks over the right third of the
    # viewport and covers every right-aligned control (delete-set ✕, "+ serie",
    # "Borrar"), making them unclickable.
    DEBUG_TOOLBAR_CONFIG = {"SHOW_COLLAPSED": True}
except ImportError:
    pass

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# In dev, skip Whitenoise's manifest storage — it requires `collectstatic` to
# build a manifest.json and otherwise raises ValueError on every {% static %}
# tag, which is what made the first runserver test feel slow (10s/page).
# Prod (`prod.py`) inherits the manifest storage from base.py and runs
# collectstatic at build time.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
