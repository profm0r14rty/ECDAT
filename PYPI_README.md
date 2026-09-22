# ecdat

[![PyPI](https://img.shields.io/pypi/v/ecdat?color=3ddc97&label=PyPI)](https://pypi.org/project/ecdat/)
[![Python](https://img.shields.io/pypi/pyversions/ecdat?color=3ddc97)](https://pypi.org/project/ecdat/)
[![Downloads](https://img.shields.io/pypi/dm/ecdat?color=3ddc97&label=downloads)](https://pypi.org/project/ecdat/)
[![License: MIT](https://img.shields.io/github/license/profm0r14rty/ECDAT?color=3ddc97)](https://github.com/profm0r14rty/ECDAT/blob/main/LICENSE)
[![SIH 2026](https://img.shields.io/badge/SIH%202026-Winner%20🏆-gold)](https://github.com/profm0r14rty/ECDAT)

**ECDAT** is a [CycloneDX](https://cyclonedx.org/) **Cryptography Bill of
Materials (CBOM) scanner for post-quantum readiness**. One command finds the
cryptographic artefacts in a codebase — RSA, ECC, DH, DSA, MD5, SHA-1, DES,
3DES, RC4, AES, and others — scores each one's post-quantum risk with Mosca's
inequality, recommends NIST post-quantum replacements, and emits a real
CycloneDX 1.6 CBOM next to a dashboard-friendly risk summary.

It is a small, self-contained Python package (runtime dependencies: `pydantic`
and `rich`) — no FastAPI, Postgres, Redis, or Docker required. It runs fully
offline: the only network access is `git clone` for an explicit URL scan.

Why it is more than a lookalike scanner:

- **Real CBOM output.** The report is genuine CycloneDX 1.6, validated against
  the official JSON Schema on every scan in the test suite, so Dependency-Track,
  Syft, Grype, and other CycloneDX tooling parse it unchanged.
- **"Classically broken" is not "quantum vulnerable".** MD5, SHA-1, DES, 3DES,
  and RC4 are reported as broken *today*; RSA, ECC, DH, and DSA as broken *by
  Shor's algorithm*. An actively exploitable hash is never mislabeled
  "quantum-safe".
- **Offline and private.** No telemetry, no update checks.
- **Crash-safe.** Expected errors print a clear message and exit code;
  unexpected errors are written to a local crash log instead of a raw
  traceback.

## Install

```bash
pipx install ecdat        # recommended: isolated and on PATH
uv tool install ecdat     # recommended if you use uv
pip install ecdat         # into the active Python environment
```

If plain `pip` reports `externally-managed-environment`, that is
[PEP 668](https://peps.python.org/pep-0668/) protecting your OS Python — use
`pipx` or `uv tool` (or a virtualenv) instead of forcing the install. On
Windows, install with `py -m pip install ecdat`; if `ecdat` is not on `PATH`,
run the CLI as `py -m ecdat …`.

## 60-second tour

```bash
ecdat demo                                   # scan the bundled sample project
ecdat scan .                                 # scan the current directory
ecdat scan https://github.com/<user>/<repo>  # scan a public https:// repo
ecdat about                                  # credits and an animated 3D globe
ecdat doctor                                 # check your environment
```

## Commands

| Command | Description |
|---------|-------------|
| `ecdat scan <path-or-url>` | Scan a local directory, or an `https://` Git repository |
| `ecdat demo` | Scan the bundled, deliberately-insecure sample project (zero setup) |
| `ecdat doctor` | Environment self-check with a one-line fix per problem |
| `ecdat about` | Credits, project links, and a spinning 3D globe |
| `ecdat help [command]` | Command overview, or full help for one command |
| `ecdat version` | Version, engine, signature count, Python, and OS |

Global flags: `--version`, `--no-color`, and `--debug`.

## Formats

`ecdat scan --format <pretty|json|cbom|summary>`:

| Format | Contents |
|--------|----------|
| `pretty` | Colourised terminal report (default) |
| `json` | The full `ScanResult` |
| `cbom` | A CycloneDX 1.6 CBOM |
| `summary` | The risk rollup used by dashboards |

Payload formats write **only** the payload to stdout; progress, warnings, and
errors go to stderr — so `ecdat scan . -f cbom > cbom.json` is safe to pipe.
`ecdat demo` supports `pretty`, `json`, and `summary`.

For CI, `ecdat scan . --fail-on high` exits `1` when a finding is at or above
that level (`quantum-safe` findings never count) and `0` when clean. The other
exit codes are `2` (usage/validation error), `3` (scan/runtime/unexpected
error), and `130` (interrupted with `Ctrl-C`).

## Guarantees

- **Offline by default.** Only `git clone` for an explicit `https://` URL scan
  touches the network; local scans never do.
- **No telemetry and no update checks.**
- **Injection-safe rendering.** File paths, matched snippets, and algorithm
  names from scanned (untrusted) code are rendered as plain text and cannot
  inject terminal escapes or Rich/HTML/Markdown markup.
- **Validated Git-URL scanning.** Only `https://` URLs are cloned, and the host
  is resolved and checked against private/reserved address ranges before any
  clone runs.

## Links

- Source, issues, and documentation: <https://github.com/profm0r14rty/ecdat>
- Security policy: <https://github.com/profm0r14rty/ecdat/blob/main/SECURITY.md>
- Changelog: <https://github.com/profm0r14rty/ecdat/blob/main/CHANGELOG.md>
- Live demo dashboard: <https://ecdat-web.onrender.com>
- Live demo API: <https://ecdat-api.onrender.com>
- License (MIT): <https://github.com/profm0r14rty/ecdat/blob/main/LICENSE>
