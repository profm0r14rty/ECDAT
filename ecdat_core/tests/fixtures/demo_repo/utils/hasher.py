"""Demo utility module showing legacy MD5 usage for password hashing."""

from __future__ import annotations

import hashlib


def hash_password(password: str) -> str:
    """Return an MD5 digest of the given password (DEMO ONLY — not secure)."""
    return hashlib.md5(password.encode("utf-8")).hexdigest()


def verify_password(password: str, expected_digest: str) -> bool:
    """Check a plaintext password against a stored MD5 digest."""
    return hash_password(password) == expected_digest
