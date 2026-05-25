# syntax=docker/dockerfile:1.7
#
# Production image. Used by Railway. Local dev uses `python manage.py runserver`
# directly, NOT this image — keeps the dev loop fast.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

WORKDIR /app

# System deps. libpq is needed by psycopg even with the [binary] wheel for some platforms.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for better layer caching.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Application code
COPY . .

# Collect static files at build time so the container starts faster.
# SECRET_KEY is required by Django even for `collectstatic`; pass a throwaway here.
RUN DJANGO_SECRET_KEY=build-time-not-used \
    DJANGO_ALLOWED_HOSTS=* \
    python manage.py collectstatic --noinput

# Drop privileges
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Railway provides PORT at runtime.
ENV PORT=8000
EXPOSE 8000

# On Railway the railway.json startCommand drives the container; this CMD mirrors
# it. gunicorn starts immediately (so the healthcheck passes without racing
# Railway's private networking, which takes a few seconds to reach Postgres);
# migrate + superuser bootstrap run in the background once the DB is reachable.
CMD ["sh", "-c", "(python manage.py migrate --noinput && python manage.py createsuperuser --noinput </dev/null 2>&1 || true) & exec gunicorn config.wsgi --bind 0.0.0.0:${PORT} --workers 2 --timeout 30 --access-logfile -"]
