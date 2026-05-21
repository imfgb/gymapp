"""Test settings — fast hasher, predictable DB, no Sentry, no whitenoise."""
from .base import *  # noqa: F401,F403
from .base import MIDDLEWARE

DEBUG = False

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Use plain StaticFilesStorage — no manifest, no compression. Avoids the
# `collectstatic` requirement and the `staticfiles/` directory check.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Whitenoise warns when STATIC_ROOT doesn't exist (collectstatic hasn't run);
# our strict filterwarnings turn that warning into an error during request
# handling. Drop the middleware in tests — we don't serve static files in
# unit tests anyway.
MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m.lower()]
