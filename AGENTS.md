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

## Workflow
- Work is broken into numbered phases (Batch 1 = Phases 0–8, done; Fix Pass = Fix Phase 1–4; Batch 2 = Phases 9–15; further batches TBD).
- After each phase: run the full test suite, update `progress.md` (one row per phase: Status/Commit/Notes), commit with message `"Phase N: <description>"` or `"Fix Phase N: <description>"`.
- Never silently change what an existing `signatures.json` entry matches or how it's classified — if a fix changes an existing signature's behavior, say so explicitly in the phase report so downstream assumptions (tests, docs, frontend) get updated too.
