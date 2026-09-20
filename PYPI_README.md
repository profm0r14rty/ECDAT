# ecdat-cbom

ECDAT is a Cryptography Bill of Materials (CBOM) scanner for post-quantum
readiness assessment. It discovers cryptographic artefacts in source code
(RSA, ECC, DH, DSA, MD5, SHA-1, DES, 3DES, RC4, AES, and others), scores
each one's post-quantum risk using Mosca's inequality, recommends NIST
post-quantum replacements, and emits a real CycloneDX 1.6 CBOM alongside a
dashboard-friendly risk summary.

This package is the standalone scanner engine — a dependency-light library
whose only runtime requirement is `pydantic>=2`. It runs from the command
line or is imported directly; no FastAPI, Postgres, Redis, or Docker needed.

## Install

Published to PyPI — the fastest way to try the scanner is to install it and
point it at a directory:

```bash
pip install ecdat-cbom
```

## CLI

```bash
# Scan a local directory:
ecdat scan /path/to/repo

# Scan a public Git repository (--git-url makes PATH a clone URL):
ecdat scan https://github.com/example/project.git --git-url
```

Writes `cbom.json` (CycloneDX 1.6 CBOM) and `summary.json` to the current
directory, and prints a human-readable risk-level breakdown to stdout. The
classic module invocation still works if you prefer it:

```bash
python -m ecdat_core.cli scan /path/to/repo
```

## Python API

```python
from ecdat_core.cli import run_scan
from ecdat_core.cbom_export import export_cbom, export_summary

# Orchestrate the full pipeline: ingest → detect → assess → recommend.
result = run_scan("/path/to/repo")

print(f"{result.files_scanned} files scanned, {len(result.detections)} detections")

for risk in result.risk_assessments:
    print(risk.detection_id, risk.risk_level, f"urgency={risk.urgency_ratio:.2f}")

# Emit real CycloneDX 1.6 CBOM output (see "Output" below).
cbom = export_cbom(result)         # CycloneDX 1.6 BOM dict
summary = export_summary(result)   # risk-level rollup for dashboards
```

`run_scan` also accepts `is_git_url=True` to shallow-clone and scan a public
`https://` Git repository.

## Output — CycloneDX 1.6 CBOM

The CBOM is a real CycloneDX 1.6 BOM — not a custom format. Every
cryptographic artefact is a component with `type: "cryptographic-asset"`,
and the output validates against the official CycloneDX 1.6 JSON Schema
(vendored in the scanner's test suite and enforced on every scan).

Quantum-risk extensions live under the standard `properties` array with an
`ecdat:` prefix (`ecdat:riskLevel`, `ecdat:quantumVulnerable`,
`ecdat:classicallyBroken`, `ecdat:confidence`,
`ecdat:recommendedAlgorithm`, `ecdat:fipsReference`), so existing CycloneDX
tooling — Dependency-Track, Syft, Grype, and friends — parses the output
without change.

## Why this is more than a hackathon prototype

- **Real CycloneDX 1.6 output, validated against the official schema.** The
  CBOM is not a lookalike JSON blob — it validates against the official
  CycloneDX 1.6 JSON Schema (vendored, and enforced by the scanner's test
  suite), so Dependency-Track, Syft, and other CycloneDX tooling parse it
  unchanged.
- **It distinguishes *classically broken* from *quantum vulnerable*.** The
  common shortcut is to collapse "uses crypto" into a single quantum-risk
  score. ECDAT reports two separate booleans: `classically_broken` (MD5,
  SHA-1, DES, 3DES, RC4 — exploitable today, independent of quantum computers)
  and `quantum_vulnerable` (RSA, ECC, DH, DSA — broken specifically by Shor's
  algorithm). An actively broken hash is therefore never mislabeled
  "quantum-safe".
- **The security posture is documented, not implied.** SSRF controls on
  Git-URL scanning, the local-path sandbox, the optional API-key gate, and
  scan-creation rate limiting are described with their actual mechanisms in
  [SECURITY.md](https://github.com/profm0r14rty/ecdat/blob/main/SECURITY.md).

## Full project

This package is the standalone scanner engine. The full ECDAT project — web
dashboard, HTTP API, and Docker / Render deployment story — lives at
<https://github.com/profm0r14rty/ecdat>.

## License

MIT — see <https://github.com/profm0r14rty/ecdat/blob/main/LICENSE>.
