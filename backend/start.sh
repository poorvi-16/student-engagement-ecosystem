#!/bin/sh
# Production entrypoint: apply pending migrations, then serve.
# Safe because the backend runs as a single instance (see CLAUDE.md).
set -e
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*"
