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
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]