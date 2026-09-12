# ECDAT - Enterprise Cryptographic Discovery & Analysis Tool

## Project Purpose
ECDAT is a Cryptography Bill of Materials (CBOM) scanner for post-quantum readiness assessment (SIH 2026, Problem Statement 26164, NTRO). It discovers cryptographic artefacts in source code and dependency manifests, assesses each artefact's risk using Mosca's inequality, recommends NIST post-quantum replacements, and outputs a real CycloneDX 1.6 CBOM report plus a dashboard-friendly summary.

## Current Architecture (post Batch-1 fix pass)
- Repo root: `pyproject.toml` (PEP 621 — the package is built from the repo root, NOT from inside `ecdat_core/`; putting it inside `ecdat_core/` once broke test discovery by making every `.py` file a top-level module — don't repeat that).
- `ecdat_core/` — standalone, dependency-light scanner engine (only runtime dependency: `pydantic>=2`). No web-framework code lives here. It must stay independently importable, testable, and CLI-runnable without FastAPI/Postgres/Redis running.
  - `signatures.json` — the crypto signature knowledge base; source of truth for detection patterns and PQC recommendations. Edit this, not hardcoded values in `detector.py`, when adjusting algorithm coverage.
  - `signature_loader.py` — loads/validates `signatures.json` into `SignatureEntry` Pydantic models at import time.
  - `models.py` — `Detection`, `RiskAssessment`, `Recommendation`, `ScanResult` (the core data contract).
  - `detector.py` — regex-based scanning (`scan_file_content`, `detect_language`).
  - `ingestion.py` — repo/manifest ingestion (`ingest_local_directory`, `ingest_git_url`, `ingest_manifest_dependencies`).
  - `risk_engine.py` — Mosca's-inequality risk scoring (`assess_risk`).
  - `recommender.py` — PQC recommendation lookup (`recommend`).
  - `cbom_export.py` — CycloneDX 1.6 export (`export_cbom`, `export_summary`).
  - `cli.py` — orchestrates the full pipeline (`run_scan`); `python -m ecdat_core.cli scan <path>` entrypoint.
  - `tests/` — pytest, including `tests/fixtures/demo_repo/` (a small planted-vulnerability repo used for end-to-end tests).
- `backend/` — FastAPI app (Batch 2+). Wraps `ecdat_core`; never re-implements scanning logic in the API layer.
- `frontend/` — React + Vite + TS + Tailwind dashboard (Batch 3+).

## Environment
- A project virtualenv already exists at `test_virt_env/` (gitignored), package installed via `pip install -e ".[dev]"`. Reuse it — don't create a second venv. Run tests via `test_virt_env/bin/python -m pytest`.
- Network-gated tests (git-clone tests) are marked `network` and deselected by default. Run explicitly with `-m network` only when network access is confirmed available; don't assume it is.
- Do not spawn background/sub-agent delegation for exploration tasks — it has repeatedly failed in this environment with a model-resolution error (`opencode/gpt-5-nano` not found) and just wastes time before falling back to direct implementation anyway. Implement directly.

## Output Standard
Real CycloneDX 1.6 CBOM JSON. Component `type: "cryptographic-asset"`. `cryptoProperties.assetType` in `[algorithm, certificate, protocol, related-crypto-material]`. Never invent custom top-level fields — anything CycloneDX 1.6 has no slot for goes under `properties` with an `ecdat:` prefix (existing: `ecdat:riskLevel`, `ecdat:quantumVulnerable`, `ecdat:classicallyBroken`, `ecdat:confidence`, `ecdat:recommendedAlgorithm`, `ecdat:fipsReference`).

## Risk Model — two different concepts, do not conflate them (this was a real bug once)
1. **`quantum_vulnerable`** (bool, on `SignatureEntry` and `Detection`) — is this artefact broken *specifically* by a quantum algorithm (Shor's/Grover's)? RSA/ECC/DH/DSA = yes. ML-KEM/ML-DSA/SLH-DSA = no. Symmetric ciphers with a `min_quantum_safe_key_bits` threshold (currently AES: 192) are computed dynamically per-detection from the extracted key size, in `detector.py`.
2. **`classically_broken`** (bool, on `SignatureEntry` and `Detection`) — is this artefact already broken/deprecated *today*, independent of quantum computers entirely? MD5, SHA-1, DES, 3DES, RC4 = yes. This must never be reported as "quantum-safe" — that mislabels an actively-exploitable weakness as fine.

`assess_risk()` branch order, in this priority:
1. `classically_broken` → `risk_level="critical"`, `mosca_violation=True`, `urgency_ratio` floored at `1.0` (X/Y/Z are still computed via the normal heuristics for transparency, just floored so the Pydantic consistency validator holds). Rationale text must say this is a classical break, not a quantum-specific one.
2. Else `quantum_vulnerable is False` → `risk_level="quantum-safe"`, short-circuit (skip the Mosca formula).
3. Else → full Mosca's inequality: `urgency_ratio = (X + Y) / Z`; thresholds critical≥1.0, high≥0.8, medium≥0.5, else low.

## Detection Coverage Convention
Every applicable algorithm family's Python patterns must cover both the `cryptography` (hazmat) library style AND the PyCryptodome (`Crypto.*`) style — the two dominant Python crypto libraries. When adding any signature, ask: "would this miss a very common, idiomatic way of writing this?" An invisible artefact is worse than a low-confidence one — prefer a broad 0.5–0.6-confidence match over no match. If a language genuinely has no natural equivalent API for a given family, say so explicitly rather than inventing a pattern that doesn't correspond to real code.

## Recommendation Engine Convention
The "already using PQC, no migration needed" message in `recommender.py` fires only when `quantum_vulnerable is False` AND the signature's `family` is `pqc-kem` or `pqc-signature` (see `_PQC_FAMILIES`). It must not fire for other quantum-safe-but-not-PQC cases (classically-broken hashes, or adequately-sized AES) — those get their normal `pqc_recommendation` payload instead.

## Coding Conventions
Type-hinted Python, Pydantic v2 models, pytest for all new logic, small single-purpose functions, docstrings on every public function. When a real ambiguity or contradiction turns up between these instructions and what a required test demands, resolve it in favor of technical correctness as documented here, and state the deviation explicitly in your phase report — don't silently pick one interpretation.

## Backend Conventions (Batch 2+)
FastAPI + SQLAlchemy 2.0 (typed `Mapped[...]` style) + Alembic migrations + Postgres for persistence, Redis for job status only (not a message broker — background work runs via FastAPI `BackgroundTasks`, not Celery, to avoid extra infra under the hackathon deadline). The API layer never duplicates `ecdat_core` logic — it calls into `ecdat_core.cli.run_scan` (or an equivalent orchestrator function) and persists the resulting `ScanResult`.

## Security Conventions (Phase 45+)
Ingestion targets are the only user-controlled inputs that touch the network or the filesystem, so both ingestion paths are sandboxed by default. The protections live in `ecdat_core/ingestion.py` (the capability boundary — defense in depth, CLI included) and are re-checked at request time in `backend/app/routers/scans.py` (`POST /api/scans` returns a clear 400 instead of an asynchronous background failure). Never bypass these validators when a new endpoint accepts a user-controlled path or URL.

**git_url — SSRF protection** (`validate_git_url`, invoked before every `git clone`):
1. Scheme must be `https://` only. `file://`, `git://`, `ssh://`, plain `http://`, and scheme-less strings are rejected with a clear message.
2. The hostname is resolved via `socket.getaddrinfo` and **every** resolved address is checked against Python's `ipaddress` module — any address flagged `is_private`, `is_loopback`, `is_link_local`, `is_reserved`, or `is_multicast` rejects the URL (this blocks internal networks, loopback, and cloud metadata endpoints like `169.254.169.254`). Known residual risk: DNS-rebinding (resolve-then-connect TOCTOU) is not defended against at this stage — documented and accepted, do not "fix" it with more machinery.
3. `GIT_URL_ALLOWED_HOSTS` (env, comma-separated hostnames, unset = no restriction) optionally restricts cloning to known git hosts for hardened deployments. The allowlist does **not** bypass the IP checks — an allowlisted host that resolves to a private address is still rejected.
4. `GIT_URL_MAX_SIZE_MB` (env, default `200`) sets a post-clone size ceiling; an oversized clone aborts the scan cleanly (the temp clone directory is removed first) instead of consuming resources or hanging.

**local_path — workspace sandbox** (`validate_local_path`):
- Every local-path scan target must resolve — symlinks followed via `os.path.realpath` — inside `SCAN_WORKSPACE_ROOT` (env). Default: the bundled `ecdat_core/tests/fixtures` directory, resolved package-relative so the container path (`/app/ecdat_core/tests/fixtures`) is covered automatically; existing fixture-based demo/showcase scans keep working with zero config.
- Violations are rejected with a clear 400 at `POST /api/scans`, and `ingest_local_directory` / `ingest_manifest_dependencies` enforce the same containment as defense in depth.
- To scan other directories in a hardened deployment, widen `SCAN_WORKSPACE_ROOT` (e.g. `/app/data`) — never disable the check.

## Frontend Conventions (Batch 3+)
- Stack: Vite + React 19 + TypeScript + Tailwind CSS v4 (via the `@tailwindcss/vite` plugin — no `tailwind.config.js`/`postcss.config.js`; v4 is configured in `src/index.css` + `vite.config.ts`), shadcn/ui (`components.json` base: `radix`, `baseColor: neutral`), React Router 7 (`createBrowserRouter`), Recharts for charts, axios for HTTP.
- Components come from `npx shadcn@latest add <component>` — add through the CLI (it resolves registry + CSS vars), never hand-write `components.json`-tracked files. Import via `@/components/ui/...` (path alias `@/* -> src/*` lives in `vite.config.ts` and `tsconfig.app.json`).
- **Never call `fetch`/`axios` directly in a component** — always go through `frontend/src/api/client.ts` (`api.getHealth/createScan/listScans/getScan/getArtefacts/getCbom/getReport/patchArtefact`) so response shapes stay in one place. Its TypeScript interfaces mirror the Pydantic response models in `backend/app/routers/scans.py` 1:1 — when the backend models change, update the client too.
- Base URL: `VITE_API_BASE_URL` env var. Unset (default) → same-origin, meaning Vite's dev proxy (`vite.config.ts` `server.proxy`, forwards `/api` and `/health` to `http://localhost:8000`) handles calls with zero CORS. Set it (e.g. `http://localhost:8000` to hit a containerized API directly) → the backend's CORS middleware must allow the origin (`CORS_ORIGINS` env, comma-separated, default = Vite dev origins `http://localhost:5173`).
- Routing: `src/App.tsx` — `/` = scan list + new-scan form, `/scans/:id` = scan detail (grows into overview/artefacts/etc. as tabs or sub-routes). Pages live in `src/pages/`.
- Commands (from `frontend/`): `npm run dev` (dev server + proxy), `npm run build` (`tsc -b && vite build` — must stay TS-error-free). Run `tsc -b` via the build before claiming a phase done.

## Workflow
- Work is broken into numbered phases (Batch 1 = Phases 0–8, done; Fix Pass = Fix Phase 1–4; Batch 2 = Phases 9–15; further batches TBD).
- After each phase: run the full test suite, update `progress.md` (one row per phase: Status/Commit/Notes), commit with message `"Phase N: <description>"` or `"Fix Phase N: <description>"`.
- Never silently change what an existing `signatures.json` entry matches or how it's classified — if a fix changes an existing signature's behavior, say so explicitly in the phase report so downstream assumptions (tests, docs, frontend) get updated too.

## Deployment Conventions (Render — primary, free)
Primary hackathon deployment target: Render.com's free tier — a Docker-based Web Service for the API, a Static Site for the frontend build, a free managed Postgres database, and a free Redis-compatible Key Value store. No credit card required, no capacity-constrained provisioning (unlike the Oracle plan below, which is deprioritized for now — see that section's note).

Port binding: Render assigns the public port dynamically via a `$PORT` environment variable — the API's entrypoint must bind uvicorn to `0.0.0.0:$PORT` (falling back to `8000` for local/Docker Compose dev where `$PORT` isn't set), not a hardcoded port. Check `backend/docker-entrypoint.sh` and fix this if it currently hardcodes the port.

git availability: `ingestion.ingest_git_url` shells out to `git clone`. The existing `backend/Dockerfile` is based on `python:3.12-slim`, which does NOT include git by default — verify `git` is installed in the image (`apt-get install -y git` in the Dockerfile) before relying on git_url scans working in the deployed container. This may never have been exercised in a real container before (prior verification used `local_path` scans against the bundled fixture) — treat it as unverified until a real git_url scan is tested against the deployed instance.

Infrastructure as code: define the full topology (api web service, frontend static site, Postgres database, Key Value store) in a `render.yaml` Blueprint at the repo root rather than clicking through the dashboard by hand — this makes redeploys reproducible, which matters when you're iterating close to a deadline. Wire cross-service env vars (`DATABASE_URL`, `REDIS_URL`, the frontend's API base URL) via the Blueprint's `fromDatabase`/`fromService` references rather than hand-copying connection strings.

CORS: the frontend (static site) and API (web service) will be on different Render subdomains, unlike the same-origin nginx setup in docker-compose.yml — the existing `CORS_ORIGINS` env var on the backend must be set to the real deployed frontend URL, and the frontend's `VITE_API_BASE_URL` must point at the real deployed API URL (both are already env-driven per the Frontend/Backend Conventions sections above — this is a config change, not a code change).

Cold starts: the free web service sleeps after 15 minutes of inactivity with a roughly one-minute cold-start on the next request. Before any live demo or judging session, hit the deployed API's `/health` endpoint once a few minutes ahead of time to ensure it's warm — don't let the first request a judge triggers be the one that eats the cold-start delay.

Keeping the API warm: during the judging window, you can ensure the API stays responsive by opening the URL yourself a few minutes before you're called. For a set-and-forget option, UptimeRobot's free tier can ping the `/health` endpoint every 5 minutes, which is more than enough to prevent the 15-minute sleep.

## Deployment Conventions (Oracle Cloud Free Tier — secondary, future)
Target: a single Oracle Cloud "Always Free" Ampere A1 (ARM/aarch64) compute instance, `VM.Standard.A1.Flex`, Ubuntu 24.04. Design for 2 OCPU / 12 GB RAM as the ceiling — Oracle's Always Free Ampere A1 allowance was cut from 4 OCPU/24GB to 2 OCPU/12GB in mid-2026 and enforcement has been inconsistent across tenancies, so build for the smaller number rather than assuming the larger one is available. 200 GB block storage and 10 TB/month egress are part of Always Free and are not a constraint at this project's scale. No paid resources of any kind are in scope: no OCI Load Balancer, no managed database, no purchased domain — access is via the instance's public IP (optionally a free dynamic-DNS hostname).

Architecture: the instance is ARM64/aarch64, not x86-64. Every image already in docker-compose.yml (postgres:16-alpine, redis:7-alpine, python:3.12-slim, node:22-alpine, nginx:1.27-alpine) is officially multi-arch and has native arm64 builds — no Dockerfile base-image changes are needed for architecture compatibility. Do not assume an image or dependency works on arm64 just because it works on the dev machine's x86-64 — verify with a real arm64 build (`docker buildx build --platform linux/arm64`) before relying on it deploying unseen.

Build-vs-run split: do not build container images on the free-tier VM itself — a concurrent frontend build (`npm run build`) alongside Postgres/Redis/the API on a 2-OCPU box risks a slow or OOM-killed build at exactly the moment you need the machine serving traffic. Build images elsewhere (locally with `docker buildx build --platform linux/arm64`, or a free CI runner) and push to a free registry (GitHub Container Registry, `ghcr.io`, free for public repos); the VM only ever runs `docker compose pull && docker compose up -d`, never `--build`.

Networking: OCI's default Virtual Cloud Network security list blocks all inbound traffic except SSH (port 22). Any port the app needs reachable (the `web`/nginx service's port) must be opened in TWO places, not one: the OCI Security List / Network Security Group (console or `oci` CLI) AND the instance's own OS-level firewall (Ubuntu ships with restrictive default iptables/netfilter rules on OCI images) — a service that's "up" but unreachable from outside is almost always this double-firewall gap, not an application bug. Check both before assuming the app is broken.

Persistence and secrets: Postgres data lives on the existing named Docker volume (already defined in docker-compose.yml), which is durable across container restarts but is a single point of failure on a single free VM — take periodic `pg_dump` backups (a simple cron job is enough for a hackathon deployment, no need to over-engineer this). `.env` lives only on the VM, is never committed, and `.env.example` stays the template others copy from. No new secret-management system — this is a hackathon deployment, not a production SaaS.

Fallback: if Always Free Ampere A1 provisioning is capacity-constrained in the home region when it's actually needed, the fallback is running the full Docker Compose stack locally and exposing it via a free tunnel (Cloudflare Tunnel or ngrok) for a working live URL — this is an acceptable, not-lesser demo path and should not be treated as a last resort to be embarrassed about.
