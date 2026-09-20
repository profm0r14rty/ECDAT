# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-09-21


### Added

- **New `ecdat` command-line interface.** A pip-installable, terminal-native
  front end for the scanner, with subcommands:
  - `ecdat scan <path-or-url>` — scan a local directory or an `https://` Git
    repository, with `--format pretty|json|cbom|summary`, `--output DIR`,
    `--fail-on critical|high|medium|low`, `--limit N`, `--no-progress`,
    `--quiet`, and `--git-url`.
  - `ecdat demo` — scan the bundled, deliberately-insecure sample project with
    zero setup (and `--path` to materialise a persistent copy).
  - `ecdat doctor` — environment self-check (Python, platform, install
    location, git, terminal, signatures, `ECDAT_HOME`) with a one-line fix per
    failing check.
  - `ecdat about` — credits, project links, and an animated 3D globe.
  - `ecdat help [command]` — command overview and per-command help.
  - `ecdat version` — version, engine, signature count, Python, and OS.
  - Global flags `--version`, `--no-color`, and `--debug`.
- **Gradient ASCII banner** shown on interactive runs.
- **Animated 3D globe** in `ecdat about` (opt-out with `--no-anim`, duration
  controlled by `--spin`).
- **Padlock verdict emblem** in the pretty scan report.
- **Bundled demo project** (`ecdat/demo_project/`) shipped inside the wheel, so
  `ecdat demo` works with no repository checkout.
- **Crash-safe error handling.** Expected errors print a friendly message and a
  documented exit code; unexpected errors are written to a local crash log
  under `ECDAT_HOME/logs` with a pointer for bug reports, instead of a raw
  traceback.
- **Documented exit codes** for scripting and CI: `0` success, `1` findings at
  or above `--fail-on`, `2` usage/validation error, `3` scan/runtime/unexpected
  error, `130` interrupted (`Ctrl-C`).
- `CHANGELOG.md` and `PYPI_README.md`, and a `[project.scripts]` console entry
  point (`ecdat = "ecdat.cli:main"`).

### Changed

- **Distribution renamed to `ecdat`** (previously `ecdat-cbom`). A single wheel
  now ships both import packages: the new app layer (`ecdat`) and the scanner
  engine (`ecdat_core`). `python -m ecdat` behaves identically to the console
  script; the legacy `python -m ecdat_core.cli` entry point is unchanged.
- **Engine: `run_scan()` gained a `sandboxed=` parameter.** Callers can opt a
  trusted local scan out of the workspace sandbox (the CLI and TUI do this — the
  user is the trust boundary), while the HTTP API keeps the sandbox enabled.
- Runtime dependency on `rich` added for the CLI/TUI renderers.

### Security

- CLI renderers treat scanned repository content (file paths, snippets,
  algorithm names) as untrusted and render it as plain text, so it cannot
  inject terminal escapes or Rich/HTML/Markdown markup.
