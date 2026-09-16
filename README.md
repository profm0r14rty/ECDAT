# ecdat_core

The scanner engine behind
[ECDAT](https://github.com/profm0r14rty/ecdat) — a Cryptography Bill of
Materials (CBOM) scanner for post-quantum readiness assessment.

> **Placeholder.** This file is a minimal stub so the PyPI package metadata
> can build in Phase 51. The full package-scoped README — install, API
> reference, and the scanner-specific usage examples — lands in Phase 52.

## Install

```bash
pip install ecdat-cbom
```

## Use

```python
from ecdat_core.cli import run_scan

result = run_scan("/path/to/repo")
print(result.files_scanned, len(result.detections))
```

## What you get

A `.docs`-free, dependency-light engine (`pydantic>=2` only — no FastAPI,
no Postgres, no Redis) that:

- discovers cryptographic artefacts in source code via regex signatures
  loaded from a JSON knowledge base,
- scores each artefact's post-quantum risk via Mosca's inequality
  (`X + Y > Z`),
- recommends NIST post-quantum replacements (ML-KEM, ML-DSA, SLH-DSA), and
- emits a real CycloneDX 1.6 CBOM validated against the official schema.

See the [main README](https://github.com/profm0r14rty/ecdat) for the
end-to-end project overview, security model, and CBOM output standard.
