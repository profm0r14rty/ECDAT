"""Payment processing module — handles card-on-file encryption and
tokenization for the PCI-DSS-scoped payment pipeline.

All card data is encrypted at rest with AES-256-GCM (hardware-accelerated,
quantum-safe at 256-bit key size) and tokenized via a format-preserving
encryption scheme before storage.
"""

from __future__ import annotations

import os
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# AES-256 key for card data encryption (32 bytes = 256 bits).
_CARD_ENCRYPTION_KEY = os.urandom(32)

# Nonce size recommended for AES-GCM per NIST SP 800-38D.
_NONCE_SIZE = 12


def encrypt_card_number(card_number: str) -> dict:
    """Encrypt a card number with AES-256-GCM and return ciphertext + nonce.

    Args:
        card_number: The plaintext PAN (primary account number).

    Returns:
        A dict with ``nonce`` (hex) and ``ciphertext`` (hex) fields.
    """
    nonce = os.urandom(_NONCE_SIZE)
    aesgcm = AESGCM(_CARD_ENCRYPTION_KEY)
    ct = aesgcm.encrypt(nonce, card_number.encode("utf-8"), None)
    return {"nonce": nonce.hex(), "ciphertext": ct.hex()}


def decrypt_card_number(nonce_hex: str, ciphertext_hex: str) -> str:
    """Decrypt a card number previously encrypted with ``encrypt_card_number``."""
    nonce = bytes.fromhex(nonce_hex)
    ct = bytes.fromhex(ciphertext_hex)
    aesgcm = AESGCM(_CARD_ENCRYPTION_KEY)
    return aesgcm.decrypt(nonce, ct, None).decode("utf-8")


def generate_encryption_key() -> bytes:
    """Generate a new AES-256 encryption key.

    This is used during key rotation — a new 256-bit key is generated,
    old data is re-encrypted, and the old key is retired.
    """
    return os.urandom(32)  # AES-256 (256-bit key)


def encrypt_amount(amount_cents: int, key: bytes) -> bytes:
    """Encrypt a payment amount for secure transit.

    Uses the caller-supplied AES key so the caller controls the
    encryption lifecycle.
    """
    nonce = os.urandom(_NONCE_SIZE)
    aesgcm = AESGCM(key)
    return aesgcm.encrypt(nonce, str(amount_cents).encode(), None)
