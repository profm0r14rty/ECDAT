#!/bin/sh
# ECDAT API container entrypoint.
#
# Applies pending Alembic migrations against the DATABASE_URL, then execs the
# container command (uvicorn by default; docker-compose passes the dev
# hot-reload variant). Runs with the working directory set by compose
# (/app/backend), so `alembic` picks up alembic.ini next to the mounted source.
set -e

# The Dockerfile WORKDIR is the repo root (/app), but alembic.ini lives in
# /app/backend and the FastAPI app package too — without this cd, `alembic
# upgrade head` fails ("No 'script_location' key found") and `app.main` is not
# importable, on any run outside Docker Compose (which already sets
# working_dir: /app/backend). Compose is unaffected: the cd is a no-op there.
cd /app/backend

echo "[entrypoint] Applying Alembic migrations against DATABASE_URL..."
alembic upgrade head
echo "[entrypoint] Migrations up to date."

echo "[entrypoint] Executing: $*"
exec "$@"