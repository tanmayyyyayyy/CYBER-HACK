"""Restore an encrypted Drishti SQLite metadata backup while the app is stopped."""
from __future__ import annotations

import getpass
import os
import sqlite3
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import store
from backend.security import decrypt_snapshot


def previous_database_path(target: Path) -> Path:
    preserved = target.with_name(f"{target.name}.pre-restore")
    if preserved.exists():
        preserved = target.with_name(f"{target.name}.{uuid.uuid4().hex}.pre-restore")
    return preserved


def restore_backup(source: Path, passphrase: str, target: Path | None = None) -> Path:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError("Backup file not found.")
    target = target or store.DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        target.parent.chmod(0o700)
    except OSError:
        pass
    plaintext = decrypt_snapshot(source.read_bytes(), passphrase)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".restore-", suffix=".sqlite3", dir=target.parent, delete=False) as temp:
            temp_name = temp.name
            os.chmod(temp_name, 0o600)
            temp.write(plaintext)
            temp.flush()
            os.fsync(temp.fileno())
        with sqlite3.connect(temp_name) as validation:
            check = validation.execute("PRAGMA quick_check").fetchone()[0]
            if check != "ok":
                raise ValueError("Decrypted SQLite database did not pass quick_check.")
            foreign = validation.execute("PRAGMA foreign_key_check").fetchall()
            if foreign:
                raise ValueError(f"Database has {len(foreign)} foreign-key integrity violation(s).")
        if target.exists():
            preserved = previous_database_path(target)
            os.replace(target, preserved)
            os.chmod(preserved, 0o600)
        os.replace(temp_name, target)
        temp_name = None
        os.chmod(target, 0o600)
        return target
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/restore_database.py /path/to/drishti-db-*.enc")
        return 2
    source = Path(sys.argv[1]).expanduser().resolve()
    passphrase = getpass.getpass("Backup passphrase: ")
    try:
        target = store.DB_PATH
        existed = target.exists()
        preserved = previous_database_path(target)
        result = restore_backup(source, passphrase)
        if existed:
            print(f"Previous database preserved at: {preserved}")
        print(f"Restored metadata database to: {result}")
        print("Media files are not included in this database-only backup. Restore the matching uploads/candidates separately, then run the full evidence integrity check.")
        return 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"Restore stopped safely: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
