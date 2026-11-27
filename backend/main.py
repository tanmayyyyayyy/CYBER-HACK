from __future__ import annotations

import contextvars
import csv
import hashlib
import hmac
import io
import json
import mimetypes
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import cv2
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from backend import analysis, auth, blockchain, forensics, store, streams
from backend.security import encrypt_snapshot, sign_manifest, verify_manifest
from security_portal import router as security_portal_router

APP_NAME = "Drishti Forensic Review"
ALLOWED_EXTENSIONS = {
    ".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".mpeg", ".mpg",
    ".dav", ".h264", ".264", ".ts", ".m4v", ".asf", ".vob",
}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
LOCAL_ORIGINS = ["http://127.0.0.1:5174", "http://localhost:5174"]

analysis_pool: ThreadPoolExecutor | None = None


def startup() -> None:
    global analysis_pool
    store.init_db()
    analysis_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="drishti-analysis")
    with store.connect() as db:
        interrupted = db.execute("SELECT id FROM analyses WHERE status IN ('queued','running')").fetchall()
        for row in interrupted:
            db.execute(
                "UPDATE analyses SET status='failed',error=?,updated_at=? WHERE id=?",
                ("Processing stopped because the local service restarted. Start this analysis again.", now(), row["id"]),
            )
            store.append_audit(db, "analysis.interrupted", row["id"], "Service restarted during analysis", now())
    if os.environ.get("DRISHTI_DISABLE_AUTO_STREAMS") != "1":
        streams.manager.start()


def shutdown() -> None:
    global analysis_pool
    streams.manager.stop()
    if analysis_pool is not None:
        analysis_pool.shutdown(wait=True, cancel_futures=True)
        analysis_pool = None


@asynccontextmanager
async def lifespan(_application: FastAPI):
    startup()
    try:
        yield
    finally:
        shutdown()


app = FastAPI(title=APP_NAME, version="0.2.0", docs_url="/api/docs", redoc_url=None, lifespan=lifespan)
app.include_router(security_portal_router.router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=LOCAL_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-Requested-With"],
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _matches_sha256(path: Path, expected: str) -> bool:
    try:
        return path.is_file() and _file_sha256(path) == expected
    except OSError:
        return False


def _inspect_video(path: Path) -> dict | None:
    cap = cv2.VideoCapture(str(path))
    try:
        ok, frame = cap.read()
        if not ok or frame is None:
            return None
        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        codec = "".join(chr((fourcc >> (8 * i)) & 0xFF) for i in range(4)).strip("\x00 ") or "unknown"
        fps = float(cap.get(cv2.CAP_PROP_FPS)) or 25.0
        frame_count = float(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        return {
            "width": frame.shape[1],
            "height": frame.shape[0],
            "fps": fps,
            "duration": frame_count / fps if frame_count > 0 else 0.0,
            "codec": codec,
        }
    finally:
        cap.release()


def _transcode_review_copy(source: Path, target: Path, ffmpeg: str) -> None:
    try:
        subprocess.run(
            [
                ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-an",
                "-sn",
                "-dn",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(target),
            ],
            capture_output=True,
            timeout=600,
            check=True,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(
            422,
            "Could not normalize this export locally. If it uses encrypted/proprietary DVR playback, export it as standard MP4/AVI from your DVR software (Hikvision iVMS-4200, Dahua SmartPSS, or CP Plus KVMS) and retry.",
        ) from exc


def _clip_or_404(clip_id: str) -> dict:
    with store.connect() as db:
        clip = store.row_dict(db.execute("SELECT * FROM clips WHERE id=?", (clip_id,)).fetchone())
    if not clip:
        raise HTTPException(404, "Clip not found")
    return clip


def _candidate_or_404(candidate_id: str) -> dict:
    with store.connect() as db:
        candidate = store.row_dict(db.execute("SELECT * FROM candidates WHERE id=?", (candidate_id,)).fetchone())
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    return candidate


def _public_candidate(row: dict) -> dict:
    flags = store.json_load(row.get("flags_json"), [])
    return {
        "id": row["id"],
        "analysisId": row["analysis_id"],
        "clipId": row["clip_id"],
        "time": round(float(row["frame_seconds"]), 3),
        "timeLabel": f"{int(row['frame_seconds'] // 3600):02}:{int(row['frame_seconds'] % 3600 // 60):02}:{int(row['frame_seconds'] % 60):02}",
        "trackId": row["track_id"],
        "score": row["score"],
        "metrics": {
            "sharpness": row["sharpness"],
            "illumination": row["illumination"],
            "faceSize": row["face_size"],
            "pose": row["pose"],
            "confidence": round(row["confidence"] * 100),
        },
        "flags": flags,
        "bbox": store.json_load(row.get("bbox_json"), []),
        "reviewStatus": row["review_status"],
        "note": row["note"],
        "imageUrl": f"/api/candidates/{row['id']}/image",
        "enhancedUrl": f"/api/candidates/{row['id']}/enhanced",
        "redactedFrameUrl": f"/api/candidates/{row['id']}/frame-redacted",
    }


def _public_clip(r: dict) -> dict:
    return {
        "id": r["id"],
        "filename": r["filename"],
        "sizeBytes": r["size_bytes"],
        "duration": r["duration"],
        "width": r["width"],
        "height": r["height"],
        "fps": r["fps"],
        "codec": r["codec"],
        "playbackCodec": r["playback_codec"],
        "normalized": r["sha256"] != r["analysis_sha256"],
        "previewReady": bool(r["preview_ready"]),
        "cameraId": r["camera_id"],
        "sha256": r["sha256"],
        "analysisSha256": r["analysis_sha256"],
        "forensics": store.json_load(r.get("forensics_json"), {}),
        "uploadedAt": r["uploaded_at"],
        "videoUrl": f"/api/clips/{r['id']}/video",
        "posterUrl": f"/api/clips/{r['id']}/poster",
    }


def _ingest_local_file(source_file: Path, original_name: str, camera_id: str, copy_source: bool = True) -> dict:
    suffix = Path(original_name).suffix.lower() or ".mp4"
    clip_id = uuid.uuid4().hex
    path = store.UPLOADS / f"{clip_id}{suffix}"
    normalized = store.UPLOADS / f"{clip_id}-normalized.mp4"
    if copy_source:
        shutil.copy2(source_file, path)
    size = path.stat().st_size
    source_digest = _file_sha256(path)
    source_info = _inspect_video(path)
    if source_info is None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise HTTPException(422, "This file could not be decoded. Install FFmpeg and export it as MP4/H.264.")
        _transcode_review_copy(path, normalized, ffmpeg)
        source_info = _inspect_video(normalized)
        if source_info is None:
            raise HTTPException(422, "FFmpeg could not normalize this export. Check the DVR/NVR export settings.")
        playable_path = normalized
        preview_ready = True
        playback_codec = source_info["codec"]
    else:
        playable_path = path
        codec_name = source_info["codec"].lower()
        suffix_name = suffix.lower()
        browser_codec = (suffix_name == ".mp4" and codec_name in {"avc1", "h264", "x264"}) or (
            suffix_name == ".webm" and codec_name in {"vp80", "vp90", "vp09", "av01"}
        )
        ffmpeg = shutil.which("ffmpeg")
        if not browser_codec and ffmpeg:
            _transcode_review_copy(path, normalized, ffmpeg)
            playable_path = normalized
            playback_info = _inspect_video(playable_path)
            if playback_info is None:
                raise HTTPException(422, "The converted playback copy could not be decoded.")
            playback_codec = playback_info["codec"]
            preview_ready = True
        else:
            playback_codec = source_info["codec"]
            preview_ready = browser_codec

    width, height = source_info["width"], source_info["height"]
    fps, duration, codec = source_info["fps"], source_info["duration"], source_info["codec"]
    analysis_digest = _file_sha256(playable_path)
    probe_data = forensics.probe_video_container(path)
    continuity = forensics.check_frame_continuity(playable_path)
    forensics_payload = {"container": probe_data, "continuity": continuity}

    record = {
        "id": clip_id,
        "filename": original_name[:180],
        "camera_id": camera_id,
        "path": str(playable_path),
        "source_path": str(path),
        "size_bytes": size,
        "duration": round(duration, 3),
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "codec": codec,
        "playback_codec": playback_codec,
        "preview_ready": int(preview_ready),
        "sha256": source_digest,
        "analysis_sha256": analysis_digest,
        "forensics_json": json.dumps(forensics_payload),
        "uploaded_at": now(),
    }
    with store.connect() as db:
        db.execute(
            """INSERT INTO clips(id,filename,camera_id,path,source_path,size_bytes,duration,
               width,height,fps,codec,playback_codec,preview_ready,sha256,analysis_sha256,forensics_json,uploaded_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            tuple(record.values()),
        )
        store.append_audit(
            db,
            "clip.uploaded",
            clip_id,
            f"Local clip uploaded: {original_name[:100]} ({size} bytes, SHA-256 {source_digest[:16]}…)",
            now(),
        )
    return _public_clip(record)


class AnalysisRequest(BaseModel):
    clip_id: str = Field(min_length=8, max_length=64)
    transaction_time: str = Field(min_length=5, max_length=35)
    time_mode: str = Field(default="clip", pattern=r"^(clip|absolute)$")
    clip_start_time: str = Field(default="", max_length=35)
    transaction_ref: str = Field(default="", max_length=40)
    case_ref: str = Field(default="", max_length=40)
    window_seconds: int = Field(default=30, ge=5, le=300)


class ReviewRequest(BaseModel):
    status: str = Field(pattern=r"^(selected|rejected|unreviewed)$")
    note: str = Field(default="", max_length=500)


class SearchRequest(BaseModel):
    candidate_id: str = Field(min_length=8, max_length=64)
    limit: int = Field(default=10, ge=1, le=30)
    threshold: float = Field(default=0.52, ge=0.30, le=0.95)


class SignupRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=12, max_length=256)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class AccountStatusRequest(BaseModel):
    status: str = Field(pattern=r"^(active|disabled)$")


class EvidenceCheckRequest(BaseModel):
    clip_ids: list[str] = Field(default_factory=list, max_length=100)


class DatabaseBackupRequest(BaseModel):
    passphrase: str = Field(min_length=16, max_length=256)


class StreamToggleRequest(BaseModel):
    running: bool


class StreamSourceRequest(BaseModel):
    source: str = Field(max_length=300)


class ManifestVerifyRequest(BaseModel):
    manifest: dict


class JournalMatchRequest(BaseModel):
    clip_id: str = Field(min_length=8, max_length=64)
    clip_start_time: str = Field(min_length=8, max_length=40)
    csv_text: str = Field(min_length=5, max_length=100_000)
    window_seconds: int = Field(default=30, ge=5, le=300)
    auto_queue: bool = False


class WatchlistRequest(BaseModel):
    candidate_id: str = Field(min_length=8, max_length=64)
    label: str = Field(min_length=2, max_length=60)
    case_ref: str = Field(default="", max_length=40)


class LiveEvidenceLabelRequest(BaseModel):
    label: str = Field(min_length=2, max_length=60)


class PromoteLiveRequest(BaseModel):
    label: str = Field(default="", max_length=60)
    case_ref: str = Field(default="", max_length=40)


class CaseDossierRequest(BaseModel):
    fir_number: str = Field(default="", max_length=60)
    ncrp_ack: str = Field(default="", max_length=60)
    police_station: str = Field(default="", max_length=120)
    io_name: str = Field(default="", max_length=80)
    io_badge: str = Field(default="", max_length=40)
    atm_id: str = Field(default="", max_length=60)
    bank_name: str = Field(default="", max_length=80)
    fraud_type: str = Field(default="ATM Cash-Out / Card Fraud", max_length=80)
    loss_inr: int = Field(default=0, ge=0, le=1_000_000_000)
    notes: str = Field(default="", max_length=500)


PUBLIC_AUTH_PATHS = {"/api/health", "/api/auth/bootstrap", "/api/auth/signup", "/api/auth/login", "/api/openapi.json", "/api/docs"}


@app.middleware("http")
async def protect_api(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/") or path in PUBLIC_AUTH_PATHS or request.method == "OPTIONS":
        return await call_next(request)
    session = auth.session_for(request.cookies.get(auth.COOKIE_NAME))
    if not session:
        return JSONResponse({"detail": "Sign in to access the local evidence workspace."}, status_code=401)
    if request.method not in {"GET", "HEAD"}:
        supplied = request.headers.get("x-csrf-token", "")
        if not supplied or not hmac.compare_digest(supplied, session["csrf"]):
            return JSONResponse({"detail": "Session security check failed. Refresh the page and try again."}, status_code=403)
    request.state.session = session
    actor_token = store.AUDIT_ACTOR.set(session["user"]["id"])
    try:
        return await call_next(request)
    finally:
        store.AUDIT_ACTOR.reset(actor_token)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    else:
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
            "media-src 'self' blob:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; "
            "form-action 'self'; frame-ancestors 'none'",
        )
    return response


def require_admin(request: Request) -> dict:
    user = request.state.session["user"]
    if user["role"] != "administrator":
        raise HTTPException(403, "Administrator access is required.")
    return user


@app.get("/api/auth/bootstrap")
def auth_bootstrap(request: Request) -> dict:
    with store.connect() as db:
        count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    has_session = auth.session_for(request.cookies.get(auth.COOKIE_NAME)) is not None
    return {"needsAdministrator": count == 0, "authenticated": has_session}


def _set_session(response: JSONResponse, token: str) -> None:
    response.set_cookie(
        auth.COOKIE_NAME,
        token,
        httponly=True,
        secure=os.environ.get("DRISHTI_COOKIE_SECURE") == "1",
        samesite="strict",
        max_age=auth.SESSION_HOURS * 3600,
        path="/",
    )


@app.post("/api/auth/signup")
def auth_signup(payload: SignupRequest):
    if len(payload.password) < 12:
        raise HTTPException(422, "Use a passphrase with at least 12 characters.")
    try:
        user, token, csrf = auth.create_user(payload.email, payload.display_name, payload.password)
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(409, "An account with this email already exists.") from exc
        raise
    status = 201 if token else 202
    response = JSONResponse({"user": user, "csrfToken": csrf, "approvalRequired": token is None}, status_code=status)
    if token:
        _set_session(response, token)
    return response


@app.post("/api/auth/login")
def auth_login(payload: LoginRequest):
    result, user, token, csrf = auth.login(payload.email, payload.password)
    if result == "pending":
        raise HTTPException(403, "Your account is awaiting administrator approval.")
    if result == "disabled":
        raise HTTPException(403, "This account has been disabled. Contact your administrator.")
    if result == "locked":
        raise HTTPException(429, "Too many sign-in attempts. Wait 15 minutes and try again.")
    if result != "ok":
        raise HTTPException(401, "Email or passphrase is incorrect.")
    response = JSONResponse({"user": user, "csrfToken": csrf})
    _set_session(response, token)
    return response


@app.get("/api/auth/me")
def auth_me(request: Request) -> dict:
    session = request.state.session
    return {"user": session["user"], "csrfToken": session["csrf"]}


@app.post("/api/auth/logout")
def auth_logout(request: Request):
    session = request.state.session
    auth.logout(session["token_hash"], session["user"]["id"])
    response = JSONResponse({"ok": True})
    response.delete_cookie(auth.COOKIE_NAME, path="/", httponly=True, samesite="strict")
    return response


@app.get("/api/auth/users")
def auth_users(request: Request) -> list[dict]:
    require_admin(request)
    with store.connect() as db:
        rows = db.execute("SELECT id,email,display_name,role,status,created_at,approved_at FROM users ORDER BY created_at").fetchall()
    return [
        {
            "id": row["id"],
            "email": row["email"],
            "displayName": row["display_name"],
            "role": row["role"],
            "status": row["status"],
            "createdAt": row["created_at"],
            "approvedAt": row["approved_at"],
        }
        for row in rows
    ]


@app.patch("/api/auth/users/{user_id}")
def auth_update_user(user_id: str, payload: AccountStatusRequest, request: Request) -> dict:
    admin = require_admin(request)
    if user_id == admin["id"] and payload.status != "active":
        raise HTTPException(422, "You cannot disable your own administrator account.")
    with store.connect() as db:
        row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Account not found.")
        approved = now() if payload.status == "active" else row["approved_at"]
        db.execute("UPDATE users SET status=?,approved_at=? WHERE id=?", (payload.status, approved, user_id))
        db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        store.append_audit(db, "account.status_changed", user_id, f"{row['status']} → {payload.status}", now(), actor_id=admin["id"])
        updated = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return auth.public_user(updated)


def _safe_mode(path: Path) -> dict:
    try:
        mode = path.stat().st_mode & 0o777
        return {"restricted": mode & 0o077 == 0, "mode": f"{mode:04o}"}
    except OSError:
        return {"restricted": False, "mode": "unavailable"}


@app.get("/api/security/overview")
def security_overview(request: Request) -> dict:
    require_admin(request)
    cutoff = datetime.now(timezone.utc).replace(microsecond=0).timestamp() - 86400
    cutoff_iso = datetime.fromtimestamp(cutoff, timezone.utc).isoformat(timespec="seconds")
    with store.connect() as db:
        db_check = db.execute("PRAGMA quick_check").fetchone()[0]
        foreign_key_issues = len(db.execute("PRAGMA foreign_key_check").fetchall())
        audit = store.verify_audit(db)
        failed_signins = db.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action IN ('security.login_failed','security.login_denied','security.login_throttled') AND occurred_at>=?",
            (cutoff_iso,),
        ).fetchone()[0]
        pending = db.execute("SELECT COUNT(*) FROM users WHERE status='pending'").fetchone()[0]
        active = db.execute("SELECT COUNT(*) FROM users WHERE status='active'").fetchone()[0]
        clips = db.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
        backup = db.execute("SELECT id,created_at,size_bytes,sha256 FROM security_backups ORDER BY created_at DESC LIMIT 1").fetchone()
        full_check = db.execute("SELECT checked_at,clips_checked,mismatch_count FROM security_evidence_checks ORDER BY checked_at DESC LIMIT 1").fetchone()
    data_mode = _safe_mode(store.DATA)
    db_mode = _safe_mode(store.DB_PATH)
    return {
        "database": {
            "integrity": db_check,
            "foreignKeyViolations": foreign_key_issues,
            "sizeBytes": store.DB_PATH.stat().st_size if store.DB_PATH.exists() else 0,
            "directoryPermissions": data_mode,
            "filePermissions": db_mode,
        },
        "audit": audit,
        "accounts": {"active": active, "pending": pending, "failedSignins24h": failed_signins},
        "evidence": {
            "clipCount": clips,
            "lastFullCheck": (
                {
                    "checkedAt": full_check["checked_at"],
                    "clipsChecked": full_check["clips_checked"],
                    "mismatchCount": full_check["mismatch_count"],
                }
                if full_check
                else None
            ),
        },
        "backup": (
            {"id": backup["id"], "createdAt": backup["created_at"], "sizeBytes": backup["size_bytes"], "sha256": backup["sha256"]}
            if backup
            else None
        ),
        "signingKey": {"present": store.SIGNING_KEY_PATH.is_file(), "permissions": _safe_mode(store.SIGNING_KEY_PATH)},
        "hostEncryption": {
            "status": "verify",
            "message": "Enable FileVault, BitLocker, or LUKS on the host volume; this app does not manage the device key.",
        },
        "networkBoundary": {
            "status": "loopback",
            "message": "The local runner binds to 127.0.0.1; keep reverse proxies and remote access disabled unless formally reviewed.",
        },
    }


@app.post("/api/security/verify-manifest")
def security_verify_manifest(payload: ManifestVerifyRequest, request: Request) -> dict:
    result = verify_manifest(payload.manifest)
    with store.connect() as db:
        store.append_audit(
            db,
            "security.manifest_verified",
            str(payload.manifest.get("analysisId", ""))[:40],
            f"Manifest seal verified={result['verified']}",
            now(),
        )
    return result


@app.get("/api/security/compliance-report.json")
def security_compliance_report(request: Request) -> StreamingResponse:
    admin = require_admin(request)
    with store.connect() as db:
        audit_state = store.verify_audit(db)
        db_check = db.execute("PRAGMA quick_check").fetchone()[0]
        clip_count = db.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
        cand_count = db.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        live_count = db.execute("SELECT COUNT(*) FROM live_identities").fetchone()[0]
        inc_count = db.execute("SELECT COUNT(*) FROM live_incidents").fetchone()[0]
    report = sign_manifest(
        {
            "schema": "drishti.compliance.report.v1",
            "generatedAt": now(),
            "generatedBy": admin["email"],
            "host": socket.gethostname(),
            "frameworks": {
                "bsaSection63": {
                    "ready": bool(audit_state.get("verified")) and store.SIGNING_KEY_PATH.is_file(),
                    "controls": ["SHA-256 Dual Hashing", "HMAC-SHA256 Signed Manifests", "Hash-Chained Audit Ledger", "BSA Sec 63 PDF Export"],
                },
                "dpdpAct2023": {
                    "ready": True,
                    "controls": ["Bystander Gaussian Redaction Export", "Loopback-Only 127.0.0.1 Execution", "Zero External Cloud / Telemetry"],
                },
                "cyberSecurityAndRbiBaseline": {
                    "ready": db_check == "ok",
                    "controls": ["Salted scrypt RBAC", "HttpOnly SameSite=Strict CSRF Sessions", "Hashed Auth Throttle IDs", "AES-256-GCM DB Snapshots", "PIN / PAN Card Exclusion"],
                },
                "openSourceSbom": {
                    "agplFree": True,
                    "models": analysis.model_status(),
                },
            },
            "metrics": {
                "sqliteIntegrity": db_check,
                "auditVerified": bool(audit_state.get("verified")),
                "auditEntries": audit_state.get("entriesChecked", 0),
                "clipsInVault": clip_count,
                "candidatesIndexed": cand_count,
                "liveSubjectsInDb": live_count,
                "liveIncidentsSaved": inc_count,
            },
        }
    )
    with store.connect() as db:
        store.append_audit(db, "security.compliance_exported", admin["id"], "Exported signed Indian Cyber & Privacy compliance report", now())
    return StreamingResponse(
        io.BytesIO(json.dumps(report, indent=2).encode("utf-8")),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="drishti-compliance-report.json"'},
    )


@app.post("/api/security/evidence-check")
def security_evidence_check(payload: EvidenceCheckRequest, request: Request) -> dict:
    require_admin(request)
    with store.connect() as db:
        if payload.clip_ids:
            marks = ",".join("?" for _ in payload.clip_ids)
            rows = db.execute(f"SELECT * FROM clips WHERE id IN ({marks})", payload.clip_ids).fetchall()
        else:
            rows = db.execute("SELECT * FROM clips ORDER BY uploaded_at").fetchall()
    checked, mismatches = 0, []
    for row in rows:
        clip = dict(row)
        source_path, analysis_path = Path(clip["source_path"]), Path(clip["path"])
        source_matches = _matches_sha256(source_path, clip["sha256"])
        analysis_matches = _matches_sha256(analysis_path, clip["analysis_sha256"])
        checked += 1
        if not source_matches or not analysis_matches:
            mismatches.append(
                {
                    "clipId": clip["id"],
                    "filename": clip["filename"],
                    "sourceMatches": bool(source_matches),
                    "analysisMatches": bool(analysis_matches),
                }
            )
    stamp = now()
    with store.connect() as db:
        store.append_audit(
            db,
            "security.evidence_batch_check",
            "all" if not payload.clip_ids else ",".join(payload.clip_ids)[:500],
            f"Checked {checked} clips; {len(mismatches)} integrity mismatch(es)",
            stamp,
        )
        db.execute(
            "INSERT INTO security_evidence_checks(id,checked_by,checked_at,clips_checked,mismatch_count,details_json) VALUES(?,?,?,?,?,?)",
            (uuid.uuid4().hex, request.state.session["user"]["id"], stamp, checked, len(mismatches), json.dumps(mismatches)),
        )
        for mismatch in mismatches:
            db.execute(
                "INSERT INTO events VALUES(?,?,?,?,?,?,?,?)",
                (
                    uuid.uuid4().hex,
                    None,
                    mismatch["clipId"],
                    "evidence.integrity_mismatch",
                    f"Full security check found changed or missing bytes for {mismatch['filename']}",
                    "critical",
                    stamp,
                    json.dumps({"sourceMatches": mismatch["sourceMatches"], "analysisMatches": mismatch["analysisMatches"]}),
                ),
            )
    return {
        "checked": checked,
        "verified": checked - len(mismatches),
        "mismatches": mismatches,
        "checkedAt": stamp,
        "notice": "SHA-256 matches compare local bytes to ingest fingerprints; they do not attest the original recording source.",
    }


@app.get("/api/security/database-backups")
def list_database_backups(request: Request) -> list[dict]:
    require_admin(request)
    with store.connect() as db:
        rows = db.execute("SELECT id,created_at,size_bytes,sha256 FROM security_backups ORDER BY created_at DESC LIMIT 20").fetchall()
    return [
        {"id": row["id"], "createdAt": row["created_at"], "sizeBytes": row["size_bytes"], "sha256": row["sha256"]}
        for row in rows
    ]


@app.post("/api/security/database-backups", status_code=201)
def create_database_backup(payload: DatabaseBackupRequest, request: Request) -> dict:
    admin = require_admin(request)
    backup_id = uuid.uuid4().hex
    filename = f"drishti-db-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{backup_id[:8]}.enc"
    path = store.BACKUPS / filename
    with store.connect() as db:
        store.append_audit(db, "security.database_backup_started", backup_id, "Started consistent SQLite snapshot", now())
    try:
        source = store.connect()
        snapshot = sqlite3.connect(":memory:")
        try:
            source.backup(snapshot)
            check = snapshot.execute("PRAGMA quick_check").fetchone()[0]
            if check != "ok":
                raise RuntimeError("SQLite snapshot did not pass quick_check")
            raw_snapshot = bytearray(snapshot.serialize())
            if len(raw_snapshot) >= 20 and (raw_snapshot[18] == 2 or raw_snapshot[19] == 2):
                # Normalize WAL format bytes (18, 19) to standard rollback v1 for self-contained snapshot portability
                raw_snapshot[18] = 1
                raw_snapshot[19] = 1
            encrypted = encrypt_snapshot(bytes(raw_snapshot), payload.passphrase)
        finally:
            snapshot.close()
            source.close()
        path.write_bytes(encrypted)
        path.chmod(0o600)
        size, digest = path.stat().st_size, _file_sha256(path)
        created = now()
        with store.connect() as db:
            db.execute(
                "INSERT INTO security_backups(id,filename,created_by,created_at,size_bytes,sha256) VALUES(?,?,?,?,?,?)",
                (backup_id, filename, admin["id"], created, size, digest),
            )
            store.append_audit(
                db,
                "security.database_backup_created",
                backup_id,
                f"Encrypted SQLite quick_check=ok; AES-256-GCM; {size} bytes; SHA-256 {digest}",
                created,
            )
        return {
            "id": backup_id,
            "createdAt": created,
            "sizeBytes": size,
            "sha256": digest,
            "downloadUrl": f"/api/security/database-backups/{backup_id}",
            "scope": "Passphrase-encrypted SQLite metadata snapshot only; video files and candidate images are not included.",
        }
    except Exception as exc:
        path.unlink(missing_ok=True)
        with store.connect() as db:
            store.append_audit(db, "security.database_backup_failed", backup_id, "SQLite snapshot failed validation or write", now())
        raise HTTPException(500, "Database snapshot failed. Review the security audit and available disk space.") from exc


@app.get("/api/security/database-backups/{backup_id}")
def download_database_backup(backup_id: str, request: Request) -> FileResponse:
    admin = require_admin(request)
    with store.connect() as db:
        row = db.execute("SELECT * FROM security_backups WHERE id=?", (backup_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Database snapshot not found.")
        path = store.BACKUPS / row["filename"]
        if not _matches_sha256(path, row["sha256"]):
            store.append_audit(db, "security.database_backup_mismatch", backup_id, "Snapshot missing or hash mismatch", now())
            raise HTTPException(409, "Snapshot integrity check failed; do not use this backup.")
        store.append_audit(
            db, "security.database_backup_downloaded", backup_id, "Administrator downloaded metadata snapshot", now(), actor_id=admin["id"]
        )
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=row["filename"],
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "local",
        "service": APP_NAME,
        "models": analysis.model_status(),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
        "cloud": "disabled",
    }


@app.get("/api/dvr-guidance")
def dvr_guidance() -> dict:
    return {"supportedExtensions": sorted(ALLOWED_EXTENSIONS), "guidance": forensics.DVR_EXPORT_GUIDANCE}


@app.get("/api/overview")
def overview() -> dict:
    with store.connect() as db:
        clips = db.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
        analyses = db.execute("SELECT COUNT(*) FROM analyses WHERE status='completed'").fetchone()[0]
        candidates = db.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        pending = db.execute("SELECT COUNT(*) FROM analyses WHERE status IN ('queued','running')").fetchone()[0]
        latest = db.execute("SELECT id,status,transaction_time,created_at FROM analyses ORDER BY created_at DESC LIMIT 1").fetchone()
        return {
            "clips": clips,
            "analyses": analyses,
            "candidates": candidates,
            "pending": pending,
            "latest": dict(latest) if latest else None,
        }


@app.get("/api/clips")
def list_clips() -> list[dict]:
    with store.connect() as db:
        rows = db.execute("SELECT * FROM clips ORDER BY uploaded_at DESC").fetchall()
    return [_public_clip(dict(r)) for r in rows]


@app.get("/api/cameras")
def camera_slots() -> list[dict]:
    labels = {"ATM-01": "Entry view", "ATM-02": "Keypad view", "ATM-03": "Cash slot", "ATM-04": "Exit view"}
    clips = list_clips()
    return [
        {
            "id": camera_id,
            "label": label,
            "clips": [clip for clip in clips if clip["cameraId"] == camera_id],
            "status": "recorded" if any(clip["cameraId"] == camera_id for clip in clips) else "awaiting clip",
            "source": "local file",
        }
        for camera_id, label in labels.items()
    ]


@app.post("/api/clips", status_code=201)
async def upload_clip(request: Request, filename: str, camera_id: str = "ATM-01", replace_clip_id: str = "") -> dict:
    original = Path(filename).name.strip()
    suffix = Path(original).suffix.lower()
    if camera_id not in {"ATM-01", "ATM-02", "ATM-03", "ATM-04"}:
        raise HTTPException(422, "Choose one of the four local ATM camera channels.")
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, "Use MP4, AVI, MOV, MKV, WMV, FLV, MPEG, MPG, or compatible DAV/H264/TS DVR exports.")
    if replace_clip_id:
        try:
            delete_clip(replace_clip_id)
        except HTTPException:
            pass
    clip_id = uuid.uuid4().hex
    path = store.UPLOADS / f"{clip_id}{suffix}"
    size = 0
    try:
        with path.open("wb") as output:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "Maximum clip size is 500 MB.")
                output.write(chunk)
        if size == 0:
            raise HTTPException(400, "The uploaded clip is empty.")
        # Reuse ingest pipeline without extra copy
        source_digest = _file_sha256(path)
        source_info = _inspect_video(path)
        normalized = store.UPLOADS / f"{clip_id}-normalized.mp4"
        if source_info is None:
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                raise HTTPException(422, "This file could not be decoded. Install FFmpeg and export it as MP4/H.264.")
            _transcode_review_copy(path, normalized, ffmpeg)
            source_info = _inspect_video(normalized)
            if source_info is None:
                raise HTTPException(422, "FFmpeg could not normalize this export. Check the DVR/NVR export settings.")
            playable_path = normalized
            preview_ready = True
            playback_codec = source_info["codec"]
        else:
            playable_path = path
            codec_name = source_info["codec"].lower()
            suffix_name = suffix.lower()
            browser_codec = (suffix_name == ".mp4" and codec_name in {"avc1", "h264", "x264"}) or (
                suffix_name == ".webm" and codec_name in {"vp80", "vp90", "vp09", "av01"}
            )
            ffmpeg = shutil.which("ffmpeg")
            if not browser_codec and ffmpeg:
                _transcode_review_copy(path, normalized, ffmpeg)
                playable_path = normalized
                playback_info = _inspect_video(playable_path)
                if playback_info is None:
                    raise HTTPException(422, "The converted playback copy could not be decoded.")
                playback_codec = playback_info["codec"]
                preview_ready = True
            else:
                playback_codec = source_info["codec"]
                preview_ready = browser_codec

        width, height = source_info["width"], source_info["height"]
        fps, duration, codec = source_info["fps"], source_info["duration"], source_info["codec"]
        analysis_digest = _file_sha256(playable_path)
        forensics_payload = {
            "container": forensics.probe_video_container(path),
            "continuity": forensics.check_frame_continuity(playable_path),
        }
        record = {
            "id": clip_id,
            "filename": original[:180],
            "camera_id": camera_id,
            "path": str(playable_path),
            "source_path": str(path),
            "size_bytes": size,
            "duration": round(duration, 3),
            "width": width,
            "height": height,
            "fps": round(fps, 3),
            "codec": codec,
            "playback_codec": playback_codec,
            "preview_ready": int(preview_ready),
            "sha256": source_digest,
            "analysis_sha256": analysis_digest,
            "forensics_json": json.dumps(forensics_payload),
            "uploaded_at": now(),
        }
        with store.connect() as db:
            db.execute(
                """INSERT INTO clips(id,filename,camera_id,path,source_path,size_bytes,duration,
                   width,height,fps,codec,playback_codec,preview_ready,sha256,analysis_sha256,forensics_json,uploaded_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                tuple(record.values()),
            )
            store.append_audit(
                db,
                "clip.uploaded",
                clip_id,
                f"Local clip uploaded: {original[:100]} ({size} bytes, SHA-256 {source_digest[:16]}…)",
                now(),
            )
        return _public_clip(record)
    except Exception:
        path.unlink(missing_ok=True)
        normalized_path = store.UPLOADS / f"{clip_id}-normalized.mp4"
        normalized_path.unlink(missing_ok=True)
        raise


@app.get("/api/clips/{clip_id}/video")
def clip_video(clip_id: str) -> FileResponse:
    clip = _clip_or_404(clip_id)
    media_type = mimetypes.guess_type(clip["path"])[0] or "video/mp4"
    return FileResponse(
        clip["path"],
        media_type=media_type,
        filename=clip["filename"],
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"},
    )


@app.get("/api/clips/{clip_id}/poster")
def clip_poster(clip_id: str) -> StreamingResponse:
    clip = _clip_or_404(clip_id)
    cap = cv2.VideoCapture(clip["path"])
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise HTTPException(422, "Could not decode the first frame.")
    ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
    if not ok:
        raise HTTPException(500, "Could not render a preview.")
    return StreamingResponse(io.BytesIO(jpg.tobytes()), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=600"})


@app.delete("/api/clips/{clip_id}")
def delete_clip(clip_id: str) -> dict:
    clip = _clip_or_404(clip_id)
    with store.connect() as db:
        crops = [row[0] for row in db.execute("SELECT image_path FROM candidates WHERE clip_id=?", (clip_id,))]
        analysis_ids = [row[0] for row in db.execute("SELECT id FROM analyses WHERE clip_id=?", (clip_id,))]
        db.execute("DELETE FROM candidates WHERE clip_id=?", (clip_id,))
        db.execute("DELETE FROM events WHERE clip_id=?", (clip_id,))
        db.execute("DELETE FROM analyses WHERE clip_id=?", (clip_id,))
        db.execute("DELETE FROM clips WHERE id=?", (clip_id,))
        store.append_audit(db, "clip.deleted", clip_id, f"Removed local clip {clip['filename']}", now())
    Path(clip["path"]).unlink(missing_ok=True)
    Path(clip["source_path"]).unlink(missing_ok=True)
    for crop in crops:
        Path(crop).unlink(missing_ok=True)
    return {"deleted": clip_id, "removedAnalyses": len(analysis_ids)}


@app.get("/api/clips/{clip_id}/integrity")
def clip_integrity(clip_id: str) -> dict:
    clip = _clip_or_404(clip_id)
    source_path = Path(clip["source_path"])
    analyzed_path = Path(clip["path"])
    source_ok = _matches_sha256(source_path, clip["sha256"])
    analyzed_ok = _matches_sha256(analyzed_path, clip["analysis_sha256"])
    verified = source_ok and analyzed_ok
    with store.connect() as db:
        store.append_audit(
            db,
            "clip.integrity_checked",
            clip_id,
            "SHA-256 verified against ingest fingerprints" if verified else "SHA-256 mismatch or missing local evidence file",
            now(),
        )
        if not verified:
            db.execute(
                "INSERT INTO events VALUES(?,?,?,?,?,?,?,?)",
                (
                    uuid.uuid4().hex,
                    None,
                    clip_id,
                    "evidence.integrity_mismatch",
                    f"SHA-256 verification failed for {clip['filename']}",
                    "warning",
                    now(),
                    json.dumps({"sourceMatches": source_ok, "analysisMatches": analyzed_ok}),
                ),
            )
    return {
        "clipId": clip_id,
        "filename": clip["filename"],
        "verified": verified,
        "sourceMatches": source_ok,
        "analysisMatches": analyzed_ok,
        "sourceSha256": clip["sha256"],
        "analysisSha256": clip["analysis_sha256"],
        "normalized": clip["sha256"] != clip["analysis_sha256"],
        "checkedAt": now(),
        "notice": "Hash match shows these local bytes match their ingest fingerprints; it does not prove who recorded the source footage.",
    }


def _queue_analysis_job(clip: dict, payload: AnalysisRequest) -> dict:
    if analysis_pool is None:
        raise HTTPException(503, "Local analysis worker is not ready. Restart the service and retry.")
    if payload.time_mode == "clip":
        try:
            seconds = analysis._time_seconds(payload.transaction_time)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    else:
        try:
            seconds = analysis.transaction_offset(payload.model_dump())
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, str(exc)) from exc
    if seconds >= clip["duration"]:
        raise HTTPException(422, "Transaction time must fall within the clip duration.")
    job_id = uuid.uuid4().hex
    stamp = now()
    with store.connect() as db:
        db.execute(
            """INSERT INTO analyses(id,clip_id,transaction_time,time_mode,clip_start_time,transaction_ref,
               case_ref,window_seconds,status,result_json,error,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job_id,
                clip["id"],
                payload.transaction_time,
                payload.time_mode,
                payload.clip_start_time,
                payload.transaction_ref.strip(),
                payload.case_ref.strip(),
                payload.window_seconds,
                "running",
                "{}",
                "",
                stamp,
                stamp,
            ),
        )
        store.append_audit(
            db,
            "analysis.queued",
            job_id,
            f"Queued analysis of {clip['filename']} ({clip['camera_id']}) within ±{payload.window_seconds}s of {payload.transaction_time}. "
            f"Time mode: {payload.time_mode}. Case: {payload.case_ref.strip() or 'unassigned'}. "
            f"Transaction: {payload.transaction_ref.strip() or 'unassigned'}.",
            stamp,
        )
    analysis_context = contextvars.copy_context()
    analysis_pool.submit(analysis_context.run, analysis.run_analysis, job_id)
    return {"id": job_id, "status": "running", "clipId": clip["id"], "transactionTime": payload.transaction_time}


@app.post("/api/analyses", status_code=202)
def create_analysis(payload: AnalysisRequest) -> dict:
    clip = _clip_or_404(payload.clip_id)
    return _queue_analysis_job(clip, payload)


@app.get("/api/analyses")
def list_analyses() -> list[dict]:
    with store.connect() as db:
        rows = db.execute(
            """SELECT a.*, c.filename FROM analyses a JOIN clips c ON c.id=a.clip_id
               ORDER BY a.created_at DESC LIMIT 100"""
        ).fetchall()
        analysis_ids = [r["id"] for r in rows]
        candidates_by_analysis: dict[str, list[dict]] = {key: [] for key in analysis_ids}
        if analysis_ids:
            marks = ",".join("?" for _ in analysis_ids)
            candidates = db.execute(f"SELECT * FROM candidates WHERE analysis_id IN ({marks}) ORDER BY score DESC", analysis_ids).fetchall()
            for candidate in candidates:
                candidates_by_analysis[candidate["analysis_id"]].append(_public_candidate(dict(candidate)))
    return [
        {
            "id": r["id"],
            "clipId": r["clip_id"],
            "clipName": r["filename"],
            "filename": r["filename"],
            "transactionTime": r["transaction_time"],
            "transactionRef": r["transaction_ref"],
            "caseRef": r["case_ref"] if "case_ref" in r.keys() else "",
            "timeMode": r["time_mode"],
            "clipStartTime": r["clip_start_time"],
            "windowSeconds": r["window_seconds"],
            "status": r["status"],
            "error": r["error"],
            "createdAt": r["created_at"],
            "result": store.json_load(r["result_json"], {}),
            "candidates": candidates_by_analysis[r["id"]],
        }
        for r in rows
    ]


@app.get("/api/analyses/{analysis_id}")
def get_analysis(analysis_id: str) -> dict:
    with store.connect() as db:
        row = store.row_dict(db.execute("SELECT * FROM analyses WHERE id=?", (analysis_id,)).fetchone())
        if not row:
            raise HTTPException(404, "Analysis not found")
        clip = store.row_dict(db.execute("SELECT * FROM clips WHERE id=?", (row["clip_id"],)).fetchone())
        candidates = db.execute("SELECT * FROM candidates WHERE analysis_id=? ORDER BY score DESC", (analysis_id,)).fetchall()
    return {
        "id": row["id"],
        "clipId": row["clip_id"],
        "clipName": clip["filename"],
        "transactionTime": row["transaction_time"],
        "transactionRef": row["transaction_ref"],
        "caseRef": row.get("case_ref", ""),
        "timeMode": row["time_mode"],
        "clipStartTime": row["clip_start_time"],
        "windowSeconds": row["window_seconds"],
        "status": row["status"],
        "error": row["error"],
        "createdAt": row["created_at"],
        "result": store.json_load(row["result_json"], {}),
        "candidates": [_public_candidate(dict(c)) for c in candidates],
    }


@app.get("/api/candidates/{candidate_id}/image")
def candidate_image(candidate_id: str) -> FileResponse:
    candidate = _candidate_or_404(candidate_id)
    return FileResponse(
        candidate["image_path"],
        media_type="image/jpeg",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"},
    )


@app.get("/api/candidates/{candidate_id}/enhanced")
def candidate_enhanced(candidate_id: str, label: int = 1) -> StreamingResponse:
    candidate = _candidate_or_404(candidate_id)
    face_bgr = cv2.imread(candidate["image_path"])
    if face_bgr is None:
        raise HTTPException(404, "Candidate face file missing.")
    enhanced = forensics.enhance_face_crop(face_bgr, label=bool(label))
    ok, jpg = cv2.imencode(".jpg", enhanced, [cv2.IMWRITE_JPEG_QUALITY, 94])
    if not ok:
        raise HTTPException(500, "Could not encode enhanced image.")
    return StreamingResponse(
        io.BytesIO(jpg.tobytes()),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Forensic-Enhancement": "CLAHE-Bilateral-Unsharp-2x-ReviewOnly",
        },
    )


@app.get("/api/candidates/{candidate_id}/frame-redacted")
def candidate_frame_redacted(candidate_id: str) -> StreamingResponse:
    candidate = _candidate_or_404(candidate_id)
    clip = _clip_or_404(candidate["clip_id"])
    detector = None
    try:
        detector = analysis.new_face_detector()
    except RuntimeError:
        pass
    bbox = store.json_load(candidate.get("bbox_json"), [])
    try:
        jpeg_bytes = forensics.redact_bystanders_frame(
            Path(clip["path"]),
            float(candidate["frame_seconds"]),
            bbox if isinstance(bbox, list) else None,
            detector,
            clip["sha256"],
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with store.connect() as db:
        store.append_audit(
            db,
            "candidate.privacy_frame_exported",
            candidate_id,
            f"Exported bystander-redacted frame at t={candidate['frame_seconds']}s",
            now(),
        )
    return StreamingResponse(
        io.BytesIO(jpeg_bytes),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'inline; filename="redacted-{candidate_id[:12]}.jpg"',
        },
    )


@app.patch("/api/candidates/{candidate_id}/review")
def review_candidate(candidate_id: str, payload: ReviewRequest) -> dict:
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        candidate = db.execute("SELECT * FROM candidates WHERE id=?", (candidate_id,)).fetchone()
        if candidate is None:
            raise HTTPException(404, "Candidate not found.")
        db.execute("UPDATE candidates SET review_status=?, note=? WHERE id=?", (payload.status, payload.note.strip(), candidate_id))
        store.append_audit(
            db, f"candidate.{payload.status}", candidate_id,
            f"Candidate at {candidate['frame_seconds']:.3f}s in analysis {candidate['analysis_id']}. "
            f"Review status: {candidate['review_status']} → {payload.status}. "
            f"Investigator note: {payload.note.strip() or '(empty)'}", now(),
        )
    return {"id": candidate_id, "status": payload.status, "analysisId": candidate["analysis_id"]}


@app.post("/api/search")
def search_candidate(payload: SearchRequest) -> dict:
    query = _candidate_or_404(payload.candidate_id)
    target = store.json_load(query["descriptor_json"], [])
    if not target:
        raise HTTPException(422, "This candidate has no searchable descriptor.")
    with store.connect() as db:
        rows = db.execute(
            """SELECT c.*, clips.filename FROM candidates c JOIN clips ON clips.id=c.clip_id
               WHERE c.clip_id != ? ORDER BY c.score DESC LIMIT 1000""",
            (query["clip_id"],),
        ).fetchall()
    matches = []
    for row in rows:
        candidate = dict(row)
        vector = store.json_load(candidate["descriptor_json"], [])
        score = analysis.descriptor_similarity(target, vector)
        if score is not None and score >= payload.threshold:
            matches.append({**_public_candidate(candidate), "similarity": round(score * 100, 1), "filename": candidate["filename"]})
    matches.sort(key=lambda item: item["similarity"], reverse=True)
    method = "SFace 128-D face embedding cosine similarity" if len(target) == 128 else "Local grayscale histogram similarity"
    with store.connect() as db:
        store.append_audit(
            db,
            "candidate.search",
            query["id"],
            f"{method} across {len({m['clipId'] for m in matches})} clips ({len(matches)} hits >= {int(payload.threshold * 100)}%)",
            now(),
        )
    return {
        "queryCandidateId": query["id"],
        "embeddingType": "sface_128d" if len(target) == 128 else "hist_32",
        "matches": matches[: payload.limit],
        "notice": f"{method}. Results are review candidates only — not identity verification or guilt confirmation.",
    }


@app.post("/api/journal/match")
def match_transaction_journal(payload: JournalMatchRequest) -> dict:
    clip = _clip_or_404(payload.clip_id)
    try:
        clip_start = datetime.fromisoformat(payload.clip_start_time.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(422, "Invalid clip_start_time ISO format.") from exc

    reader = csv.DictReader(io.StringIO(payload.csv_text.strip()))
    matched_rows = []
    queued_ids = []
    for idx, row in enumerate(reader, start=1):
        norm = {str(k).strip().lower(): str(v or "").strip() for k, v in row.items() if k is not None}
        ts_raw = norm.get("timestamp") or norm.get("time") or norm.get("txn_time") or ""
        txn_ref = norm.get("txn_ref") or norm.get("reference") or norm.get("rrn") or f"ROW-{idx}"
        status = norm.get("status") or norm.get("type") or "WITHDRAWAL"
        atm_id = norm.get("atm_id") or clip["camera_id"]
        if not ts_raw:
            continue
        try:
            txn_dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            cmp_start = clip_start
            # Compare in wall-clock local time if either timestamp omits timezone offset
            if txn_dt.tzinfo is None and cmp_start.tzinfo is not None:
                cmp_start = cmp_start.replace(tzinfo=None)
            elif txn_dt.tzinfo is not None and cmp_start.tzinfo is None:
                txn_dt = txn_dt.replace(tzinfo=None)
            offset = int((txn_dt - cmp_start).total_seconds())
        except ValueError:
            offset = -1
        in_clip = 0 <= offset < float(clip["duration"])
        disputed = any(word in status.lower() for word in ("dispute", "fraud", "skim", "suspect", "alert", "fail"))
        item = {
            "row": idx,
            "timestamp": ts_raw,
            "txnRef": txn_ref,
            "atmId": atm_id,
            "status": status,
            "offsetSeconds": offset,
            "inClip": in_clip,
            "disputed": disputed,
        }
        if in_clip and payload.auto_queue and (disputed or len(queued_ids) == 0):
            job = _queue_analysis_job(
                clip,
                AnalysisRequest(
                    clip_id=clip["id"],
                    transaction_time=ts_raw,
                    time_mode="absolute",
                    clip_start_time=payload.clip_start_time,
                    transaction_ref=txn_ref,
                    case_ref=f"EJ-{txn_ref[:16]}",
                    window_seconds=payload.window_seconds,
                ),
            )
            item["analysisId"] = job["id"]
            queued_ids.append(job["id"])
        matched_rows.append(item)

    with store.connect() as db:
        store.append_audit(
            db,
            "journal.matched",
            clip["id"],
            f"Matched {sum(1 for r in matched_rows if r['inClip'])}/{len(matched_rows)} ATM journal row(s); queued {len(queued_ids)}",
            now(),
        )
    return {
        "clipId": clip["id"],
        "clipFilename": clip["filename"],
        "totalRows": len(matched_rows),
        "inClipCount": sum(1 for r in matched_rows if r["inClip"]),
        "queuedAnalyses": queued_ids,
        "rows": matched_rows[:100],
    }


@app.post("/api/demo/load")
def load_demo_dataset() -> dict:
    """Ingest clearly labelled local synthetic/pilot clips for immediate hackathon demo."""
    created_clips = []
    feed_map = [
        ("ATM-01", "demo_atm_vestibule.mp4", store.DEMO_FEEDS / "cam_01_vestibule.mp4"),
        ("ATM-02", "demo_atm_keypad.mp4", store.DEMO_FEEDS / "cam_02_keypad.mp4"),
    ]
    existing = {c["filename"]: c for c in list_clips()}
    for cam_id, target_name, src in feed_map:
        if target_name in existing:
            created_clips.append(existing[target_name])
        elif src.is_file():
            created_clips.append(_ingest_local_file(src, target_name, cam_id))
    with store.connect() as db:
        store.append_audit(db, "demo.loaded", "hackathon-ps04", f"Loaded {len(created_clips)} local demo clips", now())
    sample_journal = (
        "timestamp,txn_ref,atm_id,status\n"
        "2026-11-26T14:20:06,TXN-RJP-8841,ATM-02,DISPUTED_SKIM_ALERT\n"
        "2026-11-26T14:20:14,TXN-RJP-8842,ATM-02,CASH_WITHDRAWAL\n"
        "2026-11-26T14:25:00,TXN-RJP-8849,ATM-02,OUTSIDE_WINDOW\n"
    )
    return {
        "clips": created_clips,
        "recommendedClipStart": "2026-11-26T14:20:00",
        "recommendedClipTime": "00:00:04",
        "sampleJournalCsv": sample_journal,
        "notice": "Clearly labelled local pilot/demo footage loaded. No real personal data or live bank connection.",
    }


@app.get("/api/streams")
def stream_status() -> dict:
    return streams.manager.status()


@app.post("/api/streams/toggle")
def toggle_streams(payload: StreamToggleRequest) -> dict:
    if payload.running:
        streams.manager.start()
        action = "streams.started"
        note = "Started 4-stream local person-detection surveillance pilot"
    else:
        streams.manager.stop()
        action = "streams.stopped"
        note = "Stopped 4-stream local surveillance pilot"
    with store.connect() as db:
        store.append_audit(db, action, "4-stream-wall", note, now())
    return streams.manager.status()


@app.get("/api/streams/detections")
def stream_detections(limit: int = 40) -> list[dict]:
    with store.connect() as db:
        rows = db.execute("SELECT * FROM stream_detections ORDER BY occurred_at DESC LIMIT ?", (max(1, min(limit, 200)),)).fetchall()
    return [
        {
            "id": r["id"],
            "cameraId": r["camera_id"],
            "trackId": r["track_id"],
            "personCount": r["person_count"],
            "confidence": round(float(r["confidence"]) * 100, 1),
            "alertKind": r["alert_kind"],
            "occurredAt": r["occurred_at"],
            "details": store.json_load(r["details_json"], {}),
        }
        for r in rows
    ]


@app.get("/api/streams/{stream_id}/frame.jpg")
def stream_snapshot(stream_id: str) -> StreamingResponse:
    try:
        jpg = streams.manager.snapshot_jpeg(stream_id)
    except KeyError as exc:
        raise HTTPException(404, "Unknown stream ID.") from exc
    return StreamingResponse(io.BytesIO(jpg), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/api/streams/{stream_id}/mjpeg")
def stream_mjpeg(stream_id: str) -> StreamingResponse:
    if stream_id not in {item["id"] for item in streams.STREAM_CATALOG}:
        raise HTTPException(404, "Unknown stream ID.")
    return StreamingResponse(
        streams.manager.async_mjpeg_generator(stream_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/streams/{stream_id}/latest-face.jpg")
def stream_latest_face(stream_id: str) -> StreamingResponse:
    try:
        jpg = streams.manager.latest_face_jpeg(stream_id)
    except KeyError as exc:
        raise HTTPException(404, "Unknown stream ID.") from exc
    if not jpg:
        raise HTTPException(404, "No live face capture on this stream yet.")
    return StreamingResponse(io.BytesIO(jpg), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.post("/api/streams/{stream_id}/source")
def set_stream_source(stream_id: str, payload: StreamSourceRequest) -> dict:
    try:
        status = streams.manager.set_custom_source(stream_id, payload.source)
    except KeyError as exc:
        raise HTTPException(404, "Unknown stream ID.") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with store.connect() as db:
        source = payload.source.strip()
        if source.lower() == "clear":
            detail = "Cleared camera slot."
        elif source.lower() in ("", "default"):
            detail = "Restored the default camera slot source."
        elif source.isdigit():
            detail = f"Configured local camera device {source}."
        else:
            scheme = source.split(":", 1)[0].upper()
            detail = f"Configured {scheme} camera source. Connection is verified separately by frame delivery."
        store.append_audit(db, "streams.source_changed", stream_id, detail, now())
    return status


@app.post("/api/streams/{stream_id}/capture")
def capture_stream_to_case(stream_id: str) -> dict:
    item = next((s for s in streams.STREAM_CATALOG if s["id"] == stream_id), None)
    if not item:
        raise HTTPException(404, "Unknown stream ID.")
    temp_capture = store.UPLOADS / f"live-buf-{uuid.uuid4().hex}.mp4"
    used_live_buffer = False
    try:
        if streams.manager.export_live_buffer(stream_id, temp_capture):
            used_live_buffer = True
            clip = _ingest_local_file(
                temp_capture,
                f"live-{stream_id.lower()}-{datetime.now(timezone.utc).strftime('%H%M%S')}.mp4",
                item["channelId"],
            )
        else:
            feed_file = item.get("feedFile", "")
            src = (store.DEMO_FEEDS / feed_file) if feed_file else None
            if src is None or not src.is_file():
                raise HTTPException(422, f"{stream_id} has no assigned video or live IP Webcam feed yet.")
            clip = _ingest_local_file(
                src,
                f"capture-{stream_id.lower()}-{datetime.now(timezone.utc).strftime('%H%M%S')}.mp4",
                item["channelId"],
            )
    finally:
        temp_capture.unlink(missing_ok=True)
    with store.connect() as db:
        store.append_audit(
            db,
            "streams.captured_to_case",
            clip["id"],
            f"Captured {'live IP/buffered stream' if used_live_buffer else 'pilot feed'} {stream_id} into {item['channelId']}",
            now(),
        )
    return clip


@app.post("/api/events/clear-stream-alerts")
def clear_stream_alerts() -> dict:
    with store.connect() as db:
        cur = db.execute("DELETE FROM events WHERE kind LIKE 'stream.%'")
        store.append_audit(db, "streams.alerts_cleared", "4-stream-wall", f"Cleared {cur.rowcount} stream alert notification(s)", now())
    return {"cleared": cur.rowcount}


@app.get("/api/watchlist")
def list_watchlist() -> list[dict]:
    with store.connect() as db:
        rows = db.execute("SELECT * FROM case_watchlist ORDER BY created_at DESC").fetchall()
    return [
        {
            "id": r["id"],
            "label": r["label"],
            "caseRef": r["case_ref"],
            "candidateId": r["candidate_id"],
            "clipId": r["clip_id"],
            "createdAt": r["created_at"],
            "imageUrl": f"/api/watchlist/{r['id']}/image",
        }
        for r in rows
    ]


@app.post("/api/watchlist", status_code=201)
def add_to_watchlist(payload: WatchlistRequest) -> dict:
    cand = _candidate_or_404(payload.candidate_id)
    descriptor = store.json_load(cand["descriptor_json"], [])
    if not descriptor:
        raise HTTPException(422, "Selected candidate has no face embedding.")
    entry_id = uuid.uuid4().hex
    stamp = now()
    with store.connect() as db:
        db.execute(
            "INSERT INTO case_watchlist VALUES(?,?,?,?,?,?,?,?)",
            (
                entry_id,
                payload.label.strip(),
                payload.case_ref.strip(),
                cand["id"],
                cand["clip_id"],
                cand["descriptor_json"],
                cand["image_path"],
                stamp,
            ),
        )
        store.append_audit(
            db,
            "watchlist.flagged",
            entry_id,
            f"Flagged local case suspect '{payload.label.strip()}' for live cross-camera SFace alerting",
            stamp,
        )
    return {
        "id": entry_id,
        "label": payload.label.strip(),
        "caseRef": payload.case_ref.strip(),
        "candidateId": cand["id"],
        "clipId": cand["clip_id"],
        "createdAt": stamp,
        "imageUrl": f"/api/watchlist/{entry_id}/image",
    }


@app.get("/api/watchlist/{entry_id}/image")
def watchlist_image(entry_id: str) -> FileResponse:
    with store.connect() as db:
        row = db.execute("SELECT image_path FROM case_watchlist WHERE id=?", (entry_id,)).fetchone()
    if not row or not Path(row["image_path"]).is_file():
        raise HTTPException(404, "Watchlist image not found.")
    return FileResponse(row["image_path"], media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@app.delete("/api/watchlist/{entry_id}")
def delete_watchlist(entry_id: str) -> dict:
    with store.connect() as db:
        cur = db.execute("DELETE FROM case_watchlist WHERE id=?", (entry_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Watchlist entry not found.")
        store.append_audit(db, "watchlist.removed", entry_id, "Removed suspect from local live watchlist", now())
    return {"deleted": entry_id}


def _safe_live_evidence_path(raw_path: str) -> Path | None:
    try:
        resolved = Path(raw_path).resolve()
        if resolved.is_relative_to(store.LIVE_EVIDENCE.resolve()) and resolved.is_file():
            return resolved
    except (OSError, ValueError):
        pass
    return None


@app.get("/api/live-evidence")
def list_live_evidence(limit: int = 40) -> dict:
    capped = max(1, min(limit, 100))
    with store.connect() as db:
        totals = db.execute(
            """SELECT COUNT(*) AS subjects,
                      SUM(CASE WHEN appearance_count >= 2 THEN 1 ELSE 0 END) AS repeats,
                      COALESCE(SUM(sighting_count), 0) AS sightings
               FROM live_identities"""
        ).fetchone()
        rows = db.execute(
            """SELECT * FROM live_identities
               ORDER BY CASE WHEN appearance_count >= 2 THEN 0 ELSE 1 END,
                        appearance_count DESC,
                        last_seen_at DESC
               LIMIT ?""",
            (capped,),
        ).fetchall()
        subjects = []
        for r in rows:
            s_rows = db.execute(
                "SELECT * FROM live_sightings WHERE identity_id=? ORDER BY occurred_at DESC LIMIT 6",
                (r["id"],),
            ).fetchall()
            subjects.append(
                {
                    "id": r["id"],
                    "subjectCode": r["subject_code"],
                    "label": r["label"],
                    "bestScore": round(float(r["best_score"]), 1),
                    "bestSha256": r["best_sha256"],
                    "firstCameraId": r["first_camera_id"],
                    "lastCameraId": r["last_camera_id"],
                    "cameras": store.json_load(r["cameras_json"], []),
                    "flags": store.json_load(r["flags_json"], []),
                    "sightingCount": int(r["sighting_count"]),
                    "appearanceCount": int(r["appearance_count"]),
                    "isRepeat": int(r["appearance_count"]) >= 2,
                    "firstSeenAt": r["first_seen_at"],
                    "lastSeenAt": r["last_seen_at"],
                    "imageUrl": f"/api/live-evidence/{r['id']}/image",
                    "sightings": [
                        {
                            "id": s["id"],
                            "cameraId": s["camera_id"],
                            "score": round(float(s["score"]), 1),
                            "similarity": round(float(s["similarity"]), 1),
                            "sha256": s["sha256"],
                            "occurredAt": s["occurred_at"],
                            "imageUrl": f"/api/live-evidence/sightings/{s['id']}/image",
                        }
                        for s in s_rows
                    ],
                }
            )
    return {
        "summary": {
            "totalSubjects": int(totals["subjects"] or 0),
            "repeatSubjects": int(totals["repeats"] or 0),
            "totalSightings": int(totals["sightings"] or 0),
        },
        "subjects": subjects,
    }


@app.get("/api/live-evidence/{identity_id}/image")
def live_evidence_image(identity_id: str) -> FileResponse:
    with store.connect() as db:
        row = db.execute("SELECT best_image_path FROM live_identities WHERE id=?", (identity_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Live evidence subject not found.")
    path = _safe_live_evidence_path(row["best_image_path"])
    if not path:
        raise HTTPException(404, "Live evidence image not found on disk.")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@app.get("/api/live-evidence/sightings/{sighting_id}/image")
def live_sighting_image(sighting_id: str) -> FileResponse:
    with store.connect() as db:
        row = db.execute("SELECT image_path FROM live_sightings WHERE id=?", (sighting_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Live sighting not found.")
    path = _safe_live_evidence_path(row["image_path"])
    if not path:
        raise HTTPException(404, "Sighting image not found on disk.")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@app.patch("/api/live-evidence/{identity_id}")
def update_live_evidence(identity_id: str, payload: LiveEvidenceLabelRequest) -> dict:
    clean_label = payload.label.strip()
    with store.connect() as db:
        cur = db.execute("UPDATE live_identities SET label=? WHERE id=?", (clean_label, identity_id))
        if cur.rowcount == 0:
            raise HTTPException(404, "Live evidence subject not found.")
        store.append_audit(db, "live_evidence.renamed", identity_id, f"Renamed live subject to '{clean_label}'", now())
    streams.manager.invalidate_evidence_cache()
    return {"id": identity_id, "label": clean_label}


@app.post("/api/live-evidence/{identity_id}/watchlist", status_code=201)
def promote_live_to_watchlist(identity_id: str, payload: PromoteLiveRequest) -> dict:
    with store.connect() as db:
        row = db.execute("SELECT * FROM live_identities WHERE id=?", (identity_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Live evidence subject not found.")
    entry_id = uuid.uuid4().hex
    stamp = now()
    label = payload.label.strip() or f"{row['subject_code']} ({row['label']})"[:60]
    case_ref = payload.case_ref.strip() or "LIVE-CAPTURE"
    with store.connect() as db:
        db.execute(
            "INSERT INTO case_watchlist VALUES(?,?,?,?,?,?,?,?)",
            (entry_id, label, case_ref, "", "", row["embedding_json"], row["best_image_path"], stamp),
        )
        store.append_audit(
            db,
            "watchlist.flagged",
            entry_id,
            f"Promoted live DB subject {row['subject_code']} ('{label}') to live SFace watchlist",
            stamp,
        )
    return {
        "id": entry_id,
        "label": label,
        "caseRef": case_ref,
        "candidateId": "",
        "clipId": "",
        "createdAt": stamp,
        "imageUrl": f"/api/watchlist/{entry_id}/image",
    }


@app.delete("/api/live-evidence/{identity_id}")
def delete_live_evidence(identity_id: str) -> dict:
    with store.connect() as db:
        row = db.execute("SELECT best_image_path, subject_code FROM live_identities WHERE id=?", (identity_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Live evidence subject not found.")
        sighting_rows = db.execute("SELECT image_path FROM live_sightings WHERE identity_id=?", (identity_id,)).fetchall()
        db.execute("DELETE FROM live_identities WHERE id=?", (identity_id,))
        store.append_audit(db, "live_evidence.deleted", identity_id, f"Removed live evidence subject {row['subject_code']}", now())
    for raw_p in [row["best_image_path"], *[s["image_path"] for s in sighting_rows]]:
        p = _safe_live_evidence_path(raw_p)
        if p:
            p.unlink(missing_ok=True)
    streams.manager.invalidate_evidence_cache()
    return {"deleted": identity_id}


@app.post("/api/live-evidence/clear")
def clear_live_evidence() -> dict:
    with store.connect() as db:
        count_row = db.execute("SELECT COUNT(*) FROM live_identities").fetchone()
        sighting_rows = db.execute("SELECT image_path FROM live_sightings").fetchall()
        id_rows = db.execute("SELECT best_image_path FROM live_identities").fetchall()
        inc_rows = db.execute("SELECT image_path FROM live_incidents").fetchall()
        db.execute("DELETE FROM live_sightings")
        db.execute("DELETE FROM live_identities")
        db.execute("DELETE FROM live_incidents")
        store.append_audit(db, "live_evidence.cleared", "live-db", f"Deleted {len(id_rows)} live subject records, {len(sighting_rows)} sighting records, and {len(inc_rows)} incident records.", now())
    for raw_p in [*(r["image_path"] for r in sighting_rows), *(r["best_image_path"] for r in id_rows), *(r["image_path"] for r in inc_rows)]:
        p = _safe_live_evidence_path(raw_p)
        if p:
            p.unlink(missing_ok=True)
    streams.manager.invalidate_evidence_cache()
    for state in streams.manager._streams.values():
        state.repeat_hit = ""
        state.repeat_hit_ts = 0.0
        state.last_incident_ts.clear()
    return {"cleared": int(count_row[0])}


_LIVE_INCIDENTS_MAX = 500  # keep at most this many rows; prune oldest on every list call


@app.get("/api/live-incidents")
def list_live_incidents(limit: int = 30) -> list[dict]:
    with store.connect() as db:
        # Prune oldest incidents beyond _LIVE_INCIDENTS_MAX to prevent unbounded growth
        total = db.execute("SELECT COUNT(*) FROM live_incidents").fetchone()[0]
        if total > _LIVE_INCIDENTS_MAX:
            # Collect image_paths of rows to delete so we can clean up files
            cutoff_rows = db.execute(
                "SELECT id, image_path FROM live_incidents ORDER BY occurred_at ASC LIMIT ?",
                (total - _LIVE_INCIDENTS_MAX,),
            ).fetchall()
            ids_to_delete = [r["id"] for r in cutoff_rows]
            paths_to_delete = [r["image_path"] for r in cutoff_rows if r["image_path"]]
            if ids_to_delete:
                db.execute(
                    f"DELETE FROM live_incidents WHERE id IN ({','.join('?'*len(ids_to_delete))})",
                    ids_to_delete,
                )
                db.commit()
            # Clean up orphaned image files outside the DB lock
            for img_path in paths_to_delete:
                try:
                    p = Path(img_path)
                    if p.exists():
                        p.unlink(missing_ok=True)
                except Exception:
                    pass
        rows = db.execute(
            "SELECT * FROM live_incidents ORDER BY occurred_at DESC LIMIT ?",
            (max(1, min(limit, 100)),),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "cameraId": r["camera_id"],
            "kind": r["kind"],
            "severity": r["severity"],
            "summary": r["summary"],
            "subjectCode": r["subject_code"],
            "personCount": int(r["person_count"]),
            "faceCount": int(r["face_count"]),
            "sha256": r["sha256"],
            "occurredAt": r["occurred_at"],
            "imageUrl": f"/api/live-incidents/{r['id']}/image",
        }
        for r in rows
    ]


@app.get("/api/live-incidents/{incident_id}.pdf")
def live_incident_pdf(incident_id: str, request: Request) -> StreamingResponse:
    with store.connect() as db:
        row = db.execute("SELECT * FROM live_incidents WHERE id=?", (incident_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Live incident not found.")
    img_path = _safe_live_evidence_path(row["image_path"])
    dossier = _active_dossier()
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    page_w, page_h = A4
    navy = colors.HexColor("#142b45")
    crimson = colors.HexColor("#9e2b25")
    pdf.setFillColor(navy)
    pdf.rect(0, page_h - 86, page_w, 86, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(42, page_h - 38, "DRISHTI  /  REAL-TIME INCIDENT EVIDENCE REPORT")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(42, page_h - 56, f"CAMERA: {row['camera_id']}   •   TYPE: {row['kind']}   •   SEVERITY: {row['severity'].upper()}")
    pdf.drawString(42, page_h - 70, f"FIR / NCRP 1930: {dossier['firNumber'] or 'Unassigned'} / {dossier['ncrpAck'] or '—'}   |   Station: {dossier['policeStation'] or 'Cyber Cell'}")

    pdf.setFillColor(crimson)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(42, page_h - 114, f"ALERT SUMMARY: {row['summary'][:86]}")
    pdf.setFillColor(colors.HexColor("#334455"))
    pdf.setFont("Helvetica", 9)
    pdf.drawString(42, page_h - 132, f"Occurred At: {row['occurred_at']}   |   Subject Ref: {row['subject_code'] or 'N/A'}   |   Tracks: {row['person_count']}   |   Faces: {row['face_count']}")
    pdf.setFont("Helvetica", 8)
    pdf.drawString(42, page_h - 148, f"Scene Snapshot SHA-256: {row['sha256']}")

    if img_path:
        pdf.drawImage(ImageReader(str(img_path)), 42, page_h - 420, width=510, height=250, preserveAspectRatio=True, anchor="c")

    pdf.setFillColor(colors.HexColor("#7a3c12"))
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(42, 70, "LOCAL SANDBOX DECISION-SUPPORT ALERT. OFFICER / ANALYST VERIFICATION REQUIRED.")
    pdf.setFillColor(colors.HexColor("#5e6d7a"))
    pdf.setFont("Helvetica", 8)
    pdf.drawString(42, 54, f"Generated on host {socket.gethostname()} at {now()} • Drishti PS04 Cyber Cell Suite")
    pdf.save()
    output.seek(0)
    with store.connect() as db:
        store.append_audit(db, "live_incident.pdf_exported", incident_id, f"Exported real-time incident PDF ({row['camera_id']} · {row['kind']})", now())
    return StreamingResponse(
        output,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="incident-{incident_id[:10]}.pdf"'},
    )


@app.get("/api/live-incidents/{incident_id}/image")
def live_incident_image(incident_id: str) -> FileResponse:
    with store.connect() as db:
        row = db.execute("SELECT image_path, camera_id, kind, occurred_at FROM live_incidents WHERE id=?", (incident_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Live incident snapshot not found.")
    path = _safe_live_evidence_path(row["image_path"])
    if not path:
        raise HTTPException(404, "Incident snapshot missing on disk.")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@app.delete("/api/live-incidents/{incident_id}")
def delete_live_incident(incident_id: str) -> dict:
    with store.connect() as db:
        row = db.execute("SELECT image_path FROM live_incidents WHERE id=?", (incident_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Live incident not found.")
        db.execute("DELETE FROM live_incidents WHERE id=?", (incident_id,))
        store.append_audit(db, "live_incident.deleted", incident_id, f"Deleted {row['kind']} incident record from {row['camera_id']} captured at {row['occurred_at']}.", now())
    p = _safe_live_evidence_path(row["image_path"])
    if p:
        p.unlink(missing_ok=True)
    return {"deleted": incident_id}


def _active_dossier() -> dict:
    with store.connect() as db:
        row = db.execute("SELECT * FROM case_dossiers WHERE id='ACTIVE'").fetchone()
    if not row:
        return {
            "id": "ACTIVE",
            "firNumber": "",
            "ncrpAck": "",
            "policeStation": "Cyber Crime Police Station",
            "ioName": "",
            "ioBadge": "",
            "atmId": "",
            "bankName": "",
            "fraudType": "ATM Cash-Out / Card Fraud",
            "lossInr": 0,
            "notes": "",
            "updatedAt": "",
        }
    return {
        "id": row["id"],
        "firNumber": row["fir_number"],
        "ncrpAck": row["ncrp_ack"],
        "policeStation": row["police_station"],
        "ioName": row["io_name"],
        "ioBadge": row["io_badge"],
        "atmId": row["atm_id"],
        "bankName": row["bank_name"],
        "fraudType": row["fraud_type"],
        "lossInr": int(row["loss_inr"]),
        "notes": row["notes"],
        "updatedAt": row["updated_at"],
    }


@app.get("/api/dossier")
def get_dossier() -> dict:
    return _active_dossier()


@app.put("/api/dossier")
def update_dossier(payload: CaseDossierRequest) -> dict:
    stamp = now()
    with store.connect() as db:
        db.execute(
            """INSERT INTO case_dossiers(id,fir_number,ncrp_ack,police_station,io_name,io_badge,atm_id,bank_name,fraud_type,loss_inr,notes,updated_at)
               VALUES('ACTIVE',?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 fir_number=excluded.fir_number,
                 ncrp_ack=excluded.ncrp_ack,
                 police_station=excluded.police_station,
                 io_name=excluded.io_name,
                 io_badge=excluded.io_badge,
                 atm_id=excluded.atm_id,
                 bank_name=excluded.bank_name,
                 fraud_type=excluded.fraud_type,
                 loss_inr=excluded.loss_inr,
                 notes=excluded.notes,
                 updated_at=excluded.updated_at""",
            (
                payload.fir_number.strip(),
                payload.ncrp_ack.strip(),
                payload.police_station.strip(),
                payload.io_name.strip(),
                payload.io_badge.strip(),
                payload.atm_id.strip(),
                payload.bank_name.strip(),
                payload.fraud_type.strip(),
                int(payload.loss_inr),
                payload.notes.strip(),
                stamp,
            ),
        )
        store.append_audit(
            db,
            "dossier.updated",
            "ACTIVE",
            f"Updated case dossier (FIR={payload.fir_number.strip() or '—'}, NCRP={payload.ncrp_ack.strip() or '—'}, Loss INR {payload.loss_inr})",
            stamp,
        )
    return _active_dossier()


@app.get("/api/cases/journey")
def case_journey() -> dict:
    """
    Build a unified Multi-Camera Suspect Journey & Fraud Intelligence Brief
    correlating ATM clips, transaction-linked analyses, SFace cross-clip matches,
    live surveillance sightings, and custody verification status.
    """
    with store.connect() as db:
        clips = [dict(r) for r in db.execute("SELECT * FROM clips ORDER BY uploaded_at ASC").fetchall()]
        analyses_rows = [
            dict(r)
            for r in db.execute(
                "SELECT a.*, c.camera_id, c.filename FROM analyses a JOIN clips c ON c.id=a.clip_id ORDER BY a.created_at ASC"
            ).fetchall()
        ]
        cand_rows = [dict(r) for r in db.execute("SELECT * FROM candidates ORDER BY score DESC").fetchall()]
        event_rows = [dict(r) for r in db.execute("SELECT * FROM events ORDER BY occurred_at DESC LIMIT 80").fetchall()]
        watchlist_rows = [dict(r) for r in db.execute("SELECT * FROM case_watchlist ORDER BY created_at DESC").fetchall()]
        live_rows = [dict(r) for r in db.execute("SELECT * FROM live_identities ORDER BY appearance_count DESC, last_seen_at DESC").fetchall()]
        audit_state = store.verify_audit(db)

    timeline: list[dict] = []
    for c in clips:
        timeline.append(
            {
                "id": f"clip-{c['id']}",
                "stage": "INGEST",
                "cameraId": c["camera_id"],
                "title": f"Footage ingested: {c['filename']}",
                "detail": f"SHA-256 {c['sha256'][:16]}… · {c['duration']:.1f}s · {c['width']}×{c['height']}",
                "timestamp": c["uploaded_at"],
                "severity": "info",
            }
        )

    best_score = 0.0
    occlusion_flags: set[str] = set()
    selected_cands = [c for c in cand_rows if c["review_status"] == "selected"]
    for c in cand_rows:
        best_score = max(best_score, float(c["score"]))
        for fl in store.json_load(c["flags_json"], []):
            if fl.startswith("possible "):
                occlusion_flags.add(fl)

    for a in analyses_rows:
        res = store.json_load(a["result_json"], {})
        timeline.append(
            {
                "id": f"ana-{a['id']}",
                "stage": "TRANSACTION_LINK",
                "cameraId": a["camera_id"],
                "title": f"Transaction {a['transaction_ref'] or a['transaction_time']} ({a['case_ref'] or 'Case'})",
                "detail": f"{res.get('candidateCount', 0)} face candidates · {res.get('peopleSeen', 0)} person tracks · {res.get('embeddingModel', 'local')}",
                "timestamp": a["created_at"],
                "severity": "warning" if res.get("alerts") else "info",
                "analysisId": a["id"],
            }
        )

    alert_events = [e for e in event_rows if e["kind"].startswith(("suspicious.", "stream."))]
    for e in alert_events[:25]:
        details = store.json_load(e["details_json"], {})
        timeline.append(
            {
                "id": f"evt-{e['id']}",
                "stage": "BEHAVIOUR_ALERT",
                "cameraId": details.get("cameraId", "ATM"),
                "title": e["kind"].replace(".", " · ").upper(),
                "detail": e["message"],
                "timestamp": e["occurred_at"],
                "severity": e["severity"],
            }
        )

    timeline.sort(key=lambda item: item["timestamp"], reverse=True)

    # Cross-camera SFace correlation across uploaded clips
    cross_links: list[dict] = []
    anchors = selected_cands or cand_rows[:3]
    seen_pairs: set[tuple[str, str]] = set()
    for anchor in anchors[:3]:
        avec = store.json_load(anchor["descriptor_json"], [])
        if not avec:
            continue
        for other in cand_rows:
            if other["clip_id"] == anchor["clip_id"]:
                continue
            ovec = store.json_load(other["descriptor_json"], [])
            sim = analysis.descriptor_similarity(avec, ovec)
            if sim is not None and sim >= 0.55:
                pair = tuple(sorted([anchor["clip_id"], other["clip_id"]]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                c1 = next((cl for cl in clips if cl["id"] == anchor["clip_id"]), None)
                c2 = next((cl for cl in clips if cl["id"] == other["clip_id"]), None)
                src_cam = c1["camera_id"] if c1 else "CLIP-A"
                dst_cam = c2["camera_id"] if c2 else "CLIP-B"
                if src_cam == dst_cam:
                    continue
                cross_links.append(
                    {
                        "sourceCamera": src_cam,
                        "targetCamera": dst_cam,
                        "similarity": round(sim * 100, 1),
                        "sourceCandidateId": anchor["id"],
                        "targetCandidateId": other["id"],
                        "targetAnalysisId": other["analysis_id"],
                    }
                )

    channels_covered = len({c["camera_id"] for c in clips})
    readiness_score = min(
        100,
        (25 if audit_state.get("verified") else 0)
        + min(25, channels_covered * 8)
        + (25 if cand_rows else 0)
        + (25 if selected_cands or cross_links else (10 if analyses_rows else 0)),
    )

    return {
        "readinessScore": readiness_score,
        "auditVerified": bool(audit_state.get("verified")),
        "channelsCovered": channels_covered,
        "clipCount": len(clips),
        "completedAnalyses": sum(1 for a in analyses_rows if a["status"] == "completed"),
        "selectedSuspects": len(selected_cands),
        "bestFaceQuality": round(best_score, 1),
        "occlusionFlags": sorted(occlusion_flags),
        "watchlistCount": len(watchlist_rows),
        "liveSubjects": len(live_rows),
        "repeatSubjects": sum(1 for lr in live_rows if int(lr["appearance_count"]) >= 2),
        "alertCount": len(alert_events),
        "crossLinks": cross_links,
        "timeline": timeline[:40],
        "notice": "Decision-support correlation across workspace evidence only. Requires investigator verification.",
    }


@app.get("/api/events")
def list_events(limit: int = 100) -> list[dict]:
    with store.connect() as db:
        rows = db.execute("SELECT * FROM events ORDER BY occurred_at DESC LIMIT ?", (max(1, min(limit, 500)),)).fetchall()
    return [
        {
            "id": r["id"],
            "analysisId": r["analysis_id"],
            "clipId": r["clip_id"],
            "kind": r["kind"],
            "message": r["message"],
            "severity": r["severity"],
            "occurredAt": r["occurred_at"],
            "details": store.json_load(r["details_json"], {}),
        }
        for r in rows
    ]


@app.get("/api/audit")
def list_audit(limit: int = 100) -> list[dict]:
    with store.connect() as db:
        rows = db.execute("SELECT * FROM audit_log ORDER BY rowid DESC LIMIT ?", (max(1, min(limit, 500)),)).fetchall()
    items = []
    for r in rows:
        match = re.search(r" · operator=([0-9a-f]{32})$", r["note"])
        description = r["note"][:match.start()] if match else r["note"]
        if r["action"] == "streams.source_changed" and description.startswith("Set stream source to "):
            source = description.removeprefix("Set stream source to ")
            if "://" in source:
                description = f"Configured {source.split(':', 1)[0].upper()} camera source. Frame delivery was not verified by this action."
        items.append(
        {
            "id": r["id"],
            "action": r["action"],
            "subjectId": r["subject_id"],
            "note": r["note"],
            "description": description,
            "actorId": match[1] if match else None,
            "occurredAt": r["occurred_at"],
            "entryHash": r["entry_hash"],
        }
        )
    return items


@app.get("/api/audit/integrity")
def audit_integrity() -> dict:
    with store.connect() as db:
        return store.verify_audit(db)


@app.get("/api/audit/export")
def export_audit(format: str = "json") -> StreamingResponse:
    with store.connect() as db:
        db.execute("BEGIN")
        integrity = store.verify_audit(db)
        rows = db.execute("SELECT * FROM audit_log ORDER BY rowid ASC").fetchall()
    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id", "occurred_at", "action", "subject_id", "note", "previous_hash", "entry_hash"])
        for r in rows:
            writer.writerow([r["id"], r["occurred_at"], r["action"], r["subject_id"], r["note"], r["previous_hash"], r["entry_hash"]])
        return StreamingResponse(
            io.BytesIO(buf.getvalue().encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="drishti-audit-trail.csv"'},
        )
    payload = sign_manifest(
        {
            "exportedAt": now(),
            "integrity": integrity,
            "entries": [dict(r) for r in rows],
        }
    )
    return StreamingResponse(
        io.BytesIO(json.dumps(payload, indent=2).encode("utf-8")),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="drishti-audit-trail.json"'},
    )


@app.get("/api/reports")
def reports() -> dict:
    with store.connect() as db:
        analyses = db.execute("SELECT status, COUNT(*) count FROM analyses GROUP BY status").fetchall()
        reviews = db.execute("SELECT review_status, COUNT(*) count FROM candidates GROUP BY review_status").fetchall()
        quality = db.execute("SELECT AVG(score), MAX(score), MIN(score) FROM candidates").fetchone()
        event_rows = db.execute("SELECT kind, COUNT(*) count FROM events GROUP BY kind").fetchall()
        flag_rows = db.execute("SELECT flags_json FROM candidates").fetchall()
        stream_rows = db.execute("SELECT camera_id, COUNT(*) count, SUM(person_count) people FROM stream_detections GROUP BY camera_id").fetchall()
    flag_counts: dict[str, int] = {}
    for row in flag_rows:
        for flag in store.json_load(row["flags_json"], []):
            flag_counts[flag] = flag_counts.get(flag, 0) + 1
    return {
        "analyses": {r["status"]: r["count"] for r in analyses},
        "reviews": {r["review_status"]: r["count"] for r in reviews},
        "quality": {
            "average": round(quality[0] or 0, 1),
            "best": round(quality[1] or 0, 1),
            "lowest": round(quality[2] or 0, 1),
        },
        "events": {r["kind"]: r["count"] for r in event_rows},
        "flags": flag_counts,
        "streams": {r["camera_id"]: {"events": r["count"], "detections": r["people"] or 0} for r in stream_rows},
    }


def _build_evidence_manifest(analysis_id: str) -> dict:
    record = get_analysis(analysis_id)
    if record["status"] != "completed":
        raise HTTPException(409, "Evidence manifest is available after analysis completes.")
    clip = _clip_or_404(record["clipId"])
    with store.connect() as db:
        audit_state = store.verify_audit(db)
        candidate_rows = db.execute("SELECT id, image_path FROM candidates WHERE analysis_id=?", (analysis_id,)).fetchall()
    crop_hashes = {}
    for row in candidate_rows:
        p = Path(row["image_path"])
        if p.is_file():
            crop_hashes[row["id"]] = _file_sha256(p)
    manifest = {
        "schema": "drishti.evidence.manifest.v1",
        "analysisId": analysis_id,
        "caseRef": record.get("caseRef") or "UNASSIGNED",
        "generatedAt": now(),
        "clip": {
            "id": clip["id"],
            "filename": clip["filename"],
            "cameraId": clip["camera_id"],
            "sourceSha256": clip["sha256"],
            "analysisSha256": clip["analysis_sha256"],
        },
        "transaction": {
            "timeMode": record["timeMode"],
            "transactionTime": record["transactionTime"],
            "clipStartTime": record["clipStartTime"],
            "transactionRef": record["transactionRef"],
            "windowSeconds": record["windowSeconds"],
        },
        "auditHeadHash": audit_state.get("headHash", ""),
        "candidates": [
            {
                "id": c["id"],
                "timeLabel": c["timeLabel"],
                "trackId": c["trackId"],
                "score": c["score"],
                "flags": c["flags"],
                "reviewStatus": c["reviewStatus"],
                "note": c["note"],
                "cropSha256": crop_hashes.get(c["id"], ""),
            }
            for c in record["candidates"]
        ],
        "disclaimer": "Machine scores and similarity cues assist human review and do not establish identity or guilt.",
    }
    return sign_manifest(manifest)


@app.get("/api/evidence/{analysis_id}/manifest.json")
def evidence_manifest(analysis_id: str) -> StreamingResponse:
    signed = _build_evidence_manifest(analysis_id)
    with store.connect() as db:
        store.append_audit(
            db,
            "evidence.manifest_exported",
            analysis_id,
            f"Signed HMAC-SHA256 evidence manifest exported ({signed['seal']['payloadSha256'][:16]}…)",
            now(),
        )
    safe_id = re.sub(r"[^a-zA-Z0-9-]", "", analysis_id)[:24]
    return StreamingResponse(
        io.BytesIO(json.dumps(signed, indent=2).encode("utf-8")),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="evidence-{quote(safe_id)}-manifest.json"'},
    )


class BlockchainEvidence(BaseModel):
    manifest: dict
    chainId: str = Field(max_length=32)
    transactionHash: str = Field(max_length=66)


def _blockchain_fingerprint(manifest: dict) -> str:
    canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@app.post("/api/evidence/{analysis_id}/blockchain")
def publish_blockchain_evidence(analysis_id: str, request: Request) -> dict:
    require_admin(request)
    manifest = _build_evidence_manifest(analysis_id)
    clip = _clip_or_404(manifest["clip"]["id"])
    if not manifest["auditHeadHash"] or any(not item["cropSha256"] for item in manifest["candidates"]):
        raise HTTPException(409, "The audit chain or candidate files could not be verified.")
    if not _matches_sha256(Path(clip["source_path"] or clip["path"]), clip["sha256"]) or not _matches_sha256(Path(clip["path"]), clip["analysis_sha256"]):
        raise HTTPException(409, "The current footage does not match its recorded fingerprints.")
    digest = _blockchain_fingerprint(manifest)
    try:
        anchor = blockchain.publish(digest)
    except blockchain.BlockchainError as exc:
        raise HTTPException(503, str(exc)) from exc
    with store.connect() as db:
        store.append_audit(db, "evidence.blockchain_submitted", analysis_id,
                           f"Submitted manifest SHA-256 {digest} to chain {anchor['chainId']} in transaction {anchor['transactionHash']}.", now())
    return {"manifest": manifest, **anchor}


@app.post("/api/security/verify-blockchain")
def verify_blockchain_evidence(payload: BlockchainEvidence, request: Request) -> dict:
    require_admin(request)
    try:
        digest = _blockchain_fingerprint(payload.manifest)
        result = blockchain.verify(digest, payload.chainId, payload.transactionHash)
    except ValueError as exc:
        raise HTTPException(422, "Manifest contains values that cannot be hashed.") from exc
    except blockchain.BlockchainError as exc:
        raise HTTPException(503, str(exc)) from exc
    with store.connect() as db:
        store.append_audit(db, "evidence.blockchain_checked", payload.transactionHash,
                           f"Checked manifest SHA-256 {digest} on chain {payload.chainId}. "
                           f"{result.get('reason') or 'Found matching fingerprint in the canonical block.'}", now())
    return {**result, "payloadSha256": digest}


def _render_evidence_pdf_bytes(analysis_id: str) -> bytes:
    record = get_analysis(analysis_id)
    if record["status"] != "completed":
        raise HTTPException(409, "Evidence sheet is available after analysis completes.")
    signed = _build_evidence_manifest(analysis_id)
    dossier = _active_dossier()
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    page_w, page_h = A4
    navy = colors.HexColor("#142b45")
    amber = colors.HexColor("#c48b3a")
    pdf.setFillColor(navy)
    pdf.rect(0, page_h - 92, page_w, 92, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(42, page_h - 38, "DRISHTI  /  FORENSIC EVIDENCE SHEET")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(42, page_h - 56, "LOCAL WORKSTATION PILOT  •  HUMAN VERIFICATION REQUIRED  •  HMAC-SHA256 SEALED")
    fir_line = dossier["firNumber"] or record.get("caseRef") or "Not assigned"
    ncrp_line = f"  |  NCRP 1930: {dossier['ncrpAck']}" if dossier["ncrpAck"] else ""
    pdf.drawString(42, page_h - 70, f"FIR / Case Ref: {fir_line}{ncrp_line}   |   Station: {dossier['policeStation'] or 'Cyber Cell'}")

    pdf.setFillColor(colors.HexColor("#263445"))
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(42, page_h - 118, "TRANSACTION, DOSSIER & CHAIN-OF-CUSTODY PROVENANCE")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(42, page_h - 135, f"Clip: {record['clipName'][:85]}   |   Fraud Type: {dossier['fraudType']}")
    time_label = "clip-relative" if record["timeMode"] == "clip" else f"bank time; clip starts {record['clipStartTime']}"
    pdf.drawString(42, page_h - 150, f"Transaction time ({time_label}): {record['transactionTime']}   |   Window: ±{record['windowSeconds']} s")
    pdf.drawString(42, page_h - 165, f"TXN Ref: {record['transactionRef'] or 'Not supplied'}   |   ATM/Bank: {dossier['atmId'] or '—'} / {dossier['bankName'] or '—'}   |   Loss: INR {dossier['lossInr']}")
    clip = _clip_or_404(record["clipId"])
    pdf.setFont("Helvetica", 7)
    pdf.drawString(42, page_h - 179, f"Source SHA-256:   {clip['sha256']}")
    pdf.drawString(42, page_h - 190, f"Analysis SHA-256: {clip['analysis_sha256']}")
    pdf.drawString(42, page_h - 201, f"Manifest Seal (HMAC-SHA256): {signed['seal']['signature']}")
    pdf.setStrokeColor(amber)
    pdf.setLineWidth(2)
    pdf.line(42, page_h - 210, page_w - 42, page_h - 210)

    y = page_h - 232
    alerts = record["result"].get("alerts") or []
    if alerts:
        pdf.setFillColor(colors.HexColor("#8a4b16"))
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(42, y, f"BEHAVIOUR / RELIABILITY ALERTS ({len(alerts)}):")
        y -= 13
        pdf.setFont("Helvetica", 8)
        for alert in alerts[:3]:
            pdf.drawString(50, y, f"• {alert.get('message', '')[:95]}")
            y -= 12
        y -= 6

    for index, candidate in enumerate(record["candidates"][:8], start=1):
        if y < 140:
            pdf.showPage()
            y = page_h - 55
        image_path = Path(_candidate_or_404(candidate["id"])["image_path"])
        if image_path.is_file():
            pdf.drawImage(ImageReader(str(image_path)), 42, y - 82, width=76, height=76, preserveAspectRatio=True, anchor="c", mask="auto")
        pdf.setFillColor(navy)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(132, y - 10, f"Candidate {index}  •  Track {candidate['trackId']}  •  {candidate['timeLabel']}")
        pdf.setFont("Helvetica", 9)
        pdf.setFillColor(colors.HexColor("#48586a"))
        metrics = candidate["metrics"]
        pdf.drawString(132, y - 28, f"Frame quality: {candidate['score']:.1f}/100   Sharpness: {metrics['sharpness']}   Light: {metrics['illumination']}   Pose: {metrics['pose']}")
        pdf.drawString(132, y - 44, f"Flags: {', '.join(candidate['flags']) or 'None detected by available checks'}")
        pdf.drawString(132, y - 60, f"Human review: {candidate['reviewStatus']}   Notes: {candidate['note'][:65] or '—'}")
        pdf.setStrokeColor(colors.HexColor("#dce3ea"))
        pdf.line(42, y - 94, page_w - 42, y - 94)
        y -= 108

    pdf.setFillColor(colors.HexColor("#8a4b16"))
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(42, 60, "SIMILARITY AND QUALITY SCORES ARE REVIEW AIDS, NOT IDENTIFICATION OR GUILT FINDINGS.")
    pdf.setFillColor(colors.HexColor("#647487"))
    pdf.setFont("Helvetica", 8)
    pdf.drawString(42, 45, f"Generated locally at {now()} • IO: {dossier['ioName'] or 'Investigator'} ({dossier['ioBadge'] or '—'}) • Verify manifest.json in Security Center.")
    pdf.save()
    return output.getvalue()


def _render_bsa63_pdf_bytes(analysis_id: str, officer_name: str = "") -> bytes:
    record = get_analysis(analysis_id)
    if record["status"] != "completed":
        raise HTTPException(409, "Certificate is available after analysis completes.")
    clip = _clip_or_404(record["clipId"])
    signed = _build_evidence_manifest(analysis_id)
    dossier = _active_dossier()
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    page_w, page_h = A4
    navy = colors.HexColor("#142b45")
    gold = colors.HexColor("#b8862d")

    pdf.setFillColor(navy)
    pdf.rect(0, page_h - 84, page_w, 84, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(42, page_h - 34, "CERTIFICATE UNDER SECTION 63, BHARATIYA SAKSHYA ADHINIYAM 2023")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(42, page_h - 52, "ELECTRONIC RECORD ADMISSIBILITY & HASH INTEGRITY PROVENANCE (FORMERLY SEC. 65B EVIDENCE ACT)")
    pdf.drawString(42, page_h - 68, f"Police Station / Cyber Unit: {dossier['policeStation'] or 'Cyber Crime Cell'}   |   FIR / Case: {dossier['firNumber'] or record.get('caseRef') or '—'}   |   1930 Ack: {dossier['ncrpAck'] or '—'}")

    y = page_h - 115
    pdf.setFillColor(colors.HexColor("#1d2b3a"))
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(42, y, "1. PARTICULARS OF COMPUTER SYSTEM & ELECTRONIC RECORD")
    y -= 18
    pdf.setFont("Helvetica", 9)
    lines = [
        f"Local Processing Workstation: {socket.gethostname()} (Offline Loopback Node 127.0.0.1)",
        f"Certifying Officer / Operator: {dossier['ioName'] or officer_name or 'Authorised Investigator'}   |   Badge / ID: {dossier['ioBadge'] or '—'}",
        f"Original CCTV File Ingested: {record['clipName'][:72]}   |   Channel: {clip['camera_id']}   |   Resolution: {clip['width']}x{clip['height']} @ {clip['fps']} FPS",
        f"Bank Transaction Link: Ref {record['transactionRef'] or '—'}   |   Time ({record['timeMode']}): {record['transactionTime']} (±{record['windowSeconds']}s)",
        f"ATM / Bank Details: Terminal {dossier['atmId'] or clip['camera_id']}   |   Bank: {dossier['bankName'] or '—'}   |   Fraud Type: {dossier['fraudType']}",
    ]
    for line in lines:
        pdf.drawString(48, y, line)
        y -= 15

    y -= 10
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(42, y, "2. CRYPTOGRAPHIC HASH & TAMPER-EVIDENT CUSTODY PROOFS")
    y -= 18
    pdf.setFont("Helvetica", 8)
    crypto_lines = [
        f"Hash Algorithm: SHA-256 (FIPS 180-4) + HMAC-SHA256 Local Custody Seal",
        f"Original Uploaded File SHA-256:    {clip['sha256']}",
        f"Normalized Review Copy SHA-256:    {clip['analysis_sha256']}",
        f"Manifest Payload SHA-256:          {signed['seal']['payloadSha256']}",
        f"Manifest HMAC-SHA256 Signature:    {signed['seal']['signature']}",
        f"Hash-Chained Audit Ledger Head:    {signed.get('auditHeadHash') or 'Verified'}",
    ]
    for line in crypto_lines:
        pdf.drawString(48, y, line)
        y -= 14

    y -= 10
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(42, y, "3. STATUTORY DECLARATION (SECTION 63(4) BSA 2023)")
    y -= 16
    pdf.setFont("Helvetica", 9)
    decl = [
        "(a) The electronic outputs (candidate face stills and PDF sheets) were produced by the computer system named",
        "    above during regular and lawful forensic inspection of the supplied ATM CCTV recording.",
        "(b) During ingest and analysis, the original recording bytes were hashed immediately upon receipt (SHA-256) and",
        "    preserved unmodified; any contrast/CLAHE enhancement is stored separately and explicitly labelled as enhanced.",
        "(c) Quality scores and face embedding similarity rankings are investigator decision-support aids only and do not",
        "    constitute autonomous biometric identification or proof of guilt without independent human corroboration.",
    ]
    for line in decl:
        pdf.drawString(48, y, line)
        y -= 14

    y -= 14
    pdf.setStrokeColor(gold)
    pdf.line(42, y, page_w - 42, y)
    y -= 28
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(42, y, "Investigating Officer Signature & Seal")
    pdf.drawString(320, y, "Technical / Hash Certifier Signature (Sec. 63(4)(c))")
    y -= 26
    pdf.setFont("Helvetica", 8)
    pdf.drawString(42, y, f"Date / Place: {datetime.now().strftime('%d-%m-%Y %H:%M')} IST · {dossier['policeStation'] or 'Jaipur, RJ'}")
    pdf.drawString(320, y, f"Audit Timestamp (UTC): {now()}")
    pdf.save()
    return output.getvalue()


@app.get("/api/evidence/{analysis_id}.pdf")
def evidence_pdf(analysis_id: str) -> StreamingResponse:
    pdf_bytes = _render_evidence_pdf_bytes(analysis_id)
    with store.connect() as db:
        store.append_audit(db, "evidence.pdf_exported", analysis_id, "Exported sealed PDF evidence sheet", now())
    safe_id = re.sub(r"[^a-zA-Z0-9-]", "", analysis_id)[:24]
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="evidence-{quote(safe_id)}.pdf"'},
    )


@app.get("/api/evidence/{analysis_id}/bsa63.pdf")
def evidence_bsa63_pdf(analysis_id: str, request: Request) -> StreamingResponse:
    sess = getattr(request.state, "session", None)
    officer = sess["user"]["displayName"] if sess else ""
    pdf_bytes = _render_bsa63_pdf_bytes(analysis_id, officer)
    with store.connect() as db:
        store.append_audit(db, "evidence.bsa63_exported", analysis_id, "Exported BSA Section 63 Electronic Record Certificate PDF", now())
    safe_id = re.sub(r"[^a-zA-Z0-9-]", "", analysis_id)[:24]
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="bsa-section63-{quote(safe_id)}.pdf"'},
    )


@app.get("/api/evidence/{analysis_id}/bundle.zip")
def evidence_bundle_zip(analysis_id: str, request: Request) -> StreamingResponse:
    record = get_analysis(analysis_id)
    if record["status"] != "completed":
        raise HTTPException(409, "Forensic bundle is available after analysis completes.")
    sess = getattr(request.state, "session", None)
    officer = sess["user"]["displayName"] if sess else ""
    signed = _build_evidence_manifest(analysis_id)
    dossier = _active_dossier()
    pdf_bytes = _render_evidence_pdf_bytes(analysis_id)
    bsa_bytes = _render_bsa63_pdf_bytes(analysis_id, officer)

    with store.connect() as db:
        integrity = store.verify_audit(db)
        audit_rows = [dict(r) for r in db.execute("SELECT * FROM audit_log ORDER BY rowid ASC").fetchall()]
        cand_rows = db.execute("SELECT id, image_path, bbox_json, frame_seconds, clip_id, track_id FROM candidates WHERE analysis_id=? ORDER BY score DESC LIMIT 6", (analysis_id,)).fetchall()
    signed_audit = sign_manifest({"exportedAt": now(), "integrity": integrity, "entries": audit_rows})

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("evidence-sheet.pdf", pdf_bytes)
        zf.writestr("bsa-section-63-certificate.pdf", bsa_bytes)
        zf.writestr("evidence-manifest.json", json.dumps(signed, indent=2))
        zf.writestr("case-dossier.json", json.dumps(dossier, indent=2))
        zf.writestr("audit-trail.json", json.dumps(signed_audit, indent=2))
        for idx, cr in enumerate(cand_rows, start=1):
            p = Path(cr["image_path"])
            if p.is_file():
                zf.write(p, f"candidates/{idx:02d}-track{cr['track_id']}-raw.jpg")
                crop_bgr = cv2.imread(str(p))
                if crop_bgr is not None:
                    enh = forensics.enhance_face_crop(crop_bgr)
                    ok_e, jpg_e = cv2.imencode(".jpg", enh, [cv2.IMWRITE_JPEG_QUALITY, 94])
                    if ok_e:
                        zf.writestr(f"candidates/{idx:02d}-track{cr['track_id']}-enhanced-labelled.jpg", jpg_e.tobytes())
        # Add DPDP bystander-redacted frame for top candidate if clip available
        if cand_rows:
            top = cand_rows[0]
            clip = _clip_or_404(top["clip_id"])
            bbox = store.json_load(top["bbox_json"], [])
            if len(bbox) == 4:
                redacted = forensics.redact_bystanders_frame(
                    Path(clip["path"]),
                    float(top["frame_seconds"]),
                    list(bbox) if isinstance(bbox, (list, tuple)) else None,
                    analysis.new_face_detector(),
                    clip["sha256"],
                )
                if redacted:
                    zf.writestr("candidates/01-bystander-redacted-dpdp.jpg", redacted)
        readme_txt = (
            "DRISHTI OFFLINE FORENSIC CASE BUNDLE\n"
            f"Generated (UTC): {now()}\n"
            f"Analysis ID: {analysis_id}\n"
            f"FIR / NCRP 1930: {dossier['firNumber'] or '—'} / {dossier['ncrpAck'] or '—'}\n"
            f"Manifest Payload SHA-256: {signed['seal']['payloadSha256']}\n"
            f"Manifest HMAC-SHA256 Seal: {signed['seal']['signature']}\n\n"
            "Verify manifest integrity anytime inside Drishti -> Security Center -> Manifest Verifier.\n"
        )
        zf.writestr("VERIFY-OFFLINE.txt", readme_txt)

    zip_buf.seek(0)
    with store.connect() as db:
        store.append_audit(db, "evidence.bundle_exported", analysis_id, "Exported complete offline forensic case bundle ZIP (BSA Sec 63 + Manifest + Stills)", now())
    safe_id = re.sub(r"[^a-zA-Z0-9-]", "", analysis_id)[:24]
    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="drishti-case-bundle-{quote(safe_id)}.zip"'},
    )


FRONTEND_DIST = store.ROOT / "dist"
if (FRONTEND_DIST / "index.html").is_file():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    def frontend_root() -> FileResponse:
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/favicon.ico", include_in_schema=False)
    @app.get("/favicon.svg", include_in_schema=False)
    def frontend_favicon() -> FileResponse:
        svg = FRONTEND_DIST / "favicon.svg"
        if svg.is_file():
            return FileResponse(svg, media_type="image/svg+xml")
        raise HTTPException(404, "Favicon not found")

    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend_route(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(404, "Route not found")
        return FileResponse(FRONTEND_DIST / "index.html")
