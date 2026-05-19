#!/usr/bin/env bash
# Build-time harness bootstrap.
#
# Run me at the start of every Claude Code session:
#   bash .claude/init.sh
#
# Validates the invariants from .claude/AGENTS.md and prints the next queued
# feature so the Leader can pick it up.

set -euo pipefail

cd "$(dirname "$0")/.."  # repo root

fail() { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
ok()   { printf '\033[32m✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[33m! %s\033[0m\n' "$*"; }

# --- Python version --------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  fail "python3 not found on PATH."
fi

py_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [[ "$py_version" != "3.12" ]]; then
  warn "Python ${py_version} active — project targets 3.12. Migrations and CI run under 3.12."
else
  ok "Python 3.12 active."
fi

# --- .env present ----------------------------------------------------------
if [[ ! -f .env ]]; then
  warn ".env missing. Copy .env.example to .env and fill DJANGO_SECRET_KEY."
else
  ok ".env present."
fi

# --- Single in_progress feature -------------------------------------------
if [[ ! -f .claude/feature_list.json ]]; then
  fail ".claude/feature_list.json missing."
fi

in_progress_count=$(python3 -c "
import json, sys
with open('.claude/feature_list.json') as f:
    data = json.load(f)
count = sum(1 for f in data['features'] if f['status'] == 'in_progress')
print(count)
")

if (( in_progress_count > 1 )); then
  fail "feature_list.json has ${in_progress_count} features in_progress — only one allowed at a time."
elif (( in_progress_count == 1 )); then
  in_progress_id=$(python3 -c "
import json
with open('.claude/feature_list.json') as f:
    data = json.load(f)
for feat in data['features']:
    if feat['status'] == 'in_progress':
        print(feat['id'])
        break
")
  ok "In-progress feature: ${in_progress_id}"
fi

# --- Next queued ----------------------------------------------------------
next_queued=$(python3 -c "
import json
with open('.claude/feature_list.json') as f:
    data = json.load(f)
for feat in data['features']:
    if feat['status'] == 'queued':
        print(f\"{feat['id']} :: {feat['title']}\")
        break
else:
    print('(nothing queued)')
")
ok "Next queued: ${next_queued}"

echo
echo "Ready. Leader: read .claude/AGENTS.md, then claim the next feature."
