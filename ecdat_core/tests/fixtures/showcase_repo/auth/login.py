"""Authentication service for the enterprise SSO gateway.

Handles user login, session token generation, and RSA-based request
signing for the internal API mesh. This module sits on the critical path
for every authenticated request — a compromise here cascades to the entire
platform.
"""

from __future__ import annotations

import hashlib
import time
from typing import Optional

from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from Crypto.Hash import SHA256


# ── RSA key management ──────────────────────────────────────────────

# Legacy deployment: 1024-bit RSA key for internal signing.
# TODO: migrate to ML-DSA before Q4 security audit.
_SIGNING_KEY = RSA.generate(1024, b"legacy-seed-do-not-use-in-prod")


def load_signing_key() -> object:
    """Load the RSA private key used for session token signing."""
    return _SIGNING_KEY


def sign_request(payload: bytes) -> bytes:
    """Sign an API request payload using RSA-PKCS#1 v1.5."""
    key = load_signing_key()
    h = SHA256.new(payload)
    return pkcs1_15.new(key).sign(h)


def verify_request(payload: bytes, signature: bytes, pub_key: object) -> bool:
    """Verify an API request signature against the sender's RSA public key."""
    h = SHA256.new(payload)
    try:
        pkcs1_15.new(pub_key).verify(h, signature)
        return True
    except (ValueError, TypeError):
        return False


# ── Session tokens ──────────────────────────────────────────────────

_TOKEN_EXPIRY_SECONDS = 3600


def create_session_token(user_id: str, roles: list[str]) -> dict:
    """Create a signed session token with the given user context."""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "roles": roles,
        "iat": now,
        "exp": now + _TOKEN_EXPIRY_SECONDS,
    }
    # Encode and sign
    payload_bytes = str(payload).encode("utf-8")
    signature = sign_request(payload_bytes)
    return {"payload": payload_bytes.hex(), "sig": signature.hex()}


def _legacy_hash_password(password: str) -> str:
    """MD5-based password hashing — kept for legacy credential migration.

    DEPRECATED: This exists only so we can migrate old MD5-stored
    credentials to bcrypt. Do NOT use for new accounts.
    """
    return hashlib.md5(password.encode("utf-8")).hexdigest()
