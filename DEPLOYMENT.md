# Deployment

How gymapp deploys to Railway, plus the Phase 0 verification checklist.

**LIVE on Railway** (free trial credit, not paying). The public URL lives in the
Railway dashboard → Settings → Networking.

## 1. Architecture

- **Web service**: single Railway service built from `Dockerfile`, runs `gunicorn config.wsgi`.
- **Database**: Railway-managed PostgreSQL 16. `DATABASE_URL` is referenced on the
  web service as `${{Postgres.DATABASE_URL}}` — it is **not** auto-injected across services.
- **Static**: Whitenoise serves compiled assets directly from the web dyno. No CDN, no S3.
- **TLS**: Railway terminates TLS; the app reads `X-Forwarded-Proto` via `SECURE_PROXY_SSL_HEADER`.

No Redis, no worker, no Celery (per decision #10).

## 1a. Start command — `sh start.sh` (hard-won, the 2026-05-25 deploy saga)

The start command is `sh start.sh` (in `railway.json` and the Dockerfile `CMD`).
`start.sh` starts **gunicorn immediately** and runs **`migrate` + `createsuperuser`
(from `DJANGO_SUPERUSER_*`) in the BACKGROUND**. Three reasons it must be this way:

1. **Healthcheck 400** — Railway's healthcheck hits the app with
   `Host: healthcheck.railway.app`, so `ALLOWED_HOSTS` MUST include `.railway.app`
   and `CSRF_TRUSTED_ORIGINS` `https://*.railway.app` (done in `prod.py`). Otherwise
   Django answers 400 → healthcheck fails.
2. **`migrate` hung at boot** — connecting to Postgres before Railway's private
   network (`*.railway.internal`, IPv6) is ready means gunicorn never starts →
   healthcheck fails. Fix: gunicorn first, DB setup backgrounded.
3. **"Failed to parse start command"** — Railway's startCommand parser rejects
   shell `&`, `()`, `<`. So the background logic lives in `start.sh`, invoked as the
   parser-safe `sh start.sh`.

Healthcheck: `healthcheckPath=/auth/login/` (a GET that needs no DB → passes the
moment gunicorn is up), `healthcheckTimeout=60`. `DJANGO_SETTINGS_MODULE=config.settings.prod`
is baked into the Dockerfile.

## 2. First-time setup

1. **Create the GitHub repo**.
   - Go to <https://github.com/new>; name it `gymapp`, visibility **Private**, no README/LICENSE/.gitignore (the local repo has those).
   - Locally: `git remote add origin git@github.com:imfgb/gymapp.git && git push -u origin main`.

2. **Create the Railway project**.
   - Sign in to <https://railway.app>.
   - **New Project → Deploy from GitHub repo** → pick `imfgb/gymapp`.
   - Railway detects the `Dockerfile` and starts building.

3. **Add Postgres**.
   - In the Railway project, **+ New → Database → Add PostgreSQL**.
   - Railway auto-injects `DATABASE_URL` into the web service.

4. **Set env vars on the web service** (Railway → Service → Variables):

   | Variable | Value |
   |---|---|
   | `DJANGO_SETTINGS_MODULE` | `config.settings.prod` |
   | `DJANGO_SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(50))"` (paste output) |
   | `DJANGO_DEBUG` | `false` |
   | `DJANGO_ALLOWED_HOSTS` | `<your-service>.up.railway.app` (Railway shows the domain) |
   | `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://<your-service>.up.railway.app` |
   | `SENTRY_DSN` | (optional) paste from <https://sentry.io> project settings |
   | `TIME_ZONE` | `America/Mexico_City` |
   | `LANGUAGE_CODE` | `es-mx` |

5. **Run the release migrations** (Railway runs `Procfile`'s `release:` automatically on each deploy). Watch the deploy logs for `Operations to perform: Apply all migrations:`.

6. **Create the first superuser**.
   - Railway → Service → ⋮ → **Run command**: `python manage.py createsuperuser`.
   - Or open a one-shot shell from the Railway dashboard.

7. **Visit** the public URL → `/auth/login/` → log in → `/admin/` to invite users.

## 3. Ongoing deploys

Push to `main` → Railway auto-builds the Dockerfile → `start.sh` runs gunicorn
immediately and backgrounds `migrate` (see §1a) → new container takes traffic once
the health check passes.

**Triggering a deploy:** GitHub push *should* auto-deploy but has been flaky/laggy.
Reliable manual trigger: gymapp → Variables → add/delete any variable → "Apply
change → **Deploy**" (builds the **latest** commit). Do NOT use "Redeploy" — it
re-runs the SAME (often old) commit.

Hot fixes:

- For an urgent rollback, Railway's **Deployments** tab lets you re-promote any previous successful build.
- Never edit a migration that's already merged to `main`. Add a *new* migration that supersedes it.

## 3a. Adding users (invite-only)

`/admin/` → Users → Add user (email + password); the Profile auto-creates via the
`post_save` signal; leave `is_staff` / `is_superuser` OFF. `OwnerScopedAdmin` shows
the superuser ALL users' data in `/admin/`, while each normal user sees only their
own data in the app.

## 4. Custom domain (optional)

1. Railway → Service → Settings → **Networking → Add domain**.
2. Add CNAME at your DNS host pointing to Railway's target.
3. Update env vars: append the custom domain to `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`.
4. Railway issues a Let's Encrypt cert automatically.

## 5. Phase 0 verification checklist

Run through this before declaring the scaffold done. **No code changes pass this list while any item is red.**

- [ ] `python manage.py check --deploy --settings=config.settings.prod` returns zero warnings (after `DJANGO_SECRET_KEY` + `DJANGO_ALLOWED_HOSTS` are set in the local env for the run).
- [ ] `ruff check .` passes.
- [ ] `ruff format --check .` passes.
- [ ] `pytest` passes (smoke tests in `tests/test_smoke.py` cover settings + factory + services).
- [ ] `docker compose up -d && python manage.py migrate` succeeds from a fresh clone.
- [ ] `python manage.py runserver` serves `/auth/login/` and `/admin/` without errors.
- [ ] `git push` to `imfgb/gymapp` triggers a Railway build that goes green.
- [ ] The deployed URL serves the same `/auth/login/` and `/admin/`.
- [ ] `bash .claude/init.sh` runs without errors and prints the next queued feature.
- [ ] Sentry receives a deliberate `raise Exception("sentry smoke test")` (one-shot mgmt command), then is removed.

## 6. Rollback plan

1. Railway → Deployments → pick a known-good previous deploy → **Redeploy**.
2. If the bad deploy introduced a migration, you may need to manually `python manage.py migrate <app> <previous_migration>` *before* redeploying. Plan migrations to be backward-compatible (add columns nullable first, deploy, backfill, then enforce non-null in a later deploy) so this rarely matters.

## 7. Cost ceiling

Railway's hobby tier (~$5/mo with $5 of usage included) comfortably covers ≤ 20 users + a small Postgres. Set spend limits in the Railway billing dashboard so an unexpected spike doesn't surprise you.

Sentry's free tier (5k errors/month) is plenty at this scale.
