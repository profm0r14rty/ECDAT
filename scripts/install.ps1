# ECDAT installer for Windows (PowerShell 5.1+).
#
# What this script does, in order:
#   1. Installs ECDAT with `uv tool` when uv is present  -  uv gives ECDAT its
#      own Python, sidestepping PEP 668 "externally-managed-environment".
#   2. Otherwise uses pipx, when present, for the same isolation.
#   3. Otherwise installs uv from its official astral.sh installer (the only
#      remote code this script fetches) and uses that.
#   4. Otherwise falls back to `py -m pip install --user`.
#   5. Best-effort adds the tool directory to this session's PATH and verifies
#      the install. No admin rights, no system-wide writes; the only code
#      fetched is uv's official installer.
#
# Configure with environment variables:
#   ECDAT_SPEC   package to install (default: "ecdat"; also accepts a pin such
#                as "ecdat==0.2.0" or a local wheel path  -  CI uses this).
#   ECDAT_NO_UV  set to 1 to forbid this script from installing uv.

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrEmpty($env:ECDAT_SPEC)) { $env:ECDAT_SPEC = "ecdat" }
if ([string]::IsNullOrEmpty($env:ECDAT_NO_UV)) { $env:ECDAT_NO_UV = "0" }
$BinDir = Join-Path $env:USERPROFILE ".local\bin"

function Say([string]$Message) { Write-Host $Message }

# --- 1) uv ----------------------------------------------------------------
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Say "uv found - installing $($env:ECDAT_SPEC) with 'uv tool install'."
    uv tool install --force $env:ECDAT_SPEC
    if ($LASTEXITCODE -ne 0) { Say "Error: 'uv tool install' failed."; exit 1 }

    # --- 2) pipx --------------------------------------------------------------
} elseif (Get-Command pipx -ErrorAction SilentlyContinue) {
    Say "pipx found - installing $($env:ECDAT_SPEC) with 'pipx install'."
    pipx install --force $env:ECDAT_SPEC
    if ($LASTEXITCODE -ne 0) { Say "Error: 'pipx install' failed."; exit 1 }

    # --- 3) install uv, then use it -------------------------------------------
} elseif ($env:ECDAT_NO_UV -ne "1") {
    Say "uv not found - installing uv (https://astral.sh/uv) so ECDAT gets its own Python."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    if ($LASTEXITCODE -ne 0) { Say "Error: the uv installer failed."; exit 1 }
    $env:Path = "$BinDir;$env:Path"
    Say "Installing $($env:ECDAT_SPEC) with 'uv tool install'."
    uv tool install --force $env:ECDAT_SPEC
    if ($LASTEXITCODE -ne 0) { Say "Error: 'uv tool install' failed."; exit 1 }

    # --- 4) pip fallback ------------------------------------------------------
} else {
    Say "Warning: using 'py -m pip install --user'. If pip refuses with"
    Say "'externally-managed-environment' (PEP 668), install uv or pipx instead."
    py -m pip install --user --upgrade $env:ECDAT_SPEC
    if ($LASTEXITCODE -ne 0) { Say "Error: 'py -m pip install' failed."; exit 1 }
}

# --- make the tool visible in this session, best effort -------------------
try {
    if (Get-Command uv -ErrorAction SilentlyContinue) { uv tool update-shell | Out-Null }
    elseif (Get-Command pipx -ErrorAction SilentlyContinue) { pipx ensurepath | Out-Null }
} catch { }
$env:Path = "$BinDir;$env:Path"

# --- verify, best effort (a package without --version/doctor still installs)
Say "Verifying the install (best effort)."
try { ecdat --version | Out-Null } catch { Say "Note: the installed package did not answer a version check." }
try { ecdat doctor | Out-Null } catch { }

Say "Installed. Open a NEW terminal if 'ecdat' isn't found, then try: ecdat demo"
Say "If 'ecdat' is not recognised, run: py -m ecdat demo"
exit 0
