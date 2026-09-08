"""Demo module using modern post-quantum and industry-standard primitives.

Uses ML-KEM (a NIST-standardized post-quantum KEM) for key encapsulation
and AES-256 for symmetric encryption — both considered quantum-safe.
"""

from __future__ import annotations

import os

MLKEM_PARAMETER_SET = 768  # ML-KEM-768


def generate_quantum_safe_keypair() -> tuple[bytes, bytes]:
    """Return an (encapsulation_key, decapsulation_key) ML-KEM key pair."""
    from cryptography.hazmat.primitives.kem import MLKEM  # type: ignore[import-not-found]

    kem = MLKEM(MLKEM768)
    enc_key, dec_key = kem.generate_key()
    return enc_key, dec_key


def encrypt_payload(payload: bytes) -> tuple[bytes, bytes]:
    """Encrypt a payload with AES-256-GCM using a freshly generated key."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    aes_key = os.urandom(32)  # AES-256 key (32 bytes)
    nonce = os.urandom(12)
    aesgcm = AESGCM(aes_key)
    ciphertext = aesgcm.encrypt(nonce, payload, None)
    return nonce + ciphertext, aes_key
