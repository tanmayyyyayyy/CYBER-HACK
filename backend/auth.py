from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from backend import store

SESSION_HOURS = 8
COOKIE_NAME = "drishti_session"


def stamp(value: datetime | None = None) -> str:
    return (value or datetime.now(timezone.utc)).isoformat(timespec="seconds")


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=64)
    return f"scrypt${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt, expected = encoded.split("$", 2)
        if algorithm != "scrypt":
            return False
        actual = _password_hash(password, bytes.fromhex(salt)).split("$", 2)[2]
        return hmac.compare_digest(actual, expected)
    except (ValueError, UnicodeError):
        return False


def public_user(row) -> dict:
    return {"id": row["id"], "email": row["email"], "displayName": row["display_name"],
            "role": row["role"], "status": row["status"], "createdAt": row["created_at"]}


def create_user(email: str, display_name: str, password: str) -> tuple[dict, str | None, str | None]:
    email = email.strip().lower()
    display_name = display_name.strip()
    encoded = _password_hash(password)
    user_id = uuid.uuid4().hex
    created = stamp()
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        role, status = ("administrator", "active") if count == 0 else ("investigator", "pending")
        try:
            db.execute("INSERT INTO users(id,email,display_name,password_hash,role,status,created_at,approved_at) VALUES(?,?,?,?,?,?,?,?)",
                       (user_id, email, display_name, encoded, role, status, created, created if status == "active" else ""))
        except Exception:
            db.rollback()
            raise
        store.append_audit(db, "account.created", user_id, f"Created {role} account ({status})", created, actor_id=user_id)
        row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if status != "active":
            return public_user(row), None, None
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)
        db.execute("INSERT INTO sessions(token_hash,user_id,csrf_token,created_at,expires_at) VALUES(?,?,?,?,?)",
                   (hashlib.sha256(token.encode()).hexdigest(), user_id, csrf, created, stamp(expires)))
        return public_user(row), token, csrf


def login(email: str, password: str) -> tuple[str, dict | None, str | None, str | None]:
    email = email.strip().lower()
    identifier_hash = hashlib.sha256(email.encode("utf-8")).hexdigest()
    with store.connect() as db:
        cutoff = stamp(datetime.now(timezone.utc) - timedelta(minutes=15))
        db.execute("DELETE FROM auth_attempts WHERE attempted_at<?", (stamp(datetime.now(timezone.utc) - timedelta(days=30)),))
        failures = db.execute("SELECT COUNT(*) FROM auth_attempts WHERE identifier_hash=? AND attempted_at>=?", (identifier_hash, cutoff)).fetchone()[0]
        if failures >= 5:
            store.append_audit(db, "security.login_throttled", identifier_hash[:16], "Sign-in rate limit reached")
            return "locked", None, None, None
        row = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            db.execute("INSERT INTO auth_attempts(identifier_hash,attempted_at) VALUES(?,?)", (identifier_hash, stamp()))
            store.append_audit(db, "security.login_failed", identifier_hash[:16], "Invalid local sign-in credentials")
            return "invalid", None, None, None
        if row["status"] == "pending":
            store.append_audit(db, "security.login_denied", row["id"], "Account is awaiting administrator approval")
            return "pending", None, None, None
        if row["status"] != "active":
            store.append_audit(db, "security.login_denied", row["id"], "Disabled account sign-in rejected")
            return "disabled", None, None, None
        db.execute("DELETE FROM auth_attempts WHERE identifier_hash=?", (identifier_hash,))
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        created = stamp()
        db.execute("INSERT INTO sessions(token_hash,user_id,csrf_token,created_at,expires_at) VALUES(?,?,?,?,?)",
                   (hashlib.sha256(token.encode()).hexdigest(), row["id"], csrf, created,
                    stamp(datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS))))
        store.append_audit(db, "auth.login", row["id"], "Local account sign-in", created, actor_id=row["id"])
        return "ok", public_user(row), token, csrf


def session_for(token: str | None):
    if not token:
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    with store.connect() as db:
        row = db.execute("""SELECT s.csrf_token,s.expires_at,u.* FROM sessions s JOIN users u ON u.id=s.user_id
                         WHERE s.token_hash=?""", (digest,)).fetchone()
        if not row:
            return None
        if row["expires_at"] <= stamp() or row["status"] != "active":
            db.execute("DELETE FROM sessions WHERE token_hash=?", (digest,))
            return None
        return {"user": public_user(row), "csrf": row["csrf_token"], "token_hash": digest}


def logout(token_hash: str, user_id: str) -> None:
    with store.connect() as db:
        db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
        store.append_audit(db, "auth.logout", user_id, "Local account sign-out", actor_id=user_id)
