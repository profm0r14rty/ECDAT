"""Optional single-tier API-key authentication gate for the HTTP API.

Controlled by two environment variables, read **per request** (in the
dependency, not at import time) so the gate can be flipped without a process
restart and tests can toggle it on the same app instance:

- ``REQUIRE_API_KEY`` — ``"true"`` (case-insensitive) enables the gate;
  anything else, including unset, disables it and every endpoint behaves
  exactly as before.
- ``API_KEYS`` — comma-separated list of valid keys. Only consulted when the
  gate is enabled.

When enabled, every route carrying :func:`require_api_key` as a dependency
rejects requests whose ``Authorization: Bearer <key>`` header is missing or
whose key is not in ``API_KEYS`` with ``401`` and a
``WWW-Authenticate: Bearer`` response header. Keys are compared in constant
time via :func:`secrets.compare_digest`. Failing closed when the gate is on
but no key is configured (500 with a clear message) is deliberate: a
misconfigured "protected" API must never silently become an open one.
"""

from __future__ import annotations

import os
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# auto_error=False so a missing/malformed header surfaces as ``None``
# (credentials below) instead of FastAPI's own 403 — the gate must emit its
# own 401 per the phase contract.
_bearer_scheme = HTTPBearer(auto_error=False)


def _parse_api_keys(raw: str | None) -> list[str]:
    """Split a comma-separated ``API_KEYS`` value into non-empty, trimmed keys.

    Args:
        raw: The raw ``API_KEYS`` env value, or ``None`` when unset.

    Returns:
        The individual keys with surrounding whitespace stripped; empty and
        all-whitespace entries are dropped (``"a, , b"`` -> ``["a", "b"]``).
    """
    return [key.strip() for key in (raw or "").split(",") if key.strip()]


def require_api_key(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ],
) -> None:
    """FastAPI dependency: gate an endpoint behind a Bearer API key.

    With ``REQUIRE_API_KEY`` unset or not ``"true"`` the dependency is a
    no-op and every request passes through untouched. When enabled it
    requires an ``Authorization: Bearer <key>`` header whose key appears in
    the comma-separated ``API_KEYS`` env var.

    Args:
        credentials: The parsed ``Authorization`` header, or ``None`` when
            the header is absent or not a ``Bearer`` token
            (``HTTPBearer(auto_error=False)``).

    Raises:
        HTTPException: 401 for a missing or invalid key; 500 when the gate
            is enabled but ``API_KEYS`` is empty or unset.
    """
    if os.environ.get("REQUIRE_API_KEY", "false").strip().lower() != "true":
        return

    valid_keys = _parse_api_keys(os.environ.get("API_KEYS"))
    if not valid_keys:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "REQUIRE_API_KEY=true but API_KEYS is empty or unset; "
                "refusing to serve unauthenticated requests"
            ),
        )

    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    supplied = credentials.credentials.strip()
    if not supplied or not any(
        secrets.compare_digest(supplied, key) for key in valid_keys
    ):
        raise unauthorized