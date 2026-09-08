"""Demo authentication module.

Uses RSA for signing login tokens. The deliberately small 1024-bit key
models a legacy deployment that should be flagged as critically at risk
by the Mosca risk engine (small RSA keys are breakable with near-term
quantum resources).
"""

from __future__ import annotations

# Legacy RSA signing key — only 1024 bits. Force-migrate this.
RSA_KEY_BITS = 1024


def _load_signing_key() -> object:
    """Return an RSA private key for token signing (DEMO ONLY).

    The key is generated at only 1024 bits — far below the 2048-bit
    minimum — so the Mosca risk engine flags this as critically at risk.
    """
    private_key = RSA.generate(1024, b"demo-random-seed")
    return private_key


def sign_session_token(user_id: str) -> bytes:
    """Sign a login payload with RSA and return a PKCS#1 v1.5 signature."""
    key = _load_signing_key()
    payload = f"session:{user_id}".encode("utf-8")
    return key.sign(payload, "SHA-256")



def sign_session_token(user_id: str) -> bytes:
    """Sign a login payload with RSA and return a PKCS#1 v1.5 signature."""
    key = _load_signing_key()
    payload = f"session:{user_id}".encode("utf-8")
    return key.sign(payload, "SHA-256")
