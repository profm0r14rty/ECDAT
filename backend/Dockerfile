# ECDAT API image - FastAPI backend + the ecdat_core scanner engine.
#
# IMPORTANT: the build context is the REPO ROOT (see docker-compose.yml:
# `build: { context: ., dockerfile: backend/Dockerfile }`), because the API
# imports the `ecdat_core` package that lives at the monorepo root — a
# `./backend`-only context could not reach it.
#
# PYTHONPATH=/app puts the repo root on the import path, so `import backend`
# and `import ecdat_core` resolve to the source in /app. This mirrors the local
# dev environment, where `backend` is importable because commands run from the
# repo root — and it means the compose bind-mount of ./backend is what serves
# the code (stale site-packages copies never shadow it), so hot-reload sees
# every edit.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

# git is required for `ecdat_core.ingestion.ingest_git_url` (it shells out to
# `git clone`); python:3.12-slim does not ship it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- scanner engine (ecdat_core) -------------------------------------------
# Root pyproject.toml builds the `ecdat-core` package; signatures.json is
# shipped as package data and loaded relative to the module file.
COPY pyproject.toml ./
COPY ecdat_core/ ecdat_core/
RUN pip install .

# --- FastAPI backend -------------------------------------------------------
# backend/pyproject.toml declares the backend package **and** its runtime deps
# (fastapi, uvicorn[standard], sqlalchemy>=2, alembic, psycopg[binary], redis,
# python-multipart). The `backend` top-level package itself is not registered
# by setuptools (pyproject.toml sits inside its own package dir), which is
# fine: PYTHONPATH=/app above is what makes `import backend.*` work.
COPY backend/ backend/
RUN pip install ./backend

# --- entrypoint: alembic upgrade head, then the container command ----------
COPY backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Default command — compose overrides this with the --reload dev variant.
# Alembic migrations are applied by the entrypoint before uvicorn starts.
#
# JSON form (prevents the JSONArgsRecommended lint) wrapping sh -c: exec form
# does no variable expansion, so "$@"/sh -c is what expands "${PORT:-8000}" —
# Render assigns the public port dynamically via $PORT. Locally (Docker
# Compose) $PORT is unset, so this defaults to 8000, matching the compose
# `8000:8000` mapping.
#
# --app-dir /app/backend is REQUIRED: the Dockerfile WORKDIR is /app (repo
# root), so `app.main` would not resolve on Render — compose only works today
# because it sets `working_dir: /app/backend`. --app-dir reproduces that for
# the default-CMD path (probe-verified: without it, `import app.main` fails
# with ModuleNotFoundError and the container crash-loops on boot).
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["sh", "-c", "exec uvicorn app.main:app --app-dir /app/backend --host 0.0.0.0 --port \"${PORT:-8000}\""]