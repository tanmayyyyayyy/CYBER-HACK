from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from security_portal import store

PORTAL_COOKIE = "drishti_portal_session"
SESSION_HOURS = 8

router = APIRouter(prefix="/sec-api", tags=["Security & Escalation Portal"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _now()).isoformat(timespec="seconds")


def _public_user(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "employeeId": row["employee_id"],
        "email": row["email"],
        "displayName": row["display_name"],
        "mobile": row["mobile"],
        "role": row["role"],
        "address": row["address"],
        "pinCode": row["pin_code"],
        "assignedAtms": store.json_load(row["assigned_atms_json"], []),
        "dutyTiming": row["duty_timing"],
        "emergencyContact": row["emergency_contact"],
        "verificationStatus": row["verification_status"],
        "aadhaarVerified": bool(row["aadhaar_verified"]),
        "aadhaarMasked": row["aadhaar_masked"],
        "status": row["status"],
        "createdAt": row["created_at"],
    }


def _session_for(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get(PORTAL_COOKIE)
    if not token:
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    with store.connect() as db:
        row = db.execute(
            """SELECT s.csrf_token, s.expires_at, u.*
               FROM portal_sessions s JOIN portal_users u ON u.id = s.user_id
               WHERE s.token_hash = ?""",
            (digest,),
        ).fetchone()
        if not row:
            return None
        if row["expires_at"] <= _iso() or row["status"] != "active":
            db.execute("DELETE FROM portal_sessions WHERE token_hash=?", (digest,))
            return None
        return {"user": _public_user(row), "csrf": row["csrf_token"], "token_hash": digest}


def _require_auth(request: Request, roles: set[str] | None = None) -> dict[str, Any]:
    sess = _session_for(request)
    if not sess:
        raise HTTPException(401, "Sign in to the Security & Escalation Portal.")
    if request.method not in {"GET", "HEAD"}:
        supplied = request.headers.get("x-portal-csrf", "")
        if not supplied or not hmac.compare_digest(supplied, sess["csrf"]):
            raise HTTPException(403, "Security Portal CSRF verification failed.")
    if roles and sess["user"]["role"] not in roles:
        raise HTTPException(403, f"Role '{sess['user']['role']}' is not authorised for this Security Portal action.")
    return sess


def _issue_session(response: Response, user_row) -> dict[str, Any]:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    created = _iso()
    expires = _iso(_now() + timedelta(hours=SESSION_HOURS))
    with store.connect() as db:
        db.execute(
            "INSERT INTO portal_sessions(token_hash,user_id,csrf_token,created_at,expires_at) VALUES(?,?,?,?,?)",
            (hashlib.sha256(token.encode()).hexdigest(), user_row["id"], csrf, created, expires),
        )
    response.set_cookie(
        PORTAL_COOKIE,
        token,
        httponly=True,
        samesite="strict",
        secure=False,
        max_age=SESSION_HOURS * 3600,
        path="/",
    )
    return {"user": _public_user(user_row), "csrfToken": csrf}


def seed_demo_personnel() -> list[dict[str, Any]]:
    store.init_db()
    stamp = _iso()
    accounts = [
        (
            "guard-101",
            "EMP-GRD-101",
            "guard@atmsec.local",
            "Ramesh Singh (ATM Guard)",
            "+91-98290-11201",
            "guard",
            "GuardSec2026!",
            "Quarter 14, Police Lines Road, Jaipur",
            "302001",
            ["ATM-01", "ATM-02"],
            "08:00 - 20:00",
            "+91-98290-11299",
            "verified",
            1,
            "XXXX-XXXX-4821",
        ),
        (
            "guard-102",
            "EMP-GRD-102",
            "guard2@atmsec.local",
            "Mahesh Verma (Night Guard)",
            "+91-98290-11202",
            "guard",
            "GuardSec2026!",
            "Plot 8, Tonk Phatak, Jaipur",
            "302015",
            ["ATM-03", "ATM-04"],
            "20:00 - 08:00",
            "+91-98290-11288",
            "pending",
            0,
            "",
        ),
        (
            "atm-admin-201",
            "EMP-ADM-201",
            "atmadmin@atmsec.local",
            "Vikram Rathore (ATM Bank Admin)",
            "+91-98290-22101",
            "atm_admin",
            "AdminSec2026!",
            "Zonal Currency Chest, MI Road, Jaipur",
            "302001",
            ["ATM-01", "ATM-02", "ATM-03", "ATM-04"],
            "09:30 - 18:30",
            "+91-141-2378900",
            "verified",
            1,
            "XXXX-XXXX-7710",
        ),
        (
            "govt-301",
            "EMP-GOV-301",
            "govt@atmsec.local",
            "Insp. Kavita Meena (Nodal Officer)",
            "+91-94140-33001",
            "govt_official",
            "GovtSec2026!",
            "Cyber Crime Police Station, Jaipur",
            "302016",
            ["ATM-01", "ATM-02", "ATM-03", "ATM-04"],
            "24x7 Nodal Desk",
            "112 / 1930",
            "verified",
            1,
            "XXXX-XXXX-9012",
        ),
        (
            "govt-302",
            "EMP-GOV-302",
            "backup@atmsec.local",
            "DSP Arvind Shekhawat (Backup Govt)",
            "+91-94140-33002",
            "govt_official",
            "GovtSec2026!",
            "QRT Range HQ, Jaipur",
            "302005",
            ["ATM-01", "ATM-02", "ATM-03", "ATM-04"],
            "24x7 Backup QRT",
            "112",
            "verified",
            1,
            "XXXX-XXXX-6634",
        ),
        (
            "super-001",
            "EMP-SUP-001",
            "super@atmsec.local",
            "Drishti Command Super Admin",
            "+91-141-2740100",
            "super_admin",
            "SuperSec2026!",
            "Rajasthan Cyber Security Control Hub",
            "302016",
            ["ATM-01", "ATM-02", "ATM-03", "ATM-04"],
            "00:00 - 24:00",
            "1930",
            "verified",
            1,
            "XXXX-XXXX-1001",
        ),
    ]
    with store.connect() as db:
        for (
            uid, emp, email, name, mob, role, pw, addr, pin, atms, shift, emg, vstat, a_ver, a_mask
        ) in accounts:
            exists = db.execute("SELECT id FROM portal_users WHERE employee_id=? OR email=?", (emp, email)).fetchone()
            if not exists:
                ref_hash = hashlib.sha256(f"{emp}:{a_mask}:sandbox".encode()).hexdigest() if a_ver else ""
                db.execute(
                    """INSERT INTO portal_users(
                        id,employee_id,email,display_name,mobile,role,password_hash,address,pin_code,
                        assigned_atms_json,duty_timing,emergency_contact,verification_status,
                        aadhaar_verified,aadhaar_masked,aadhaar_ref_hash,status,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        uid, emp, email, name, mob, role, store.hash_secret(pw), addr, pin,
                        json.dumps(atms), shift, emg, vstat, a_ver, a_mask, ref_hash, "active", stamp,
                    ),
                )
        for atm_id, g_id in [("ATM-01", "guard-101"), ("ATM-02", "guard-101"), ("ATM-03", "guard-102"), ("ATM-04", "guard-102")]:
            db.execute(
                """UPDATE atm_assignments
                   SET guard_user_id = CASE WHEN guard_user_id='' THEN ? ELSE guard_user_id END,
                       admin_user_id = CASE WHEN admin_user_id='' THEN 'atm-admin-201' ELSE admin_user_id END,
                       govt_user_id = CASE WHEN govt_user_id='' THEN 'govt-301' ELSE govt_user_id END,
                       backup_govt_user_id = CASE WHEN backup_govt_user_id='' THEN 'govt-302' ELSE backup_govt_user_id END
                   WHERE atm_id=?""",
                (g_id, atm_id),
            )
        rows = db.execute("SELECT * FROM portal_users ORDER BY role, employee_id").fetchall()
    return [_public_user(r) for r in rows]


def process_escalations() -> int:
    """Advance any unacknowledged Priority 1 / Priority 2 alerts past their SLA deadline."""
    now_dt = _now()
    now_str = _iso(now_dt)
    changed = 0
    with store.connect() as db:
        rows = db.execute(
            "SELECT * FROM escalation_alerts WHERE status IN ('active_p1','escalated_p2') AND escalate_after_at != '' AND escalate_after_at <= ?",
            (now_str,),
        ).fetchall()
        for r in rows:
            assign = db.execute("SELECT * FROM atm_assignments WHERE atm_id=?", (r["atm_id"],)).fetchone()
            p2_sla = int(assign["p2_sla_seconds"]) if assign else 20
            tl = store.json_load(r["timeline_json"], [])
            if r["status"] == "active_p1":
                next_dl = _iso(now_dt + timedelta(seconds=max(5, p2_sla)))
                tl.append({"at": now_str, "tier": "Priority 2 · ATM Admin", "note": "Guard SLA expired without response — auto-escalated to ATM Admin / Owner"})
                db.execute(
                    "UPDATE escalation_alerts SET status='escalated_p2', current_priority=2, escalate_after_at=?, updated_at=?, timeline_json=? WHERE id=?",
                    (next_dl, now_str, json.dumps(tl), r["id"]),
                )
                changed += 1
            elif r["status"] == "escalated_p2":
                tl.append({"at": now_str, "tier": "Priority 3 · Backup Govt Official", "note": "ATM Admin SLA expired — auto-escalated to Backup Government Security Official"})
                db.execute(
                    "UPDATE escalation_alerts SET status='escalated_p3', current_priority=3, escalate_after_at='', updated_at=?, timeline_json=? WHERE id=?",
                    (now_str, json.dumps(tl), r["id"]),
                )
                changed += 1
    return changed


class PortalLoginRequest(BaseModel):
    identifier: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=1, max_length=200)


class OtpRequestPayload(BaseModel):
    identifier: str = Field(min_length=2, max_length=120)


class OtpVerifyPayload(BaseModel):
    challenge_id: str = Field(min_length=8, max_length=64)
    otp: str = Field(min_length=4, max_length=10)


class GuardCreateRequest(BaseModel):
    employee_id: str = Field(min_length=3, max_length=40)
    email: str = Field(min_length=5, max_length=120)
    display_name: str = Field(min_length=2, max_length=80)
    mobile: str = Field(min_length=8, max_length=24)
    role: str = Field(default="guard", pattern=r"^(guard|atm_admin|govt_official|super_admin)$")
    password: str = Field(min_length=8, max_length=128)
    address: str = Field(default="", max_length=200)
    pin_code: str = Field(default="", max_length=12)
    assigned_atms: list[str] = Field(default_factory=list)
    duty_timing: str = Field(default="08:00 - 20:00", max_length=60)
    emergency_contact: str = Field(default="", max_length=40)


class GuardUpdateRequest(BaseModel):
    display_name: str | None = None
    mobile: str | None = None
    address: str | None = None
    pin_code: str | None = None
    assigned_atms: list[str] | None = None
    duty_timing: str | None = None
    emergency_contact: str | None = None
    verification_status: str | None = Field(default=None, pattern=r"^(pending|verified|suspended)$")
    status: str | None = Field(default=None, pattern=r"^(active|disabled)$")


class AadhaarOtpRequest(BaseModel):
    aadhaar_input: str = Field(min_length=4, max_length=16, description="Last 4 digits or 12 digits (never persisted in full)")


class AadhaarOtpVerify(BaseModel):
    challenge_id: str = Field(min_length=8, max_length=64)
    otp: str = Field(min_length=4, max_length=10)


class AssignmentUpdateRequest(BaseModel):
    guard_user_id: str = ""
    admin_user_id: str = ""
    govt_user_id: str = ""
    backup_govt_user_id: str = ""
    p1_sla_seconds: int = Field(default=20, ge=5, le=600)
    p2_sla_seconds: int = Field(default=20, ge=5, le=600)


class RuleToggleRequest(BaseModel):
    enabled: bool


class BridgeEventRequest(BaseModel):
    camera_id: str = Field(min_length=2, max_length=32)
    atm_id: str = Field(min_length=2, max_length=32)
    stage: str = Field(pattern=r"^(observe|escalate)$")
    rule_code: str = Field(min_length=2, max_length=60)
    prior_rule_code: str = Field(default="", max_length=60)
    incident_kind: str = Field(min_length=2, max_length=60)
    severity: str = Field(default="warning", max_length=20)
    summary: str = Field(min_length=3, max_length=240)
    subject_code: str = Field(default="", max_length=40)
    snapshot_url: str = Field(default="", max_length=240)
    snapshot_sha256: str = Field(default="", max_length=128)


class SimulateBreachRequest(BaseModel):
    atm_id: str = Field(default="ATM-01", max_length=32)
    with_prior_helmet: bool = True


@router.get("/health")
def portal_health() -> dict[str, Any]:
    store.init_db()
    with store.connect() as db:
        users = db.execute("SELECT COUNT(*) FROM portal_users").fetchone()[0]
        active_alerts = db.execute("SELECT COUNT(*) FROM escalation_alerts WHERE status IN ('active_p1','escalated_p2','escalated_p3')").fetchone()[0]
        observations = db.execute("SELECT COUNT(*) FROM rule_observations").fetchone()[0]
    return {
        "status": "online",
        "service": "Drishti Security & Escalation Portal",
        "usersCount": users,
        "activeAlerts": active_alerts,
        "observations": observations,
    }


@router.post("/auth/demo-seed")
def portal_demo_seed() -> dict[str, Any]:
    users = seed_demo_personnel()
    return {
        "seeded": len(users),
        "accounts": [
            {"role": "guard", "employeeId": "EMP-GRD-101", "email": "guard@atmsec.local", "hint": "Guard (ATM-01, ATM-02)"},
            {"role": "atm_admin", "employeeId": "EMP-ADM-201", "email": "atmadmin@atmsec.local", "hint": "ATM Admin / Owner"},
            {"role": "govt_official", "employeeId": "EMP-GOV-301", "email": "govt@atmsec.local", "hint": "Govt Nodal Officer"},
            {"role": "govt_official", "employeeId": "EMP-GOV-302", "email": "backup@atmsec.local", "hint": "Backup Govt QRT"},
            {"role": "super_admin", "employeeId": "EMP-SUP-001", "email": "super@atmsec.local", "hint": "Super Admin"},
        ],
    }


@router.get("/auth/me")
def portal_me(request: Request) -> dict[str, Any]:
    sess = _session_for(request)
    if not sess:
        raise HTTPException(401, "Not signed in to Security Portal.")
    return {"user": sess["user"], "csrfToken": sess["csrf"]}


@router.post("/auth/login")
def portal_login(payload: PortalLoginRequest, response: Response) -> dict[str, Any]:
    store.init_db()
    ident = payload.identifier.strip()
    with store.connect() as db:
        row = db.execute("SELECT * FROM portal_users WHERE employee_id=? OR email=?", (ident, ident.lower())).fetchone()
    if not row or not store.verify_secret(payload.password, row["password_hash"]):
        raise HTTPException(401, "Invalid Employee ID / email or passphrase.")
    if row["status"] != "active":
        raise HTTPException(403, "Security Portal account is disabled.")
    return _issue_session(response, row)


@router.post("/auth/otp/request")
def portal_otp_request(payload: OtpRequestPayload) -> dict[str, Any]:
    store.init_db()
    ident = payload.identifier.strip()
    with store.connect() as db:
        row = db.execute("SELECT * FROM portal_users WHERE employee_id=? OR email=? OR mobile=?", (ident, ident.lower(), ident)).fetchone()
        if not row or row["status"] != "active":
            raise HTTPException(404, "No active guard/official found for that Employee ID or mobile.")
        otp = f"{secrets.randbelow(900000) + 100000}"
        cid = uuid.uuid4().hex
        mob = str(row["mobile"] or "98XXXXXX00")
        masked = f"{mob[:4]}****{mob[-2:]}" if len(mob) >= 6 else "****"
        db.execute(
            "INSERT INTO portal_otp_challenges VALUES(?,?,?,?,?,?,?,?)",
            (cid, row["id"], "login", store.hash_secret(otp), masked, _iso(_now() + timedelta(minutes=5)), 0, _iso()),
        )
    return {
        "challengeId": cid,
        "maskedMobile": masked,
        "demoOtpHint": otp,
        "notice": "Offline sandbox OTP issued for local guard sign-in demo.",
    }


@router.post("/auth/otp/verify")
def portal_otp_verify(payload: OtpVerifyPayload, response: Response) -> dict[str, Any]:
    with store.connect() as db:
        ch = db.execute("SELECT * FROM portal_otp_challenges WHERE id=? AND purpose='login'", (payload.challenge_id,)).fetchone()
        if not ch or ch["expires_at"] <= _iso():
            raise HTTPException(401, "OTP challenge expired or invalid.")
        if int(ch["attempts"]) >= 5:
            raise HTTPException(429, "Too many invalid OTP attempts.")
        if not store.verify_secret(payload.otp.strip(), ch["otp_hash"]):
            db.execute("UPDATE portal_otp_challenges SET attempts=attempts+1 WHERE id=?", (ch["id"],))
            raise HTTPException(401, "Incorrect OTP code.")
        db.execute("DELETE FROM portal_otp_challenges WHERE id=?", (ch["id"],))
        user_row = db.execute("SELECT * FROM portal_users WHERE id=?", (ch["user_id"],)).fetchone()
    if not user_row or user_row["status"] != "active":
        raise HTTPException(403, "Account inactive.")
    return _issue_session(response, user_row)


@router.post("/auth/logout")
def portal_logout(request: Request, response: Response) -> dict[str, bool]:
    sess = _session_for(request)
    if sess:
        with store.connect() as db:
            db.execute("DELETE FROM portal_sessions WHERE token_hash=?", (sess["token_hash"],))
    response.delete_cookie(PORTAL_COOKIE, path="/")
    return {"ok": True}


@router.get("/guards")
def list_guards(request: Request) -> list[dict[str, Any]]:
    sess = _require_auth(request)
    with store.connect() as db:
        if sess["user"]["role"] == "guard":
            rows = db.execute("SELECT * FROM portal_users WHERE id=?", (sess["user"]["id"],)).fetchall()
        else:
            rows = db.execute("SELECT * FROM portal_users ORDER BY role, employee_id").fetchall()
    return [_public_user(r) for r in rows]


@router.post("/guards", status_code=201)
def create_guard(payload: GuardCreateRequest, request: Request) -> dict[str, Any]:
    sess = _require_auth(request, {"atm_admin", "super_admin"})
    if payload.role in {"govt_official", "super_admin"} and sess["user"]["role"] != "super_admin":
        raise HTTPException(403, "Only Super Admin can register Government Official or Super Admin accounts.")
    uid = uuid.uuid4().hex
    stamp = _iso()
    with store.connect() as db:
        exists = db.execute("SELECT 1 FROM portal_users WHERE employee_id=? OR email=?", (payload.employee_id.strip(), payload.email.strip().lower())).fetchone()
        if exists:
            raise HTTPException(409, "Employee ID or email already exists.")
        db.execute(
            """INSERT INTO portal_users(
                id,employee_id,email,display_name,mobile,role,password_hash,address,pin_code,
                assigned_atms_json,duty_timing,emergency_contact,verification_status,
                aadhaar_verified,aadhaar_masked,aadhaar_ref_hash,status,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                uid, payload.employee_id.strip().upper(), payload.email.strip().lower(), payload.display_name.strip(),
                payload.mobile.strip(), payload.role, store.hash_secret(payload.password), payload.address.strip(),
                payload.pin_code.strip(), json.dumps(payload.assigned_atms), payload.duty_timing.strip(),
                payload.emergency_contact.strip(), "pending", 0, "", "", "active", stamp,
            ),
        )
        row = db.execute("SELECT * FROM portal_users WHERE id=?", (uid,)).fetchone()
    return _public_user(row)


@router.patch("/guards/{user_id}")
def update_guard(user_id: str, payload: GuardUpdateRequest, request: Request) -> dict[str, Any]:
    sess = _require_auth(request, {"guard", "atm_admin", "super_admin"})
    if sess["user"]["role"] == "guard" and sess["user"]["id"] != user_id:
        raise HTTPException(403, "Guards can only update their own profile.")
    with store.connect() as db:
        row = db.execute("SELECT * FROM portal_users WHERE id=?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Guard / Official record not found.")
        updates: dict[str, Any] = {}
        for key, col in [
            ("display_name", "display_name"),
            ("mobile", "mobile"),
            ("address", "address"),
            ("pin_code", "pin_code"),
            ("duty_timing", "duty_timing"),
            ("emergency_contact", "emergency_contact"),
        ]:
            val = getattr(payload, key)
            if val is not None:
                updates[col] = val.strip()
        if sess["user"]["role"] in {"atm_admin", "super_admin"}:
            if payload.assigned_atms is not None:
                updates["assigned_atms_json"] = json.dumps(payload.assigned_atms)
            if payload.verification_status is not None:
                updates["verification_status"] = payload.verification_status
            if payload.status is not None:
                updates["status"] = payload.status
        if updates:
            set_clause = ", ".join(f"{col}=?" for col in updates)
            db.execute(f"UPDATE portal_users SET {set_clause} WHERE id=?", (*updates.values(), user_id))
        updated = db.execute("SELECT * FROM portal_users WHERE id=?", (user_id,)).fetchone()
    return _public_user(updated)


@router.post("/guards/{user_id}/aadhaar-otp/request")
def request_aadhaar_ekyc_otp(user_id: str, payload: AadhaarOtpRequest, request: Request) -> dict[str, Any]:
    sess = _require_auth(request)
    if sess["user"]["role"] == "guard" and sess["user"]["id"] != user_id:
        raise HTTPException(403, "Guards may only verify their own Aadhaar eKYC status.")
    digits = "".join(ch for ch in payload.aadhaar_input if ch.isdigit())
    if len(digits) not in (4, 12):
        raise HTTPException(422, "Provide the last 4 digits (or 12 digits; only masked XXXX-XXXX-last4 is retained).")
    last4 = digits[-4:]
    masked = f"XXXX-XXXX-{last4}"
    otp = f"{secrets.randbelow(900000) + 100000}"
    cid = uuid.uuid4().hex
    with store.connect() as db:
        row = db.execute("SELECT * FROM portal_users WHERE id=?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Guard record not found.")
        db.execute(
            "INSERT INTO portal_otp_challenges VALUES(?,?,?,?,?,?,?,?)",
            (cid, user_id, "aadhaar_ekyc", store.hash_secret(otp), masked, _iso(_now() + timedelta(minutes=5)), 0, _iso()),
        )
    return {
        "challengeId": cid,
        "aadhaarMasked": masked,
        "demoOtpHint": otp,
        "notice": "Simulated UIDAI eKYC OTP adapter: raw 12-digit Aadhaar is never written to storage.",
    }


@router.post("/guards/{user_id}/aadhaar-otp/verify")
def verify_aadhaar_ekyc_otp(user_id: str, payload: AadhaarOtpVerify, request: Request) -> dict[str, Any]:
    sess = _require_auth(request)
    if sess["user"]["role"] == "guard" and sess["user"]["id"] != user_id:
        raise HTTPException(403, "Guards may only verify their own Aadhaar eKYC status.")
    with store.connect() as db:
        ch = db.execute(
            "SELECT * FROM portal_otp_challenges WHERE id=? AND user_id=? AND purpose='aadhaar_ekyc'",
            (payload.challenge_id, user_id),
        ).fetchone()
        if not ch or ch["expires_at"] <= _iso():
            raise HTTPException(401, "Aadhaar OTP challenge expired or invalid.")
        if int(ch["attempts"]) >= 5:
            raise HTTPException(429, "Too many OTP attempts.")
        if not store.verify_secret(payload.otp.strip(), ch["otp_hash"]):
            db.execute("UPDATE portal_otp_challenges SET attempts=attempts+1 WHERE id=?", (ch["id"],))
            raise HTTPException(401, "Invalid OTP code.")
        ref_hash = hmac.new(store.bridge_service_key().encode(), f"{user_id}:{ch['masked_target']}".encode(), hashlib.sha256).hexdigest()
        db.execute(
            "UPDATE portal_users SET aadhaar_verified=1, aadhaar_masked=?, aadhaar_ref_hash=?, verification_status='verified' WHERE id=?",
            (ch["masked_target"], ref_hash, user_id),
        )
        db.execute("DELETE FROM portal_otp_challenges WHERE id=?", (ch["id"],))
        row = db.execute("SELECT * FROM portal_users WHERE id=?", (user_id,)).fetchone()
    return _public_user(row)


@router.get("/assignments")
def list_assignments(request: Request) -> list[dict[str, Any]]:
    _require_auth(request)
    with store.connect() as db:
        rows = db.execute("SELECT * FROM atm_assignments ORDER BY atm_id").fetchall()
        users = {r["id"]: r["display_name"] for r in db.execute("SELECT id, display_name FROM portal_users").fetchall()}
    return [
        {
            "atmId": r["atm_id"],
            "atmName": r["atm_name"],
            "location": r["location"],
            "guardUserId": r["guard_user_id"],
            "guardName": users.get(r["guard_user_id"], "Unassigned"),
            "adminUserId": r["admin_user_id"],
            "adminName": users.get(r["admin_user_id"], "Unassigned"),
            "govtUserId": r["govt_user_id"],
            "govtName": users.get(r["govt_user_id"], "Unassigned"),
            "backupGovtUserId": r["backup_govt_user_id"],
            "backupGovtName": users.get(r["backup_govt_user_id"], "Unassigned"),
            "p1SlaSeconds": int(r["p1_sla_seconds"]),
            "p2SlaSeconds": int(r["p2_sla_seconds"]),
            "updatedAt": r["updated_at"],
        }
        for r in rows
    ]


@router.put("/assignments/{atm_id}")
def update_assignment(atm_id: str, payload: AssignmentUpdateRequest, request: Request) -> dict[str, Any]:
    _require_auth(request, {"atm_admin", "super_admin"})
    stamp = _iso()
    with store.connect() as db:
        cur = db.execute(
            """UPDATE atm_assignments
               SET guard_user_id=?, admin_user_id=?, govt_user_id=?, backup_govt_user_id=?,
                   p1_sla_seconds=?, p2_sla_seconds=?, updated_at=?
               WHERE atm_id=?""",
            (
                payload.guard_user_id, payload.admin_user_id, payload.govt_user_id,
                payload.backup_govt_user_id, payload.p1_sla_seconds, payload.p2_sla_seconds, stamp, atm_id,
            ),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "ATM assignment not found.")
    return next(a for a in list_assignments(request) if a["atmId"] == atm_id)


@router.get("/rules")
def list_rules(request: Request) -> list[dict[str, Any]]:
    _require_auth(request)
    with store.connect() as db:
        rows = db.execute("SELECT * FROM security_rules ORDER BY code").fetchall()
    return [
        {
            "id": r["id"],
            "code": r["code"],
            "name": r["name"],
            "stage": r["stage"],
            "enabled": bool(r["enabled"]),
            "requirePriorRule": r["require_prior_rule"],
            "description": r["description"],
            "updatedAt": r["updated_at"],
        }
        for r in rows
    ]


@router.patch("/rules/{rule_id}")
def toggle_rule(rule_id: str, payload: RuleToggleRequest, request: Request) -> dict[str, Any]:
    _require_auth(request, {"atm_admin", "super_admin"})
    with store.connect() as db:
        cur = db.execute("UPDATE security_rules SET enabled=?, updated_at=? WHERE id=?", (int(payload.enabled), _iso(), rule_id))
        if cur.rowcount == 0:
            raise HTTPException(404, "Security rule not found.")
        r = db.execute("SELECT * FROM security_rules WHERE id=?", (rule_id,)).fetchone()
    return {
        "id": r["id"],
        "code": r["code"],
        "name": r["name"],
        "stage": r["stage"],
        "enabled": bool(r["enabled"]),
        "requirePriorRule": r["require_prior_rule"],
        "description": r["description"],
        "updatedAt": r["updated_at"],
    }


def ingest_bridge_payload(payload: BridgeEventRequest) -> dict[str, Any]:
    """Core contextual two-stage evaluation: Rule 1 observes quietly; Rule 2 escalates Priority 1->2->3."""
    store.init_db()
    stamp = _iso()
    atm_id = payload.atm_id
    with store.connect() as db:
        rules = {r["code"]: r for r in db.execute("SELECT * FROM security_rules").fetchall()}
        rule = rules.get(payload.rule_code)
        if rule and not bool(rule["enabled"]):
            return {"action": "rule_disabled", "siren": False}

        if payload.stage == "observe":
            # Stage 1 (e.g. Rule 1: Person entered wearing helmet/mask) -> Record silently, DO NOT trigger siren
            obs_id = uuid.uuid4().hex
            db.execute(
                "INSERT INTO rule_observations VALUES(?,?,?,?,?,?,?,?,?)",
                (obs_id, payload.camera_id, atm_id, payload.rule_code, payload.subject_code, payload.summary, payload.snapshot_url, "observing", stamp),
            )
            return {"action": "recorded_silent", "observationId": obs_id, "siren": False}

        # Stage 2: Escalate only if no duplicate open P1/P2/P3 alert for same ATM + kind in last 12 seconds
        recent = db.execute(
            """SELECT id FROM escalation_alerts
               WHERE atm_id=? AND incident_kind=? AND status IN ('active_p1','escalated_p2','escalated_p3')
               ORDER BY created_at DESC LIMIT 1""",
            (atm_id, payload.incident_kind),
        ).fetchone()
        if recent:
            return {"action": "deduplicated", "alertId": recent["id"], "siren": True}

        # Check recent Rule 1 observations for contextual link
        prior_code = payload.prior_rule_code
        if not prior_code:
            cutoff = _iso(_now() - timedelta(minutes=5))
            prior_obs = db.execute(
                "SELECT rule_code FROM rule_observations WHERE atm_id=? AND observed_at>=? ORDER BY observed_at DESC LIMIT 1",
                (atm_id, cutoff),
            ).fetchone()
            if prior_obs:
                prior_code = prior_obs["rule_code"]

        assign = db.execute("SELECT * FROM atm_assignments WHERE atm_id=?", (atm_id,)).fetchone()
        guard_id = assign["guard_user_id"] if assign else ""
        admin_id = assign["admin_user_id"] if assign else ""
        govt_id = assign["govt_user_id"] if assign else ""
        backup_id = assign["backup_govt_user_id"] if assign else ""
        p1_sla = int(assign["p1_sla_seconds"]) if assign else 20
        escalate_dl = _iso(_now() + timedelta(seconds=p1_sla))

        alert_id = uuid.uuid4().hex
        timeline = [
            {
                "at": stamp,
                "tier": "Priority 1 · Assigned Guard",
                "note": f"Triggered on {atm_id} ({payload.camera_id})" + (f" following {prior_code}" if prior_code else ""),
            }
        ]
        db.execute(
            """INSERT INTO escalation_alerts(
                id,atm_id,camera_id,incident_kind,prior_rule_code,severity,summary,subject_code,
                snapshot_url,snapshot_sha256,current_priority,status,siren_active,
                assigned_guard_id,assigned_admin_id,assigned_govt_id,backup_govt_id,
                escalate_after_at,acknowledged_by,resolved_by,timeline_json,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                alert_id, atm_id, payload.camera_id, payload.incident_kind, prior_code, payload.severity,
                payload.summary, payload.subject_code, payload.snapshot_url, payload.snapshot_sha256,
                1, "active_p1", 1, guard_id, admin_id, govt_id, backup_id,
                escalate_dl, "", "", json.dumps(timeline), stamp, stamp,
            ),
        )
        db.execute("UPDATE rule_observations SET status='escalated' WHERE atm_id=? AND status='observing'", (atm_id,))
    return {"action": "alert_triggered_p1", "alertId": alert_id, "priority": 1, "siren": True, "priorRule": prior_code}


@router.post("/bridge/event")
def bridge_ingest_event(payload: BridgeEventRequest, request: Request) -> dict[str, Any]:
    supplied = request.headers.get("x-drishti-service-key", "")
    if not supplied or not hmac.compare_digest(supplied, store.bridge_service_key()):
        raise HTTPException(401, "Invalid Drishti bridge service key.")
    return ingest_bridge_payload(payload)


@router.get("/alerts")
def list_alerts_and_observations(request: Request) -> dict[str, Any]:
    sess = _require_auth(request)
    process_escalations()
    user = sess["user"]
    with store.connect() as db:
        users = {r["id"]: r["display_name"] for r in db.execute("SELECT id, display_name FROM portal_users").fetchall()}
        all_alerts = db.execute("SELECT * FROM escalation_alerts ORDER BY created_at DESC LIMIT 60").fetchall()
        obs_rows = db.execute("SELECT * FROM rule_observations ORDER BY observed_at DESC LIMIT 30").fetchall()

    visible_alerts = []
    for r in all_alerts:
        if user["role"] == "guard":
            if r["assigned_guard_id"] != user["id"] and r["atm_id"] not in user["assignedAtms"]:
                continue
        visible_alerts.append(
            {
                "id": r["id"],
                "atmId": r["atm_id"],
                "cameraId": r["camera_id"],
                "incidentKind": r["incident_kind"],
                "priorRuleCode": r["prior_rule_code"],
                "severity": r["severity"],
                "summary": r["summary"],
                "subjectCode": r["subject_code"],
                "snapshotUrl": r["snapshot_url"],
                "snapshotSha256": r["snapshot_sha256"],
                "currentPriority": int(r["current_priority"]),
                "status": r["status"],
                "sirenActive": bool(r["siren_active"]),
                "assignedGuardId": r["assigned_guard_id"],
                "assignedGuardName": users.get(r["assigned_guard_id"], "On-Duty Guard"),
                "assignedAdminName": users.get(r["assigned_admin_id"], "ATM Admin"),
                "assignedGovtName": users.get(r["assigned_govt_id"], "Govt Official"),
                "backupGovtName": users.get(r["backup_govt_id"], "Backup Govt Official"),
                "escalateAfterAt": r["escalate_after_at"],
                "acknowledgedBy": r["acknowledged_by"],
                "resolvedBy": r["resolved_by"],
                "timeline": store.json_load(r["timeline_json"], []),
                "createdAt": r["created_at"],
                "updatedAt": r["updated_at"],
            }
        )

    observations = []
    for o in obs_rows:
        if user["role"] == "guard" and o["atm_id"] not in user["assignedAtms"]:
            continue
        observations.append(
            {
                "id": o["id"],
                "cameraId": o["camera_id"],
                "atmId": o["atm_id"],
                "ruleCode": o["rule_code"],
                "subjectCode": o["subject_code"],
                "detail": o["detail"],
                "status": o["status"],
                "observedAt": o["observed_at"],
            }
        )
    return {"alerts": visible_alerts, "observations": observations}


@router.post("/alerts/simulate")
def simulate_two_stage_breach(payload: SimulateBreachRequest, request: Request) -> dict[str, Any]:
    _require_auth(request, {"guard", "atm_admin", "govt_official", "super_admin"})
    cam_id = payload.atm_id.replace("ATM-", "CAM-")
    if payload.with_prior_helmet:
        ingest_bridge_payload(
            BridgeEventRequest(
                camera_id=cam_id,
                atm_id=payload.atm_id,
                stage="observe",
                rule_code="RULE_1_CONCEALMENT",
                incident_kind="rule1.helmet_entry",
                severity="info",
                summary=f"Rule 1: Person entered {payload.atm_id} wearing helmet/face cover — observing quietly (no siren).",
                subject_code="SUB-DEMO",
            )
        )
    res = ingest_bridge_payload(
        BridgeEventRequest(
            camera_id=cam_id,
            atm_id=payload.atm_id,
            stage="escalate",
            rule_code="RULE_2_ATM_TAMPER_OR_FORCE",
            prior_rule_code="RULE_1_CONCEALMENT" if payload.with_prior_helmet else "",
            incident_kind="stream.atm_breach_alert",
            severity="critical",
            summary=f"Suspicious activity detected at {payload.atm_id}: Masked/helmeted subject attempting to shake/pry ATM machine!",
            subject_code="SUB-DEMO",
        )
    )
    return res


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str, request: Request) -> dict[str, Any]:
    sess = _require_auth(request)
    user = sess["user"]
    stamp = _iso()
    with store.connect() as db:
        row = db.execute("SELECT * FROM escalation_alerts WHERE id=?", (alert_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Alert not found.")
        tl = store.json_load(row["timeline_json"], [])
        tl.append({"at": stamp, "tier": f"Acknowledged by {user['displayName']}", "note": f"Siren silenced; responder ({user['role']}) handling incident."})
        db.execute(
            "UPDATE escalation_alerts SET status='acknowledged', siren_active=0, escalate_after_at='', acknowledged_by=?, updated_at=?, timeline_json=? WHERE id=?",
            (user["displayName"], stamp, json.dumps(tl), alert_id),
        )
    return {"status": "acknowledged", "id": alert_id}


@router.post("/alerts/{alert_id}/escalate")
def escalate_alert_manual(alert_id: str, request: Request) -> dict[str, Any]:
    sess = _require_auth(request)
    user = sess["user"]
    stamp = _iso()
    with store.connect() as db:
        row = db.execute("SELECT * FROM escalation_alerts WHERE id=?", (alert_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Alert not found.")
        tl = store.json_load(row["timeline_json"], [])
        cur_p = int(row["current_priority"])
        if cur_p <= 1:
            next_p, next_status, tier = 2, "escalated_p2", "Priority 2 · ATM Admin"
        else:
            next_p, next_status, tier = 3, "escalated_p3", "Priority 3 · Backup Govt Official"
        tl.append({"at": stamp, "tier": tier, "note": f"Manually escalated by {user['displayName']} ({user['role']})"})
        db.execute(
            "UPDATE escalation_alerts SET status=?, current_priority=?, siren_active=1, escalate_after_at='', updated_at=?, timeline_json=? WHERE id=?",
            (next_status, next_p, stamp, json.dumps(tl), alert_id),
        )
    return {"status": next_status, "priority": next_p, "id": alert_id}


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: str, request: Request) -> dict[str, Any]:
    sess = _require_auth(request)
    user = sess["user"]
    stamp = _iso()
    with store.connect() as db:
        row = db.execute("SELECT * FROM escalation_alerts WHERE id=?", (alert_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Alert not found.")
        tl = store.json_load(row["timeline_json"], [])
        tl.append({"at": stamp, "tier": "Resolved", "note": f"Incident closed by {user['displayName']} ({user['role']})"})
        db.execute(
            "UPDATE escalation_alerts SET status='resolved', siren_active=0, escalate_after_at='', resolved_by=?, updated_at=?, timeline_json=? WHERE id=?",
            (user["displayName"], stamp, json.dumps(tl), alert_id),
        )
    return {"status": "resolved", "id": alert_id}

