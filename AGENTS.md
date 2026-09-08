# ECDAT - Enterprise Cryptographic Discovery & Analysis Tool

## Project Purpose (one paragraph)
ECDAT is a Cryptography Bill of Materials (CBOM) scanner for post-quantum readiness assessment. It discovers cryptographic artefacts in source code, assesses their quantum-computing risk using Mosca's algorithm, and recommends NIST post-quantum replacements, outputting a CycloneDX 1.6 CBOM report.

## Tech Stack
- **Python 3.12 scanner core** (ecdat_core, stdlib regex-based detection, zero web deps)
- **FastAPI backend** (Batch 2)
- **React+Vite+TS+Tailwind frontend** (Batch 3)
- **Postgres+Redis** (Batch 2+)
- **Docker Compose** (Batch 2+)

## Output Standard
- **CycloneDX 1.6 CBOM JSON**
- Component type: `cryptographic-asset`
- `cryptoProperties.assetType` in `[algorithm, certificate, protocol, related-crypto-material]`
- Never invent a custom JSON schema — always target real CycloneDX 1.6 field names

## Risk Model
- **Mosca's inequality**: X (migration time) + Y (shelf-life) > Z (quantum threat horizon) means at-risk
- **Continuous urgency_ratio** = (X+Y)/Z
- **Risk level thresholds**:
  - >=1.0 critical
  - 0.8-1.0 high
  - 0.5-0.8 medium
  - <0.5 low
  - non-quantum-vulnerable = quantum-safe

## Coding Conventions
- Type-hinted Python
- Pydantic v2 models
- pytest for all new logic
- Small single-purpose functions
- Docstrings on every public function

## Workflow
- Work is broken into numbered phases
- After each phase: run tests, update progress.md, commit with message "Phase N: <description>"