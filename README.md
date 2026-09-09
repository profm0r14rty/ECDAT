# ECDAT - Enterprise Cryptographic Discovery & Analysis Tool

ECDAT is a Cryptography Bill of Materials (CBOM) scanner for post-quantum readiness assessment. It discovers cryptographic artefacts in source code, assesses their quantum-computing risk using Mosca's algorithm, and recommends NIST post-quantum replacements, outputting a CycloneDX 1.6 CBOM report.

## Running locally

### Prerequisites

- Docker with Docker Compose (Compose v2+).

### Infrastructure + API + Dashboard

From the repo root, build and start the whole stack:

```bash
docker compose up --build
```

This brings up four services:

| Service  | Image / source       | Purpose                                            |
|----------|----------------------|----------------------------------------------------|
| postgres | `postgres:16-alpine` | Persistent scan database (named volume `postgres_data`) |
| redis    | `redis:7-alpine`     | Scan job status keys (`scan:{id}:status`)          |
| api      | `backend/Dockerfile` | FastAPI app on `http://localhost:8000`, uvicorn with hot reload |
| web      | `frontend/Dockerfile`| React dashboard at `http://localhost:5173`, nginx serves the build and reverse-proxies `/api` + `/health` to `api` |

Database credentials are read from `.env` (copy `.env.example` to `.env` and
adjust as needed). The compose file falls back to the same dev defaults, so a
plain `docker compose up --build` works with no `.env` file at all.

Smoke test — the API should answer immediately once the containers are up
(either directly, or through the web container's proxy):

```bash
curl http://localhost:8000/health
# {"status":"ok"}
curl http://localhost:5173/health
# {"status":"ok"}
```

The dashboard lives at `http://localhost:5173`. The `web` container keeps the
frontend bundle's default same-origin `VITE_API_BASE_URL`: nginx serves the
compiled static files and forwards `/api` + `/health` to the `api` service, so
no runtime env substitution or CORS config is needed in the containerized flow.

Details:

- On container start, the API entrypoint (`backend/docker-entrypoint.sh`)
  runs `alembic upgrade head` against Postgres before launching uvicorn.
- `./backend` is bind-mounted into the container and uvicorn runs with
  `--reload`, so backend code edits take effect without rebuilding.
- The `api` service waits for both `postgres` and `redis` to report healthy
  (`depends_on.condition: service_healthy`); `web` waits for `api` to start.

Tear down with `docker compose down` (add `-v` to also delete the Postgres
named volume).