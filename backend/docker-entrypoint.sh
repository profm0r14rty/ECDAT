#!/bin/sh
# ECDAT API container entrypoint.
#
# Applies pending Alembic migrations against the DATABASE_URL, then execs the
# container command (uvicorn by default; docker-compose passes the dev
# hot-reload variant). Runs with the working directory set by compose
# (/app/backend), so `alembic` picks up alembic.ini next to the mounted source.
set -e

echo "[entrypoint] Applying Alembic migrations against DATABASE_URL..."
alembic upgrade head
echo "[entrypoint] Migrations up to date."

echo "[entrypoint] Executing: $*"
exec "$@"