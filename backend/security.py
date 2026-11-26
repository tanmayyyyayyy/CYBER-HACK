from __future__ import annotations

import hashlib
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

MAGIC = b"DRISHTI-DB1"
AAD = b"Drishti local SQLite snapshot v1"
SALT_BYTES = 16
NONCE_BYTES = 12


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    return hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)


def encrypt_snapshot(plaintext: bytes, passphrase: str) -> bytes:
    salt = secrets.token_bytes(SALT_BYTES)
    nonce = secrets.token_bytes(NONCE_BYTES)
    key = _derive_key(passphrase, salt)
    return MAGIC + salt + nonce + AESGCM(key).encrypt(nonce, plaintext, AAD)


def decrypt_snapshot(blob: bytes, passphrase: str) -> bytes:
    header_size = len(MAGIC) + SALT_BYTES + NONCE_BYTES
    if len(blob) < header_size + 16 or not blob.startswith(MAGIC):
        raise ValueError("Unsupported or truncated Drishti database backup.")
    offset = len(MAGIC)
    salt = blob[offset:offset + SALT_BYTES]
    nonce = blob[offset + SALT_BYTES:header_size]
    try:
        return AESGCM(_derive_key(passphrase, salt)).decrypt(nonce, blob[header_size:], AAD)
    except InvalidTag as exc:
        raise ValueError("Backup authentication failed. Check the passphrase and file integrity.") from exc
