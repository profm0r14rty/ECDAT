# ECDAT Project Progress

## Batch 1 Summary

ECDAT's scanner core (Batch 1) is complete and tested end-to-end. It now
discovers cryptographic artefacts in source code across Python, JavaScript,
Java, Go, and C/C++ via regex signatures, assesses each artefact's post-quantum
risk using Mosca's inequality (with key-size- and path-based heuristics),
recommends NIST post-quantum replacements (ML-KEM, ML-DSA, SLH-DSA, AES-256),
and exports a real CycloneDX 1.6 CBOM report plus a frontend-friendly summary.
A CLI entrypoint (`python -m ecdat_core.cli scan <path>`) ties the pipeline
together, and an end-to-end test scans a mixed-language `demo_repo` fixture to
prove critical and quantum-safe outcomes flow through to a structurally valid
CBOM. The full suite stands at 92 passing tests (2 network-gated tests
deselected by default).

| Phase | Description | Status | Commit | Notes |
|-------|-------------|--------|--------|-------|
| 0: Repo scaffold | Initialize git repo, create project structure, AGENTS.md, progress.md | Done | 68505bd | 2026-09-08 |
| 1: CBOM-aligned Pydantic data models | Detection, RiskAssessment, Recommendation, ScanResult with validators | Done | 83fc732 | 2026-09-08 |
| 2: Cryptographic signature knowledge base | signatures.json + signature_loader.py with Pydantic validation + pytest | Done | 0fd0e9b | 2026-09-08 |
| 3: Regex-based detection engine | detector.py (scan_file_content + detect_language) + detector tests (47 passing) | Done | 09b8f0e | 2026-09-08 |
| 4: Repo and manifest ingestion | ingestion.py (ingest_local_directory, ingest_git_url, ingest_manifest_dependencies) + ingestion tests (62 passing) | Done | 7d721a2 | 2026-09-08 |
| 5: Mosca's algorithm risk engine | risk_engine.py (assess_risk with X/Y/Z heuristics, urgency ratio, risk levels) + 5 risk-engine tests (67 passing) | Done | de96e53 | 2026-09-08 |
| 6: PQC recommendation engine | recommender.py (recommend pass-through of pqc_recommendation + "no migration needed" for existing PQC) + 3 recommender tests (70 passing) | Done | 03204b4 | 2026-09-08 |
| 7: CycloneDX 1.6 CBOM export | cbom_export.py (export_cbom + export_summary) + 18 cbom-export tests (88 passing) | Done | 6871169 | 2026-09-08 |
| 9: Backend scaffold, SQLAlchemy models, Alembic migration | FastAPI app, SQLAlchemy 2.0 ORM models, Alembic migration with ScanRun, DetectionRow, RiskAssessmentRow, RecommendationRow models; health endpoint test | Done |  | Created backend/ project structure, models_orm.py, db.py, main.py, Alembic migration, test_health.py |
| Fix Phase 1 | Split `classically_broken` from `quantum_vulnerable` (required field on every signature entry), replace AES-128 entry with generic AES entry (`min_quantum_safe_key_bits=192`, dynamic per-detection quantum_vulnerable in detector.py), add verified PyCryptodome coverage (RSA/DSA/ECC/AES/DES/3DES/ARC4/MD5/SHA-1/DSS), hashlib.sha1 verified present; 97 tests passing | Done | 3a295c7 | 2026-09-09 |
| Fix Phase 2 | Propagate `classically_broken` onto `Detection` (additive `bool = False` default, no breaking change to existing constructions), set it from `signature_entry.classically_broken` in `scan_file_content`; dynamic per-detection AES `quantum_vulnerable` (min_quantum_safe_key_bits=192 threshold) confirmed already implemented in `_resolve_quantum_vulnerable`; new detector tests lock AES-128 → vulnerable, AES-256 → detection produced + quantum-safe, bare AES → conservative fallback with key_size None, MD5 → classically_broken, PyCryptodome `from Crypto.PublicKey import RSA` import (previously non-matching per Phase 3); verified no AES over-matching of words containing "aes"; 99 tests passing | Done | 65c55a6 | 2026-09-09 |
| Fix Phase 3 | `assess_risk()` branch order per AGENTS.md: new first branch for `classically_broken` → always `risk_level="critical"` + `mosca_violation=True` with the naive `(X+Y)/Z` urgency ratio floored at 1.0 (X/Y/Z still computed via normal heuristics for transparency; Pydantic consistency validator holds since floored ratio is exactly >= 1.0); quantum-safe short-circuit now only reachable when `classically_broken` is False, so MD5/DES/3DES/RC4/SHA-1 are never mislabelled "quantum-safe" (demo_repo MD5×5 + DES now critical vs previously quantum-safe; summary went critical 1→7, quantum-safe 10 unchanged). Note: no `signatures.json` entry behavior changed — the misclassification was purely a risk-engine branch-order bug. Two new risk-engine tests: classically_broken MD5-like → critical/mosca_violation/urgency≥1.0 with floor demonstrated (naive 0.275 floored to 1.0), and genuinely quantum-safe AES-256 still short-circuits to "quantum-safe". Full suite: 101 passing (2 network deselect), up from 99 | Done | b10a424 | 2026-09-09 |
| Fix Phase 4 | CBOM export property `ecdat:classicallyBroken` added to `export_cbom()` populated from each Detection's `classically_broken` field; CLI scan re-validated: RSA-1024 critical (Mosca), MD5 and DES critical (classically broken), AES-256 quantum-safe; end-to-end test updated to assert at least 2 distinct critical detections with differing `classically_broken` values, preventing silent regression | Done | bad4920c039923b8322b76313fac44943df44add | 2026-09-09 |

### Batch 1 — Fix Pass

- CBOM export now includes `ecdat:classicallyBroken` property populated from each Detection's `classically_broken` field (Part A)
- CLI scan against demo_repo correctly flags RSA-1024 as critical (Mosca violation), MD5 and DES as critical (classically broken), and AES-256 as quantum-safe (Part B)
- End-to-end test asserts at least 2 distinct critical detections with differing `classically_broken` values, preventing silent regression (Part C)

### CLI Summary (corrected output)

```
$ python -m ecdat_core.cli scan /home/pratyay/Documents/My Codes/ECDAT/ecdat_core/tests/fixtures/demo_repo

wrote cbom.json
wrote summary.json

Scan target : /home/pratyay/Documents/My Codes/ECDAT/ecdat_core/tests/fixtures/demo_repo
Files scanned: 4
Detections  : 17
--------------------------------
Risk level       Count
--------------------------------
critical             7
high                 0
medium               0
low                  0
quantum-safe        10
--------------------------------
```

### Phase 8 — CLI run against `fixtures/demo_repo`

```
$ python -m ecdat_core.cli scan ecdat_core/tests/fixtures/demo_repo

wrote cbom.json
wrote summary.json

Scan target : .../ecdat_core/tests/fixtures/demo_repo
Files scanned: 4
Detections  : 17
--------------------------------
Risk level       Count
--------------------------------
critical             7
high                 0
medium               0
low                  0
quantum-safe        10
--------------------------------
```