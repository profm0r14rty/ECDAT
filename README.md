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

## Full project

This package is the standalone scanner engine. The full ECDAT project — web
dashboard, HTTP API, and Docker / Render deployment story — lives at
<https://github.com/profm0r14rty/ecdat>.

## License

MIT — see <https://github.com/profm0r14rty/ecdat/blob/main/LICENSE>.
