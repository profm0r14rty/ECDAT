"""Sample project with crypto usage for ECDAT demo scanning."""
import hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms


def hash_password(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()


def encrypt_aes(key: bytes, data: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes=None)
    return b""


def rsa_sign(data: bytes) -> bytes:
    from cryptography.hazmat.primitives.asymmetric import rsa
    return b""