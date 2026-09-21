"""Post-quantum cryptographic utilities — NIST-standardized algorithms.

This module wraps ML-KEM (FIPS 203) and ML-DSA (FIPS 204) for the
platform's PQC migration path. These are the recommended replacements
for RSA/ECDH/ECDSA in a post-quantum world.
"""

from __future__ import annotations

from ML_KEM import MLKEM768
from ML_DSA import MLDSA65


# ── ML-KEM (Key Encapsulation Mechanism) ─────────────────────────────

def generate_kem_keypair():
    """Generate an ML-KEM-768 key pair for post-quantum key exchange.

    ML-KEM-768 targets NIST security level 3 (~192-bit classical security,
    ~128-bit quantum security). This is the recommended parameter set for
    most applications.
    """
    kem = MLKEM768()
    enc_key, dec_key = kem.generate_key()
    return enc_key, dec_key


def kem_encapsulate(enc_key: bytes) -> tuple[bytes, bytes]:
    """Encapsulate a shared secret under the recipient's ML-KEM public key.

    Returns:
        A (ciphertext, shared_secret) tuple. The ciphertext is sent to
        the recipient; the shared_secret is used for symmetric encryption.
    """
    kem = MLKEM768()
    ct, ss = kem.encapsulate(enc_key)
    return ct, ss


def kem_decapsulate(dec_key: bytes, ciphertext: bytes) -> bytes:
    """Decapsulate a shared secret using the recipient's ML-KEM private key."""
    kem = MLKEM768()
    return kem.decapsulate(dec_key, ciphertext)


# ── ML-DSA (Digital Signature Algorithm) ─────────────────────────────

def generate_signature_keypair():
    """Generate an ML-DSA-65 key pair for post-quantum signatures.

    ML-DSA-65 targets NIST security level 3. Signing is fast;
    verification is slower but still practical for most use cases.
    """
    dsa = MLDSA65()
    return dsa.generate_key()


def sign(message: bytes, private_key: bytes) -> bytes:
    """Sign a message with ML-DSA-65."""
    dsa = MLDSA65()
    return dsa.sign(private_key, message)


def verify(message: bytes, signature: bytes, public_key: bytes) -> bool:
    """Verify an ML-DSA-65 signature."""
    dsa = MLDSA65()
    return dsa.verify(public_key, message, signature)
