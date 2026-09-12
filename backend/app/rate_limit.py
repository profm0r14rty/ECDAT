"""Per-client rate limiting for the HTTP API.

Phase 47: ``POST /api/scans`` is the only rate-limited endpoint — scan
creation schedules a background job per request, so it is the abuse surface
worth throttling. The limiter is a :class:`slowapi.Limiter` (a
Starlette/FastAPI wrapper around the ``limits`` library — dependency verified
before adoption: slowapi v0.1.10, published 2026-06, actively maintained, no
known vulnerabilities, native FastAPI support). It is instantiated here and
wired into the app in :mod:`backend.app.main` via ``app.state.limiter`` and a
``RateLimitExceeded`` exception handler.

Client identity (:func:`scan_client_key`) — key-based when auth is in use,
IP-based otherwise:

- When Phase 46's API-key gate is enabled and the request carries a *valid*
  ``Authorization: Bearer <key>``, the client is identified by the SHA-256
  digest of that key. Multiple key holders behind one NAT / shared IP each get
  their own bucket, and rotating a key starts a fresh bucket immediately.
- Otherwise the client is identified by its remote IP (slowapi's
  ``get_remote_address`` — deliberately *not* the X-Forwarded-For-honoring
  ``get_ipaddr``, which would let a client fake its bucket identity by setting
  that header itself). Known limitation, documented: behind Render's single
  reverse proxy every request arrives from the proxy's IP, so IP buckets
  aggregate per proxy until the API-key gate is enabled — the gate is the
  per-client identity of record for hardened deployments.

Configuration (env vars):

- ``SCAN_CREATE_RATE_LIMIT`` — the ``limits`` rate-string applied to
  ``POST /api/scans``; read **per request** (like ``REQUIRE_API_KEY`` /
  ``API_KEYS`` in :mod:`backend.app.security`) so it can be tuned without a
  restart. Default ``"10/hour"``. The spec is also validated at import so a
  garbage value fails the app boot instead of silently disabling the limit
  (slowapi swallows ``ValueError`` from dynamic limit callables — that would
  fail *open*; misconfiguration must be loud).
- ``RATE_LIMIT_STORAGE_URI`` — the ``limits`` storage URI, read once at import
  (the storage backend cannot be swapped per request). Default ``"memory://"``
  — correct for the single-process Render / compose deployment; set a
  ``redis://host:6379/0`` URL only when running multiple uvicorn workers
  behind a load balancer. Redis is deliberately NOT required for the default
  path.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import time

from fastapi import Request, status
from fastapi.responses import JSONResponse
from limits import parse as parse_rate_limit_spec
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend.app.security import parse_api_keys

_DEFAULT_SCAN_CREATE_RATE_LIMIT = "10/hour"
_SCAN_CREATE_RATE_LIMIT_ENV = "SCAN_CREATE_RATE_LIMIT"
_SCAN_STORAGE_URI_ENV = "RATE_LIMIT_STORAGE_URI"


def scan_client_key(request: Request) -> str:
    """The rate-limit identity for a request.

    A valid API key (when the Phase 46 gate is enabled) identifies the client
    by the SHA-256 digest of that key — key holders behind a shared IP get
    separate buckets. Otherwise the client is identified by its remote IP.

    Args:
        request: The incoming request.

    Returns:
        A stable identity string: ``"apikey:<sha256>"`` or ``"ip:<host>"``.
    """
    key_digest = _valid_api_key_digest(request)
    if key_digest is not None:
        return f"apikey:{key_digest}"
    return f"ip:{get_remote_address(request)}"


def _valid_api_key_digest(request: Request) -> str | None:
    """Return the SHA-256 digest of a valid Bearer API key, else ``None``.

    The gate must be enabled (``REQUIRE_API_KEY=true``) and the request's
    ``Authorization: Bearer <key>`` header must carry one of the configured
    ``API_KEYS``. The digest (not the raw secret) is used as the rate-limit
    key so the plaintext never appears in the storage backend.

    Args:
        request: The incoming request.

    Returns:
        The hexdigest of a valid key, or ``None`` when the gate is off, the
        header is missing/malformed, or the key is not authorized.
    """
    if os.environ.get("REQUIRE_API_KEY", "false").strip().lower() != "true":
        return None

    auth_header = request.headers.get("Authorization", "")
    scheme, _, credential = auth_header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    supplied = credential.strip()
    if not supplied or not any(
        secrets.compare_digest(supplied, key)
        for key in parse_api_keys(os.environ.get("API_KEYS"))
    ):
        return None
    return hashlib.sha256(supplied.encode("utf-8")).hexdigest()


def scan_create_limit_spec() -> str:
    """Per-request value of ``SCAN_CREATE_RATE_LIMIT``, validated.

    Returns:
        The current rate-limit spec (default ``"10/hour"`` when the env var is
        unset).

    Raises:
        RuntimeError: When the configured spec is not a valid ``limits``
            rate-string (e.g. ``"banana/garbage"``). ``RuntimeError`` is
            deliberate: slowapi catches ``ValueError`` while evaluating a
            dynamic limit and silently applies *no* limit (fail-open for the
            whole endpoint), so an invalid spec must surface as something that
            propagates — a loud ``500`` on the endpoint.
    """
    raw = os.environ.get(_SCAN_CREATE_RATE_LIMIT_ENV)
    spec = (raw or _DEFAULT_SCAN_CREATE_RATE_LIMIT).strip()
    try:
        parse_rate_limit_spec(spec)
    except ValueError as exc:
        raise RuntimeError(
            f"{_SCAN_CREATE_RATE_LIMIT_ENV}={spec!r} is not a valid "
            f"rate-limit spec (expected e.g. '10/hour' or '3/minute'); "
            f"refusing to serve without an enforced limit"
        ) from exc
    return spec


limiter = Limiter(
    key_func=scan_client_key,
    strategy="fixed-window",
    storage_uri=os.environ.get(_SCAN_STORAGE_URI_ENV, "memory://"),
    headers_enabled=False,
)

# Fail fast at boot on a misconfigured SCAN_CREATE_RATE_LIMIT rather than
# discovering it on the first request.
scan_create_limit_spec()


def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    """``429`` response for an exceeded limit.

    slowapi's stock handler returns a terse ``{"error": ...}`` with no retry
    timing; this one matches the API's ``{"detail": ...}`` error shape and
    adds a ``Retry-After`` header (whole seconds, per RFC 9110) so a throttled
    client knows exactly when the window resets.

    Args:
        request: The request that hit the limit.
        exc: The raised rate-limit exception.

    Returns:
        A ``429`` JSON response with a clear ``detail`` and a ``Retry-After``
        header when the reset time is computable.
    """
    retry_after: str | None = None
    current_limit = getattr(request.state, "view_rate_limit", None)
    app_limiter = getattr(request.app.state, "limiter", None)
    if current_limit is not None and app_limiter is not None:
        try:
            item, args = current_limit
            reset_at = app_limiter.limiter.get_window_stats(item, *args).reset_time
            retry_after = str(max(1, int(reset_at - time.time())))
        except Exception:
            # Never let the 429 itself fail because stats were unavailable.
            retry_after = None
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
        headers={"Retry-After": retry_after} if retry_after is not None else None,
    )