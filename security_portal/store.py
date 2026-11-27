from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("DRISHTI_DATA_DIR", ROOT / "backend" / "data")).resolve()
DB_PATH = DATA / "security_portal.sqlite3"
SERVICE_KEY_PATH = DATA / "bridge.key"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def json_load(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or "")
    except (TypeError, json.JSONDecodeError):
        return default


def bridge_service_key() -> str:
    env_key = os.environ.get("DRISHTI_BRIDGE_KEY", "").strip()
    if env_key:
        return env_key
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not SERVICE_KEY_PATH.is_file():
        key = secrets.token_hex(32)
        SERVICE_KEY_PATH.write_text(key, encoding="utf-8")
        try:
            SERVICE_KEY_PATH.chmod(0o600)
        except OSError:
            pass
        return key
    return SERVICE_KEY_PATH.read_text(encoding="utf-8").strip()


def connect() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        DATA.chmod(0o700)
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


def hash_secret(value: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.scrypt(value.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${derived.hex()}"


def verify_secret(value: str, encoded: str) -> bool:
    import hmac

    try:
        alg, salt, expected = encoded.split("$", 2)
        if alg != "scrypt":
            return False
        actual = hash_secret(value, bytes.fromhex(salt)).split("$", 2)[2]
        return hmac.compare_digest(actual, expected)
    except (ValueError, UnicodeError):
        return False


def init_db() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS portal_users (
                id TEXT PRIMARY KEY,
                employee_id TEXT NOT NULL UNIQUE COLLATE NOCASE,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                display_name TEXT NOT NULL,
                mobile TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'guard',
                password_hash TEXT NOT NULL,
                address TEXT NOT NULL DEFAULT '',
                pin_code TEXT NOT NULL DEFAULT '',
                assigned_atms_json TEXT NOT NULL DEFAULT '[]',
                duty_timing TEXT NOT NULL DEFAULT '08:00 - 20:00',
                emergency_contact TEXT NOT NULL DEFAULT '',
                verification_status TEXT NOT NULL DEFAULT 'pending',
                aadhaar_verified INTEGER NOT NULL DEFAULT 0,
                aadhaar_masked TEXT NOT NULL DEFAULT '',
                aadhaar_ref_hash TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS portal_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES portal_users(id) ON DELETE CASCADE,
                csrf_token TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS portal_otp_challenges (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES portal_users(id) ON DELETE CASCADE,
                purpose TEXT NOT NULL,
                otp_hash TEXT NOT NULL,
                masked_target TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS portal_auth_attempts (
                identifier_hash TEXT NOT NULL,
                remote_hash TEXT NOT NULL,
                attempted_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_portal_auth_attempts_time
                ON portal_auth_attempts(attempted_at);
            CREATE TABLE IF NOT EXISTS security_rules (
                id TEXT PRIMARY KEY,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                stage TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                require_prior_rule TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS atm_assignments (
                atm_id TEXT PRIMARY KEY,
                atm_name TEXT NOT NULL,
                location TEXT NOT NULL DEFAULT '',
                guard_user_id TEXT NOT NULL DEFAULT '',
                admin_user_id TEXT NOT NULL DEFAULT '',
                govt_user_id TEXT NOT NULL DEFAULT '',
                backup_govt_user_id TEXT NOT NULL DEFAULT '',
                p1_sla_seconds INTEGER NOT NULL DEFAULT 20,
                p2_sla_seconds INTEGER NOT NULL DEFAULT 20,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rule_observations (
                id TEXT PRIMARY KEY,
                camera_id TEXT NOT NULL,
                atm_id TEXT NOT NULL,
                rule_code TEXT NOT NULL,
                subject_code TEXT NOT NULL DEFAULT '',
                detail TEXT NOT NULL,
                snapshot_url TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'observing',
                observed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS escalation_alerts (
                id TEXT PRIMARY KEY,
                atm_id TEXT NOT NULL,
                camera_id TEXT NOT NULL,
                incident_kind TEXT NOT NULL,
                prior_rule_code TEXT NOT NULL DEFAULT '',
                severity TEXT NOT NULL DEFAULT 'critical',
                summary TEXT NOT NULL,
                subject_code TEXT NOT NULL DEFAULT '',
                snapshot_url TEXT NOT NULL DEFAULT '',
                snapshot_sha256 TEXT NOT NULL DEFAULT '',
                current_priority INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'active_p1',
                siren_active INTEGER NOT NULL DEFAULT 1,
                assigned_guard_id TEXT NOT NULL DEFAULT '',
                assigned_admin_id TEXT NOT NULL DEFAULT '',
                assigned_govt_id TEXT NOT NULL DEFAULT '',
                backup_govt_id TEXT NOT NULL DEFAULT '',
                escalate_after_at TEXT NOT NULL DEFAULT '',
                acknowledged_by TEXT NOT NULL DEFAULT '',
                resolved_by TEXT NOT NULL DEFAULT '',
                timeline_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_portal_alerts_created ON escalation_alerts(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_portal_obs_time ON rule_observations(observed_at DESC);
            """
        )
        stamp = now_iso()
        default_rules = [
            (
                "rule-1-concealment",
                "RULE_1_CONCEALMENT",
                "Rule 1: Face Concealment Entry (Helmet / Mask / Muffler)",
                "observe",
                1,
                "",
                "Detects helmet, mask, cap or muffler hiding face inside ATM vestibule. Logs silently & monitors without triggering siren.",
            ),
            (
                "rule-2-tamper",
                "RULE_2_ATM_TAMPER_OR_FORCE",
                "Rule 2: Machine Tampering, Shaking, Prying or Force Entry",
                "escalate",
                1,
                "RULE_1_CONCEALMENT",
                "Triggers immediate siren & Priority 1 Guard alert if person shakes/tampers/pries ATM machine, damages keypad, or triggers cutter flash.",
            ),
            (
                "rule-3-repeat-risk",
                "RULE_3_REPEAT_SUSPECT_BEHAVIOR",
                "Rule 3: Repeat Concealed Visitor + Terminal Manipulation",
                "escalate",
                1,
                "",
                "Escalates alert if an auto-collected repeat visitor performs extended suspicious manipulation or crowd surround at terminal.",
            ),
        ]
        for rid, code, name, stage, enabled, req, desc in default_rules:
            db.execute(
                """INSERT OR IGNORE INTO security_rules(id,code,name,stage,enabled,require_prior_rule,description,updated_at)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (rid, code, name, stage, enabled, req, desc, stamp),
            )

        default_atms = [
            ("ATM-01", "ATM Vestibule North", "MI Road Branch, Jaipur", 20, 20),
            ("ATM-02", "Keypad & Card Slot", "MI Road Branch, Jaipur", 20, 20),
            ("ATM-03", "Cash Dispenser & Queue", "Tonk Road Kiosk, Jaipur", 20, 20),
            ("ATM-04", "Exterior & Exit Perimeter", "Tonk Road Kiosk, Jaipur", 20, 20),
        ]
        for atm_id, name, loc, p1, p2 in default_atms:
            db.execute(
                """INSERT OR IGNORE INTO atm_assignments(
                    atm_id,atm_name,location,guard_user_id,admin_user_id,govt_user_id,backup_govt_user_id,p1_sla_seconds,p2_sla_seconds,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (atm_id, name, loc, "", "", "", "", p1, p2, stamp),
            )


def remove_demo_accounts() -> None:
    with connect() as db:
        db.execute("DELETE FROM portal_otp_challenges")
        db.execute("UPDATE portal_users SET verification_status='pending' WHERE aadhaar_verified=1")
        db.execute("UPDATE portal_users SET aadhaar_verified=0, aadhaar_masked='', aadhaar_ref_hash=''")
        db.execute("""UPDATE atm_assignments SET
            guard_user_id = CASE WHEN guard_user_id IN ('guard-101','guard-102') THEN '' ELSE guard_user_id END,
            admin_user_id = CASE WHEN admin_user_id = 'atm-admin-201' THEN '' ELSE admin_user_id END,
            govt_user_id = CASE WHEN govt_user_id IN ('govt-301','govt-302') THEN '' ELSE govt_user_id END,
            backup_govt_user_id = CASE WHEN backup_govt_user_id = 'govt-302' THEN '' ELSE backup_govt_user_id END""")
        db.execute("""DELETE FROM portal_users WHERE employee_id IN
            ('EMP-GRD-101','EMP-GRD-102','EMP-ADM-201','EMP-GOV-301','EMP-GOV-302','EMP-SUP-001')""")

