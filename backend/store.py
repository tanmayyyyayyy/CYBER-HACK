from __future__ import annotations

import json
import hashlib
import contextvars
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("DRISHTI_DATA_DIR", ROOT / "backend" / "data")).resolve()
UPLOADS = DATA / "uploads"
CANDIDATES = DATA / "candidates"
BACKUPS = DATA / "backups"
DB_PATH = DATA / "drishti.sqlite3"
AUDIT_ACTOR: contextvars.ContextVar[str] = contextvars.ContextVar("drishti_audit_actor", default="")


def connect() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    UPLOADS.mkdir(parents=True, exist_ok=True, mode=0o700)
    CANDIDATES.mkdir(parents=True, exist_ok=True, mode=0o700)
    BACKUPS.mkdir(parents=True, exist_ok=True, mode=0o700)
    for directory in (DATA, UPLOADS, CANDIDATES, BACKUPS):
        try:
            directory.chmod(0o700)
        except OSError:
            pass
    db = sqlite3.connect(DB_PATH, timeout=20)
    try:
        DB_PATH.chmod(0o600)
    except OSError:
        pass
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 20000")
    db.execute("PRAGMA secure_delete = ON")
    return db


def init_db() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS clips (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                camera_id TEXT NOT NULL DEFAULT 'ATM-01',
                path TEXT NOT NULL,
                source_path TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                duration REAL NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                fps REAL NOT NULL,
                codec TEXT NOT NULL DEFAULT 'unknown',
                playback_codec TEXT NOT NULL DEFAULT 'unknown',
                preview_ready INTEGER NOT NULL DEFAULT 1,
                sha256 TEXT NOT NULL,
                analysis_sha256 TEXT NOT NULL,
                uploaded_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                clip_id TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
                transaction_time TEXT NOT NULL,
                time_mode TEXT NOT NULL DEFAULT 'clip',
                clip_start_time TEXT NOT NULL DEFAULT '',
                transaction_ref TEXT NOT NULL DEFAULT '',
                window_seconds INTEGER NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT NOT NULL DEFAULT '{}',
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS candidates (
                id TEXT PRIMARY KEY,
                analysis_id TEXT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
                clip_id TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
                frame_seconds REAL NOT NULL,
                track_id INTEGER NOT NULL,
                score REAL NOT NULL,
                sharpness REAL NOT NULL,
                illumination REAL NOT NULL,
                face_size REAL NOT NULL,
                pose REAL NOT NULL,
                confidence REAL NOT NULL,
                flags_json TEXT NOT NULL DEFAULT '[]',
                image_path TEXT NOT NULL,
                descriptor_json TEXT NOT NULL,
                review_status TEXT NOT NULL DEFAULT 'unreviewed',
                note TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                analysis_id TEXT,
                clip_id TEXT,
                kind TEXT NOT NULL,
                message TEXT NOT NULL,
                severity TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                details_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                subject_id TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                occurred_at TEXT NOT NULL,
                previous_hash TEXT NOT NULL DEFAULT '',
                entry_hash TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'investigator',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                approved_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                csrf_token TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
            CREATE TABLE IF NOT EXISTS auth_attempts (
                identifier_hash TEXT NOT NULL,
                attempted_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS security_backups (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL UNIQUE,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS security_evidence_checks (
                id TEXT PRIMARY KEY,
                checked_by TEXT NOT NULL,
                checked_at TEXT NOT NULL,
                clips_checked INTEGER NOT NULL,
                mismatch_count INTEGER NOT NULL,
                details_json TEXT NOT NULL DEFAULT '[]'
            );
            CREATE INDEX IF NOT EXISTS idx_security_checks_time ON security_evidence_checks(checked_at DESC);
            CREATE INDEX IF NOT EXISTS idx_security_backups_time ON security_backups(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_analyses_created ON analyses(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_candidates_analysis ON candidates(analysis_id, score DESC);
            CREATE INDEX IF NOT EXISTS idx_events_time ON events(occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_log(occurred_at DESC);
            """
        )
        columns = {row[1] for row in db.execute("PRAGMA table_info(clips)")}
        migrations = {
            "source_path": "ALTER TABLE clips ADD COLUMN source_path TEXT NOT NULL DEFAULT ''",
            "sha256": "ALTER TABLE clips ADD COLUMN sha256 TEXT NOT NULL DEFAULT ''",
            "analysis_sha256": "ALTER TABLE clips ADD COLUMN analysis_sha256 TEXT NOT NULL DEFAULT ''",
        }
        for column, statement in migrations.items():
            if column not in columns:
                db.execute(statement)
        clip_columns = {row[1] for row in db.execute("PRAGMA table_info(clips)")}
        if "playback_codec" not in clip_columns:
            db.execute("ALTER TABLE clips ADD COLUMN playback_codec TEXT NOT NULL DEFAULT 'unknown'")
        if "preview_ready" not in clip_columns:
            db.execute("ALTER TABLE clips ADD COLUMN preview_ready INTEGER NOT NULL DEFAULT 1")
        audit_columns = {row[1] for row in db.execute("PRAGMA table_info(audit_log)")}
        if "previous_hash" not in audit_columns:
            db.execute("ALTER TABLE audit_log ADD COLUMN previous_hash TEXT NOT NULL DEFAULT ''")
        if "entry_hash" not in audit_columns:
            db.execute("ALTER TABLE audit_log ADD COLUMN entry_hash TEXT NOT NULL DEFAULT ''")
        attempt_columns = {row[1] for row in db.execute("PRAGMA table_info(auth_attempts)")}
        if "identifier_hash" not in attempt_columns:
            old_attempts = db.execute("SELECT email,attempted_at FROM auth_attempts").fetchall()
            db.execute("ALTER TABLE auth_attempts RENAME TO auth_attempts_legacy")
            db.execute("CREATE TABLE auth_attempts(identifier_hash TEXT NOT NULL,attempted_at TEXT NOT NULL)")
            db.executemany("INSERT INTO auth_attempts(identifier_hash,attempted_at) VALUES(?,?)",
                           [(hashlib.sha256(str(row["email"]).strip().lower().encode()).hexdigest(), row["attempted_at"])
                            for row in old_attempts])
            db.execute("DROP TABLE auth_attempts_legacy")
        db.execute("CREATE INDEX IF NOT EXISTS idx_auth_attempts_time ON auth_attempts(identifier_hash,attempted_at)")
        # Existing records are chained once during migration; new records use append_audit().
        previous_hash = ""
        for row in db.execute("SELECT * FROM audit_log ORDER BY rowid").fetchall():
            if row["entry_hash"]:
                previous_hash = row["entry_hash"]
                continue
            entry_hash = audit_digest(row["id"], row["action"], row["subject_id"], row["note"], row["occurred_at"], previous_hash)
            db.execute("UPDATE audit_log SET previous_hash=?,entry_hash=? WHERE id=?",
                       (previous_hash, entry_hash, row["id"]))
            previous_hash = entry_hash
        # Upgrade older local prototype records in place without discarding footage.
        for row in db.execute("SELECT id,path,source_path,sha256,analysis_sha256 FROM clips").fetchall():
            source_path = row["source_path"] or row["path"]
            try:
                hasher = hashlib.sha256()
                with Path(source_path).open("rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        hasher.update(chunk)
                digest = hasher.hexdigest()
            except OSError:
                digest = ""
            db.execute("""UPDATE clips SET source_path=?,sha256=CASE WHEN sha256='' THEN ? ELSE sha256 END,
                         analysis_sha256=CASE WHEN analysis_sha256='' THEN ? ELSE analysis_sha256 END WHERE id=?""",
                       (source_path, digest, digest, row["id"]))


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def json_load(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def audit_digest(entry_id: str, action: str, subject_id: str, note: str, occurred_at: str, previous_hash: str) -> str:
    payload = json.dumps(
        {"id": entry_id, "action": action, "subject_id": subject_id, "note": note,
         "occurred_at": occurred_at, "previous_hash": previous_hash},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def append_audit(db: sqlite3.Connection, action: str, subject_id: str, note: str, occurred_at: str | None = None,
                 actor_id: str | None = None) -> str:
    stamp = occurred_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    actor = actor_id or AUDIT_ACTOR.get()
    if actor and f"operator={actor}" not in note:
        note = f"{note} · operator={actor}"
    previous = db.execute("SELECT entry_hash FROM audit_log ORDER BY rowid DESC LIMIT 1").fetchone()
    previous_hash = previous[0] if previous else ""
    entry_id = uuid.uuid4().hex
    entry_hash = audit_digest(entry_id, action, subject_id, note, stamp, previous_hash)
    db.execute("INSERT INTO audit_log(id,action,subject_id,note,occurred_at,previous_hash,entry_hash) VALUES(?,?,?,?,?,?,?)",
               (entry_id, action, subject_id, note, stamp, previous_hash, entry_hash))
    return entry_id


def verify_audit(db: sqlite3.Connection) -> dict[str, Any]:
    rows = db.execute("SELECT * FROM audit_log ORDER BY rowid").fetchall()
    previous_hash = ""
    for index, row in enumerate(rows):
        expected = audit_digest(row["id"], row["action"], row["subject_id"], row["note"], row["occurred_at"], previous_hash)
        if row["previous_hash"] != previous_hash or row["entry_hash"] != expected:
            return {"verified": False, "entriesChecked": index + 1, "entryId": row["id"],
                    "reason": "Audit entry changed, removed, or chain link is broken."}
        previous_hash = row["entry_hash"]
    return {"verified": True, "entriesChecked": len(rows), "headHash": previous_hash,
            "verifiedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "limitation": "Local hash chaining is tamper-evident, not immutable against a privileged database rewrite."}
