# Security

This document describes the security posture of ECDAT's scanner engine
(`ecdat-cbom`) and its HTTP API. It covers mechanisms that are implemented and
shipped. Nothing here is planned or aspirational: where a control is described,
you can point at the code that enforces it.

## Threat model

The scanner ingests two classes of user-controlled input: Git repository URLs
and local filesystem paths. Both can reach the network or the filesystem, so
both are sandboxed by default. When the HTTP API is exposed to untrusted
callers it also supports an optional API-key gate and per-client rate limiting
on scan creation.

## Git URL scanning — SSRF protections

Git-URL scans shell out to `git clone`, which makes the target URL an SSRF
vector. `validate_git_url()` in `ecdat_core/ingestion.py` runs before every
clone and enforces the following.

1. **Scheme restriction.** Only `https://` URLs are accepted. `file://`,
   `git://`, `ssh://`, plain `http://`, and scheme-less strings are rejected
   with a clear message.
2. **Private / reserved IP blocking.** The hostname is resolved via
   `socket.getaddrinfo()` and *every* resolved address is checked against
   Python's `ipaddress` module. Any address flagged `is_private`, `is_loopback`,
   `is_link_local`, `is_reserved`, or `is_multicast` rejects the URL. This
   blocks internal networks, loopback, and cloud metadata endpoints such as
   `169.254.169.254`.
3. **Optional host allowlist.** The `GIT_URL_ALLOWED_HOSTS` environment
   variable (comma-separated hostnames; unset means no restriction) can
   restrict cloning to known Git hosts. The allowlist does **not** bypass the
   IP checks — an allowlisted host that resolves to a private address is still
   rejected.
4. **Size ceiling.** `GIT_URL_MAX_SIZE_MB` (default `200`) sets a post-clone
   size limit. An oversized clone aborts the scan cleanly, removing the
   temporary clone directory first, rather than consuming resources or hanging.

**Known residual risk.** DNS-rebinding (a resolve-then-connect TOCTOU between
the address check and the actual `git clone`) is *not* defended against at this
stage. It is documented and accepted, not silently ignored.

## Local path scanning — workspace sandbox

Every local-path scan target must resolve — symlinks followed via
`os.path.realpath()` — inside `SCAN_WORKSPACE_ROOT` (environment variable).
`validate_local_path()` enforces this.

- The default root is the bundled `ecdat_core/tests/fixtures` directory,
  resolved package-relative so container layouts are covered automatically;
  the stock demo/fixture scans work with zero configuration.
- Violations are rejected with a clear `400` at `POST /api/scans`, and both
  `ingest_local_directory()` and `ingest_manifest_dependencies()` enforce the
  same containment as defense in depth.
- **One sanctioned exemption.** `run_scan()` scans a freshly cloned Git repo
  with `sandboxed=False`. That directory is scanner-created (`tempfile.mkdtemp`,
  mode `0700`, ephemeral) and is never a user-supplied path; the user-supplied
  Git URL has already passed `validate_git_url()`. This exemption is never
  applied to user-supplied paths.
- To scan other directories in a hardened deployment, widen
  `SCAN_WORKSPACE_ROOT` (for example `/app/data`) — never disable the check.

## HTTP API access control — optional API-key gate

The API ships a single-tier Bearer API-key gate, intended as a minimum viable
control for non-demo deployments. It is not a multi-tenant auth system.

- **Off by default.** `REQUIRE_API_KEY` (default `false`) leaves every endpoint
  behaving as before, so the public demo is unaffected.
- Controlled by two environment variables, both read *per request* in
  `require_api_key()` (`backend/app/security.py`), so toggling the gate needs
  no restart: `REQUIRE_API_KEY` and `API_KEYS` (comma-separated).
- When enabled, **every** `/api/scans/*` endpoint — reads as well as writes —
  requires `Authorization: Bearer <key>`. Gating reads too is a deliberate
  decision: the motivating leak is "anyone with the URL can read scan history,
  artefacts, and CBOM exports".
- Missing or invalid keys get a `401` with a `WWW-Authenticate: Bearer`
  challenge. Comparison is constant-time via `secrets.compare_digest()`, so a
  key cannot be recovered by timing.
- The dependency is attached at the router level
  (`dependencies=[Depends(require_api_key)]` on the `APIRouter` in
  `backend/app/routers/scans.py`), so it runs before every handler. An
  unauthenticated caller gets `401`, not `404`, and cannot probe scan
  existence.
- `GET /health` stays open, for health checks and warm-keeping.
- **Fail-closed config error.** `REQUIRE_API_KEY=true` with an empty/unset
  `API_KEYS` returns `500` with a clear message. A misconfigured "protected"
  API never silently becomes an open one.

Generate keys out of band; never commit real values:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Bundled dashboard caveat.** The bundled frontend API client
(`frontend/src/api/client.ts`) sends no `Authorization` header by design, so
enabling the gate also blocks the dashboard's `/api/scans` calls. A non-demo
deployment uses API-keyed clients or terminates the key at a same-origin proxy.

## Rate limiting — scan creation

`POST /api/scans` is throttled per client via slowapi
(`backend/app/rate_limit.py`). Only scan creation is limited; other endpoints
are not.

- **Identity.** Key-based when `REQUIRE_API_KEY=true` and a valid key is
  presented (bucketed as `apikey:<sha256(key)>`, so many keys cannot be
  combined into one shared bucket); IP-based otherwise. The IP bucket uses
  `get_remote_address` deliberately, **not** `X-Forwarded-For`, so the bucket
  cannot be spoofed. Consequence: a single-worker deployment behind a proxy
  buckets all clients together until the key gate is enabled.
- **Configuration.** `SCAN_CREATE_RATE_LIMIT` (default `10/hour`, in limits'
  `"N/unit"` format) is read per request; `RATE_LIMIT_STORAGE_URI` (default
  `memory://`; use `redis://...` only for multi-worker deployments sharing one
  bucket) is read once at import.
- **Behavior.** An exceeded limit returns `429` with
  `{"detail": "Rate limit exceeded: <spec>"}` and a `Retry-After` header
  computed from the storage window's reset time. The check runs inside the
  endpoint wrapper, so `422` schema-validation failures and `401` auth
  failures happen first and never consume the bucket.
- **Fail-closed config error.** An invalid limit spec raises `RuntimeError` at
  import (surfacing as `500`) rather than failing open. slowapi swallows
  `ValueError` from dynamic-limit callables and would otherwise stop limiting
  silently, so `backend/app/rate_limit.py` raises `RuntimeError` instead.

## Output validation — CycloneDX 1.6

Every CBOM produced by `export_cbom()` is validated against the official
CycloneDX 1.6 JSON Schema (vendored at `ecdat_core/tests/fixtures/cyclonedx/`)
by the test suite in `ecdat_core/tests/test_cbom_schema.py`, so schema
conformance is a checked property of the scanner's output rather than a
convention. ECDAT never invents custom top-level fields; anything CycloneDX
1.6 has no slot for is emitted under the standard `properties` array with an
`ecdat:` prefix.

## Reporting a vulnerability

If you find a security issue, please don't open a public issue containing
exploit details. Open a private GitHub security advisory at
<https://github.com/profm0r14rty/ecdat/security/advisories/new>, including what
you did, what you expected, and what happened. This is a hackathon-origin
project without a formal SLA, but reports are read and addressed as time
allows.
