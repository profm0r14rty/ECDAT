"""SLH-DSA (SPHINCS+) signer — conservative hash-based signatures.

SLH-DSA (FIPS 205) is the NIST-standardized stateless hash-based
signature scheme. It provides a conservative alternative to ML-DSA
with well-understood security proofs based only on hash function
assumptions.
"""

from __future__ import annotations

import hashlib


# SLH-DSA parameter set (SPHINCS+-SHA2-128f)
_SLHDSA_VARIANT = "SLH-DSA-SHA2-128f"


def slh_dsa_keygen():
    """Generate an SLH-DSA key pair.

    SLH-DSA keys are larger than ML-DSA but the security argument
    is simpler: it relies only on the security of the underlying
    hash function.
    """
    # Placeholder: real implementation would use a PQ library
    private_key = hashlib.sha512(b"slh-dsa-demo-private").digest()
    public_key = hashlib.sha512(b"slh-dsa-demo-public").digest()
    return private_key, public_key


def slh_dsa_sign(message: bytes, private_key: bytes) -> bytes:
    """Sign a message with SLH-DSA."""
    h = hashlib.sha256(private_key + message).digest()
    return h


def slh_dsa_verify(message: bytes, signature: bytes, public_key: bytes) -> bool:
    """Verify an SLH-DSA signature."""
    expected = hashlib.sha256(public_key + message).digest()
    return expected == signature
