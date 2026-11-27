from __future__ import annotations

import contextvars
import hashlib
import json
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
LIVE_EVIDENCE = DATA / "live_evidence"
DEMO_FEEDS = ROOT / "demo_feeds"
DB_PATH = DATA / "drishti.sqlite3"
SIGNING_KEY_PATH = DATA / "signing.key"
AUDIT_ACTOR: contextvars.ContextVar[str] = contextvars.ContextVar("drishti_audit_actor", default="")


def connect() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    UPLOADS.mkdir(parents=True, exist_ok=True, mode=0o700)
    CANDIDATES.mkdir(parents=True, exist_ok=True, mode=0o700)
    BACKUPS.mkdir(parents=True, exist_ok=True, mode=0o700)
    LIVE_EVIDENCE.mkdir(parents=True, exist_ok=True, mode=0o700)
    for directory in (DATA, UPLOADS, CANDIDATES, BACKUPS, LIVE_EVIDENCE):
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
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA synchronous = NORMAL")
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
                forensics_json TEXT NOT NULL DEFAULT '{}',
                uploaded_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                clip_id TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
                transaction_time TEXT NOT NULL,
                time_mode TEXT NOT NULL DEFAULT 'clip',
                clip_start_time TEXT NOT NULL DEFAULT '',
                transaction_ref TEXT NOT NULL DEFAULT '',
                case_ref TEXT NOT NULL DEFAULT '',
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
                bbox_json TEXT NOT NULL DEFAULT '[]',
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
            CREATE TABLE IF NOT EXISTS stream_detections (
                id TEXT PRIMARY KEY,
                camera_id TEXT NOT NULL,
                track_id INTEGER NOT NULL,
                person_count INTEGER NOT NULL,
                confidence REAL NOT NULL,
                alert_kind TEXT NOT NULL DEFAULT '',
                occurred_at TEXT NOT NULL,
                details_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS case_watchlist (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                case_ref TEXT NOT NULL DEFAULT '',
                candidate_id TEXT NOT NULL DEFAULT '',
                clip_id TEXT NOT NULL DEFAULT '',
                embedding_json TEXT NOT NULL,
                image_path TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS live_identities (
                id TEXT PRIMARY KEY,
                subject_code TEXT NOT NULL UNIQUE,
                label TEXT NOT NULL DEFAULT '',
                embedding_json TEXT NOT NULL,
                best_score REAL NOT NULL DEFAULT 0,
                best_image_path TEXT NOT NULL,
                best_sha256 TEXT NOT NULL DEFAULT '',
                first_camera_id TEXT NOT NULL,
                last_camera_id TEXT NOT NULL,
                cameras_json TEXT NOT NULL DEFAULT '[]',
                flags_json TEXT NOT NULL DEFAULT '[]',
                sighting_count INTEGER NOT NULL DEFAULT 1,
                appearance_count INTEGER NOT NULL DEFAULT 1,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                last_repeat_alert_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS live_sightings (
                id TEXT PRIMARY KEY,
                identity_id TEXT NOT NULL REFERENCES live_identities(id) ON DELETE CASCADE,
                camera_id TEXT NOT NULL,
                score REAL NOT NULL,
                similarity REAL NOT NULL,
                flags_json TEXT NOT NULL DEFAULT '[]',
                image_path TEXT NOT NULL,
                sha256 TEXT NOT NULL DEFAULT '',
                occurred_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS live_incidents (
                id TEXT PRIMARY KEY,
                camera_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                severity TEXT NOT NULL,
                summary TEXT NOT NULL,
                subject_code TEXT NOT NULL DEFAULT '',
                person_count INTEGER NOT NULL DEFAULT 0,
                face_count INTEGER NOT NULL DEFAULT 0,
                image_path TEXT NOT NULL,
                sha256 TEXT NOT NULL DEFAULT '',
                occurred_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS case_dossiers (
                id TEXT PRIMARY KEY,
                fir_number TEXT NOT NULL DEFAULT '',
                ncrp_ack TEXT NOT NULL DEFAULT '',
                police_station TEXT NOT NULL DEFAULT '',
                io_name TEXT NOT NULL DEFAULT '',
                io_badge TEXT NOT NULL DEFAULT '',
                atm_id TEXT NOT NULL DEFAULT '',
                bank_name TEXT NOT NULL DEFAULT '',
                fraud_type TEXT NOT NULL DEFAULT 'ATM Cash-Out / Card Fraud',
                loss_inr INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
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
            CREATE INDEX IF NOT EXISTS idx_stream_detections_time ON stream_detections(occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_log(occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_live_identities_seen ON live_identities(last_seen_at DESC);
            CREATE INDEX IF NOT EXISTS idx_live_sightings_ident ON live_sightings(identity_id, occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_live_incidents_time ON live_incidents(occurred_at DESC);
            """
        )
        clip_columns = {row[1] for row in db.execute("PRAGMA table_info(clips)")}
        for col, stmt in {
            "source_path": "ALTER TABLE clips ADD COLUMN source_path TEXT NOT NULL DEFAULT ''",
            "sha256": "ALTER TABLE clips ADD COLUMN sha256 TEXT NOT NULL DEFAULT ''",
            "analysis_sha256": "ALTER TABLE clips ADD COLUMN analysis_sha256 TEXT NOT NULL DEFAULT ''",
            "playback_codec": "ALTER TABLE clips ADD COLUMN playback_codec TEXT NOT NULL DEFAULT 'unknown'",
            "preview_ready": "ALTER TABLE clips ADD COLUMN preview_ready INTEGER NOT NULL DEFAULT 1",
            "forensics_json": "ALTER TABLE clips ADD COLUMN forensics_json TEXT NOT NULL DEFAULT '{}'",
        }.items():
            if col not in clip_columns:
                db.execute(stmt)

        analysis_columns = {row[1] for row in db.execute("PRAGMA table_info(analyses)")}
        if "case_ref" not in analysis_columns:
            db.execute("ALTER TABLE analyses ADD COLUMN case_ref TEXT NOT NULL DEFAULT ''")

        cand_columns = {row[1] for row in db.execute("PRAGMA table_info(candidates)")}
        if "bbox_json" not in cand_columns:
            db.execute("ALTER TABLE candidates ADD COLUMN bbox_json TEXT NOT NULL DEFAULT '[]'")

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
            db.executemany(
                "INSERT INTO auth_attempts(identifier_hash,attempted_at) VALUES(?,?)",
                [
                    (hashlib.sha256(str(row["email"]).strip().lower().encode()).hexdigest(), row["attempted_at"])
                    for row in old_attempts
                ],
            )
            db.execute("DROP TABLE auth_attempts_legacy")
        db.execute("CREATE INDEX IF NOT EXISTS idx_auth_attempts_time ON auth_attempts(identifier_hash,attempted_at)")

        previous_hash = ""
        for row in db.execute("SELECT * FROM audit_log ORDER BY rowid").fetchall():
            if row["entry_hash"]:
                previous_hash = row["entry_hash"]
                continue
            entry_hash = audit_digest(row["id"], row["action"], row["subject_id"], row["note"], row["occurred_at"], previous_hash)
            db.execute("UPDATE audit_log SET previous_hash=?,entry_hash=? WHERE id=?", (previous_hash, entry_hash, row["id"]))
            previous_hash = entry_hash

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
            db.execute(
                """UPDATE clips SET source_path=?,sha256=CASE WHEN sha256='' THEN ? ELSE sha256 END,
                   analysis_sha256=CASE WHEN analysis_sha256='' THEN ? ELSE analysis_sha256 END WHERE id=?""",
                (source_path, digest, digest, row["id"]),
            )


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def json_load(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def audit_digest(entry_id: str, action: str, subject_id: str, note: str, occurred_at: str, previous_hash: str) -> str:
    payload = json.dumps(
        {
            "id": entry_id,
            "action": action,
            "subject_id": subject_id,
            "note": note,
            "occurred_at": occurred_at,
            "previous_hash": previous_hash,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def append_audit(
    db: sqlite3.Connection,
    action: str,
    subject_id: str,
    note: str,
    occurred_at: str | None = None,
    actor_id: str | None = None,
) -> str:
    stamp = occurred_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    actor = actor_id or AUDIT_ACTOR.get()
    if actor:
        note = f"{note} · operator={actor}"
    if not db.in_transaction:
        db.execute("BEGIN IMMEDIATE")
    previous = db.execute("SELECT entry_hash FROM audit_log ORDER BY rowid DESC LIMIT 1").fetchone()
    previous_hash = previous[0] if previous else ""
    entry_id = uuid.uuid4().hex
    entry_hash = audit_digest(entry_id, action, subject_id, note, stamp, previous_hash)
    db.execute(
        "INSERT INTO audit_log(id,action,subject_id,note,occurred_at,previous_hash,entry_hash) VALUES(?,?,?,?,?,?,?)",
        (entry_id, action, subject_id, note, stamp, previous_hash, entry_hash),
    )
    return entry_id


def verify_audit(db: sqlite3.Connection) -> dict[str, Any]:
    rows = db.execute("SELECT * FROM audit_log ORDER BY rowid").fetchall()
    previous_hash = ""
    for index, row in enumerate(rows):
        expected = audit_digest(row["id"], row["action"], row["subject_id"], row["note"], row["occurred_at"], previous_hash)
        if row["previous_hash"] != previous_hash or row["entry_hash"] != expected:
            return {
                "verified": False,
                "entriesChecked": index + 1,
                "entryId": row["id"],
                "reason": "Audit entry changed, removed, or chain link is broken.",
            }
        previous_hash = row["entry_hash"]
    return {
        "verified": True,
        "entriesChecked": len(rows),
        "headHash": previous_hash,
        "verifiedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "limitation": "Local hash chaining is tamper-evident, not immutable against a privileged database rewrite.",
    }
