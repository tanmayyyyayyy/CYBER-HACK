from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend import store

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
    salt = blob[offset : offset + SALT_BYTES]
    nonce = blob[offset + SALT_BYTES : header_size]
    try:
        return AESGCM(_derive_key(passphrase, salt)).decrypt(nonce, blob[header_size:], AAD)
    except InvalidTag as exc:
        raise ValueError("Backup authentication failed. Check the passphrase and file integrity.") from exc


def _signing_key() -> bytes:
    store.DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not store.SIGNING_KEY_PATH.is_file():
        key = secrets.token_bytes(32)
        store.SIGNING_KEY_PATH.write_bytes(key)
        try:
            store.SIGNING_KEY_PATH.chmod(0o600)
        except OSError:
            pass
        return key
    return store.SIGNING_KEY_PATH.read_bytes()


def canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    body = {k: v for k, v in manifest.items() if k != "seal"}
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Attach an HMAC-SHA256 workstation seal + payload SHA-256 to an evidence manifest."""
    payload = canonical_manifest_bytes(manifest)
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    signature = hmac.new(_signing_key(), payload, hashlib.sha256).hexdigest()
    return {
        **manifest,
        "seal": {
            "algorithm": "HMAC-SHA256",
            "payloadSha256": payload_sha256,
            "signature": signature,
            "scope": "Local workstation evidence seal; verifies manifest has not been modified after export.",
        },
    }


def verify_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    seal = manifest.get("seal")
    if not isinstance(seal, dict) or not seal.get("signature"):
        return {"verified": False, "reason": "Manifest is missing a cryptographic seal block."}
    payload = canonical_manifest_bytes(manifest)
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    expected_sig = hmac.new(_signing_key(), payload, hashlib.sha256).hexdigest()
    hash_ok = hmac.compare_digest(payload_sha256, str(seal.get("payloadSha256", "")))
    sig_ok = hmac.compare_digest(expected_sig, str(seal.get("signature", "")))
    if not hash_ok:
        return {"verified": False, "payloadSha256": payload_sha256, "reason": "Evidence manifest bytes do not match payload SHA-256 (tampered)."}
    if not sig_ok:
        return {"verified": False, "payloadSha256": payload_sha256, "reason": "HMAC-SHA256 seal does not match this workstation signing key."}
    return {"verified": True, "payloadSha256": payload_sha256, "algorithm": seal.get("algorithm", "HMAC-SHA256")}
