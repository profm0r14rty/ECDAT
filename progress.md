# ECDAT Project Progress

| Phase | Description | Status | Commit | Notes |
|-------|-------------|--------|--------|-------|
| 0: Repo scaffold | Initialize git repo, create project structure, AGENTS.md, progress.md | Done | 68505bd | 2026-09-08 |
| 1: CBOM-aligned Pydantic data models | Detection, RiskAssessment, Recommendation, ScanResult with validators | Done | 83fc732 | 2026-09-08 |
| 2: Cryptographic signature knowledge base | signatures.json + signature_loader.py with Pydantic validation + pytest | Done | 0fd0e9b | 2026-09-08 |
| 3: Regex-based detection engine | detector.py (scan_file_content + detect_language) + detector tests (47 passing) | Done | 09b8f0e | 2026-09-08 |
| 4: Repo and manifest ingestion | ingestion.py (ingest_local_directory, ingest_git_url, ingest_manifest_dependencies) + ingestion tests (62 passing) | Done | 7d721a2 | 2026-09-08 |
| 5: Mosca's algorithm risk engine | risk_engine.py (assess_risk with X/Y/Z heuristics, urgency ratio, risk levels) + 5 risk-engine tests (67 passing) | Done | de96e53 | 2026-09-08 |
| 6: PQC recommendation engine | recommender.py (recommend pass-through of pqc_recommendation + "no migration needed" for existing PQC) + 3 recommender tests (70 passing) | Done |  | 2026-09-08 |
| 7: CycloneDX 1.6 CBOM export | cbom_export.py (export_cbom + export_summary) + 18 cbom-export tests (88 passing) | Done |  | 2026-09-08 |