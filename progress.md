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
| 8: CLI entrypoint and end-to-end fixture test | cli.py (run_scan orchestrator + `python -m ecdat_core.cli scan`), demo_repo fixture, test_end_to_end.py (4 e2e tests, 92 total passing), files_scanned field on ScanResult | Done | 0159c82 | 2026-09-08 |
| Fix Phase 1 | Split `classically_broken` from `quantum_vulnerable` (required field on every signature entry), replace AES-128 entry with generic AES entry (`min_quantum_safe_key_bits=192`, dynamic per-detection quantum_vulnerable in detector.py), add verified PyCryptodome coverage (RSA/DSA/ECC/AES/DES/3DES/ARC4/MD5/SHA-1/DSS), hashlib.sha1 verified present; 97 tests passing | Done | 3a295c7 | 2026-09-09 |
| Fix Phase 2 | Propagate `classically_broken` onto `Detection` (additive `bool = False` default, no breaking change to existing constructions), set it from `signature_entry.classically_broken` in `scan_file_content`; dynamic per-detection AES `quantum_vulnerable` (min_quantum_safe_key_bits=192 threshold) confirmed already implemented in `_resolve_quantum_vulnerable`; new detector tests lock AES-128 → vulnerable, AES-256 → detection produced + quantum-safe, bare AES → conservative fallback with key_size None, MD5 → classically_broken, PyCryptodome `from Crypto.PublicKey import RSA` import (previously non-matching per Phase 3); verified no AES over-matching of words containing "aes"; 99 tests passing | Done | 65c55a6 | 2026-09-09 |

### Phase 8 — CLI run against `fixtures/demo_repo`

```
$ python -m ecdat_core.cli scan ecdat_core/tests/fixtures/demo_repo

wrote cbom.json
wrote summary.json

Scan target : .../ecdat_core/tests/fixtures/demo_repo
Files scanned: 4
Detections  : 11
--------------------------------
Risk level       Count
--------------------------------
critical             1
high                 0
medium               0
low                  0
quantum-safe        10
--------------------------------
```