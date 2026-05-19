# gymapp

A personal gym workout tracking web application (Django 5.2 + HTMX + Tailwind), deployed on Railway. For a small private circle of users.

> 🤖 If you're a Claude Code session — read **`CLAUDE.md`** first, then `.claude/AGENTS.md`, then run `bash .claude/init.sh`.

## Quickstart (local development)

Requirements: Python 3.12, Docker (for Postgres).

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env

# Generate a dev SECRET_KEY:
python -c "import secrets; print(secrets.token_urlsafe(50))"
# Paste it into DJANGO_SECRET_KEY in .env

docker compose up -d           # Postgres on localhost:5432
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Then open:

- <http://127.0.0.1:8000/> — dashboard (after login)
- <http://127.0.0.1:8000/auth/login/> — sign in
- <http://127.0.0.1:8000/admin/> — superuser admin (create new users here)

Optional: `pre-commit install` to run ruff before every commit.

## Tests

```bash
pytest
```

## Documentation

- **CLAUDE.md** — architectural memory; the most important doc for understanding *why*.
- **ARCHITECTURE.md** — system design overview.
- **ROADMAP.md** — what's in each phase.
- **DATABASE.md** — schema by app.
- **API_DESIGN.md** — HTMX endpoint catalogue.
- **DEPLOYMENT.md** — Railway runbook + verification checklist.
- **DECISIONS.md** — ADR log.

## License

Private. Not for public distribution.
