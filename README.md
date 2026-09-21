# ECDAT - Enterprise Cryptographic Discovery & Analysis Tool

ECDAT is a Cryptography Bill of Materials (CBOM) scanner for post-quantum readiness assessment. It discovers cryptographic artefacts in source code, assesses their quantum-computing risk using Mosca's algorithm, and recommends NIST post-quantum replacements, outputting a CycloneDX 1.6 CBOM report.

## Install the CLI

The `ecdat` command is a standalone, pip-installable scanner — no Docker,
Postgres, Redis, or API required. It runs fully offline; see
[Privacy and trust](#privacy-and-trust).

```bash
pipx install ecdat        # recommended: isolated and on PATH
uv tool install ecdat     # recommended if you use uv
pip install ecdat         # into the active Python environment
```

If `pip install` stops with `error: externally-managed-environment`, that is
[PEP 668](https://peps.python.org/pep-0668/) protecting your OS Python — use
`pipx` or `uv tool` (or a virtualenv) rather than forcing the install. On
Windows, install with `py -m pip install ecdat`; if `ecdat` is not on `PATH`,
run the CLI as `py -m ecdat …`.

Upgrade or remove it later:

```bash
pipx upgrade ecdat           # or: uv tool upgrade ecdat
pip install --upgrade ecdat
pipx uninstall ecdat         # or: uv tool uninstall ecdat
```

### 60-second tour

```bash
ecdat demo                                   # scan the bundled sample project
ecdat about                                  # credits and an animated 3D globe
ecdat scan .                                 # scan the current directory
ecdat scan https://github.com/<user>/<repo>  # scan a public https:// repo
ecdat help                                   # list every command
ecdat doctor                                 # check your environment
```

<!-- screenshots: docs/img/*.png -->

### Commands

| Command | What it does |
|---------|--------------|
| `ecdat scan <path-or-url>` | Scan a local directory, or an `https://` Git repository |
| `ecdat demo` | Scan the bundled, deliberately-insecure sample project (zero setup) |
| `ecdat doctor` | Environment self-check (Python, git, signatures, `ECDAT_HOME`) |
| `ecdat about` | Credits, project links, and a spinning 3D globe |
| `ecdat help [command]` | Command overview, or full help for one command |
| `ecdat version` | Version, engine, signature count, Python, and OS |

Global flags: `--version`, `--no-color`, `--debug`.

### Output formats

`ecdat scan --format <pretty|json|cbom|summary>`:

- `pretty` (default) — the colourised terminal report.
- `json` — the full `ScanResult`.
- `cbom` — a CycloneDX 1.6 CBOM.
- `summary` — the risk rollup used by dashboards.

Payload formats write **only** the payload to stdout; progress, warnings, and
errors go to stderr. That keeps `ecdat scan . -f cbom > cbom.json` safe to
pipe. `ecdat demo` supports `pretty`, `json`, and `summary`.

### Use in CI

```bash
ecdat scan . --fail-on high
```

`--fail-on <critical|high|medium|low>` returns exit code `1` when any finding
is at or above that level (`quantum-safe` findings never count). Exit codes:
`0` success · `1` findings at or above `--fail-on` · `2` usage/validation
error · `3` scan/runtime/unexpected error · `130` interrupted (`Ctrl-C`).

### Privacy and trust

- **Runs fully offline.** The only network access is `git clone` for an
  explicit `https://` URL scan; local scans never touch the network.
- **No telemetry, no update checks.**
- **Hostile repo content cannot inject escapes or markup.** File paths,
  snippets, and algorithm names from scanned repositories are attacker-
  controlled; the CLI renders them as plain text, never as Rich/HTML/Markdown
  markup. Covered by `ecdat/tests/test_app_render.py`.

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