#!/usr/bin/env sh
# Container start for Railway. Run via `sh start.sh` so Railway's start-command
# parser stays happy (it rejects shell features like `&`, `()` and `<`).
#
# gunicorn starts immediately so the healthcheck (/auth/login/, no DB needed)
# passes without racing Railway's private network, which takes a few seconds to
# reach Postgres. Migrations + the superuser bootstrap run in the background and
# finish once the DB is reachable.
(python manage.py migrate --noinput && python manage.py createsuperuser --noinput </dev/null 2>&1 || true) &

exec gunicorn config.wsgi --bind "0.0.0.0:${PORT:-8000}" --workers 2 --timeout 30 --access-logfile -
