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

## Live Deployment

The project is deployed on Render's free tier.

- **API**: [https://ecdat-api.onrender.com](https://ecdat-api.onrender.com)
- **Dashboard**: [https://ecdat-web.onrender.com](https://ecdat-web.onrender.com)

**Note on cold starts**: The API sleeps after 15 minutes of inactivity. The first request after sleep will take about a minute to respond while the service warms up. Please hit the `/health` endpoint once before starting the demo to ensure the app is responsive.

## Securing a non-demo deployment (optional API-key auth)

By default ECDAT's API is fully open — anyone with the URL can submit scans and
read everyone's scan history. That's intentional for the public hackathon demo.
For anything resembling a real deployment, the API ships with a minimal
single-tier gate: when enabled, every `/api/scans*` endpoint (writes *and*
reads) requires an `Authorization: Bearer <key>` header. Full multi-tenant
auth (users, orgs, roles) is deliberately not part of this mechanism.

1. **Generate one or more keys** out-of-band — never reuse committed values:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Enable the gate** by setting two environment variables on the API:

   - `REQUIRE_API_KEY=true`
   - `API_KEYS=<comma-separated keys>` (whitespace around keys is fine)

   Where to set them depends on the deployment:

   - **Docker Compose** — add both to your `.env` (copied from
     `.env.example`); the `api` service passes them through.
   - **Render** — set both in the Web Service's **Environment** panel
     (note: Render's env vars are separate from a local `.env` file) and
     redeploy. Render's env changes apply on the next deploy — the gate reads
     them per request, so no restart is needed once the new env is live.

   The gate is **off by default**; with `REQUIRE_API_KEY` unset or `false`,
   behavior is unchanged. If you enable it without setting `API_KEYS`, the API
   fails closed (HTTP 500) rather than silently opening up.

3. **Clients** must send the key on every (non-`/health`) request:

   ```bash
   curl -H "Authorization: Bearer <key>" https://your-api/api/scans
   ```

   `GET /health` stays public so uptime monitors and warm-keeping pings keep
   working.

**Dashboard caveat**: the bundled dashboard is a public-demo artifact — its API
client sends no auth header, so once you flip the gate on, the dashboard's
`/api/scans` calls will be rejected (401). A non-demo deployment either uses
API-keyed clients / CI pipelines, or terminates the key at a same-origin proxy.
Key entry in the UI is intentionally out of scope for this gate.