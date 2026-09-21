#!/bin/sh
# ECDAT installer for Linux and macOS.
#
# What this script does, in order:
#   1. Installs ECDAT with `uv tool` when uv is present  -  uv gives ECDAT its
#      own Python, sidestepping PEP 668 "externally-managed-environment".
#   2. Otherwise uses pipx, when present, for the same isolation.
#   3. Otherwise installs uv from its official astral.sh installer (the only
#      remote code this script fetches) and uses that.
#   4. Otherwise falls back to `python3 -m pip install --user`.
#   5. Best-effort adds the tool directory to this shell's PATH and verifies
#      the install. No root, no system-wide writes; the only code fetched is
#      uv's official installer.
#
# Configure with environment variables:
#   ECDAT_SPEC   package to install (default: "ecdat"; also accepts a pin such
#                as "ecdat==0.2.0" or a local wheel path  -  CI uses this).
#   ECDAT_NO_UV  set to 1 to forbid this script from installing uv.

set -eu

ECDAT_SPEC="${ECDAT_SPEC:-ecdat}"
ECDAT_NO_UV="${ECDAT_NO_UV:-0}"
BIN_DIR="$HOME/.local/bin"

say() {
    printf '%s\n' "$1"
}

# --- 1) uv ----------------------------------------------------------------
if command -v uv >/dev/null 2>&1; then
    say "uv found  -  installing $ECDAT_SPEC with 'uv tool install'."
    uv tool install --force "$ECDAT_SPEC"

# --- 2) pipx --------------------------------------------------------------
elif command -v pipx >/dev/null 2>&1; then
    say "pipx found  -  installing $ECDAT_SPEC with 'pipx install'."
    pipx install --force "$ECDAT_SPEC"

# --- 3) install uv, then use it -------------------------------------------
elif [ "$ECDAT_NO_UV" != "1" ]; then
    say "uv not found  -  installing uv (https://astral.sh/uv) so ECDAT gets its own Python."
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        say "Error: neither curl nor wget is available to install uv." >&2
        say "Install uv or pipx first, or set ECDAT_NO_UV=1 to use pip." >&2
        exit 1
    fi
    PATH="$BIN_DIR:$PATH"
    export PATH
    say "Installing $ECDAT_SPEC with 'uv tool install'."
    uv tool install --force "$ECDAT_SPEC"

# --- 4) pip fallback ------------------------------------------------------
else
    say "Warning: using 'python3 -m pip install --user'. If pip refuses with"
    say "'externally-managed-environment' (PEP 668), install uv or pipx instead."
    python3 -m pip install --user --upgrade "$ECDAT_SPEC"
fi

# --- make the tool visible in this shell, best effort ---------------------
if command -v uv >/dev/null 2>&1; then
    uv tool update-shell >/dev/null 2>&1 || true
elif command -v pipx >/dev/null 2>&1; then
    pipx ensurepath >/dev/null 2>&1 || true
fi
PATH="$BIN_DIR:$PATH"
export PATH

# --- verify, best effort (a package without --version/doctor still installs)
say "Verifying the install (best effort)."
ecdat --version 2>/dev/null || ecdat --help >/dev/null 2>&1 || \
    say "Note: the installed package did not answer a version check." >&2
ecdat doctor >/dev/null 2>&1 || true

say "Installed. Open a NEW terminal if 'ecdat' isn't found, then try: ecdat demo"
