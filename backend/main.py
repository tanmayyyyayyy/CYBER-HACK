from __future__ import annotations

import io
import hashlib
import contextvars
import hmac
import json
import mimetypes
import os
import re
import shutil
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
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

from backend import analysis, auth, store
from backend.security import encrypt_snapshot

APP_NAME = "Drishti Forensic Review"
ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".mpeg", ".mpg"}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
LOCAL_ORIGINS = ["http://127.0.0.1:5174", "http://localhost:5174"]

app = FastAPI(title=APP_NAME, version="0.1.0", docs_url="/api/docs", redoc_url=None)
analysis_pool: ThreadPoolExecutor | None = None
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
        return {"width": frame.shape[1], "height": frame.shape[0], "fps": fps,
                "duration": frame_count / fps if frame_count > 0 else 0.0, "codec": codec}
    finally:
        cap.release()


def _transcode_review_copy(source: Path, target: Path, ffmpeg: str) -> None:
    try:
        subprocess.run([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                        "-protocol_whitelist", "file,pipe", "-i", str(source), "-map", "0:v:0", "-an",
                        "-sn", "-dn", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(target)],
                       capture_output=True, timeout=600, check=True)
    except (subprocess.SubprocessError, OSError) as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(422, "This export needs local H.264 conversion. Install FFmpeg with libx264, then retry.") from exc


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
            "sharpness": row["sharpness"], "illumination": row["illumination"],
            "faceSize": row["face_size"], "pose": row["pose"], "confidence": round(row["confidence"] * 100),
        },
        "flags": flags,
        "reviewStatus": row["review_status"],
        "note": row["note"],
        "imageUrl": f"/api/candidates/{row['id']}/image",
    }


class AnalysisRequest(BaseModel):
    clip_id: str = Field(min_length=8, max_length=64)
    transaction_time: str = Field(min_length=5, max_length=35)
    time_mode: str = Field(default="clip", pattern=r"^(clip|absolute)$")
    clip_start_time: str = Field(default="", max_length=35)
    transaction_ref: str = Field(default="", max_length=40)
    window_seconds: int = Field(default=30, ge=5, le=300)


class ReviewRequest(BaseModel):
    status: str = Field(pattern=r"^(selected|rejected|unreviewed)$")
    note: str = Field(default="", max_length=500)


class SearchRequest(BaseModel):
    candidate_id: str = Field(min_length=8, max_length=64)
    limit: int = Field(default=10, ge=1, le=30)


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
        response.headers.setdefault("Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
            "media-src 'self' blob:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; "
            "form-action 'self'; frame-ancestors 'none'")
    return response


def require_admin(request: Request) -> dict:
    user = request.state.session["user"]
    if user["role"] != "administrator":
        raise HTTPException(403, "Administrator access is required.")
    return user


@app.get("/api/auth/bootstrap")
def auth_bootstrap() -> dict:
    with store.connect() as db:
        count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    return {"needsAdministrator": count == 0}


def _set_session(response: JSONResponse, token: str) -> None:
    response.set_cookie(auth.COOKIE_NAME, token, httponly=True, secure=os.environ.get("DRISHTI_COOKIE_SECURE") == "1",
                        samesite="strict", max_age=auth.SESSION_HOURS * 3600, path="/")


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
    return [{"id": row["id"], "email": row["email"], "displayName": row["display_name"], "role": row["role"],
             "status": row["status"], "createdAt": row["created_at"], "approvedAt": row["approved_at"]} for row in rows]


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
    cutoff = (datetime.now(timezone.utc).replace(microsecond=0).timestamp() - 86400)
    cutoff_iso = datetime.fromtimestamp(cutoff, timezone.utc).isoformat(timespec="seconds")
    with store.connect() as db:
        db_check = db.execute("PRAGMA quick_check").fetchone()[0]
        foreign_key_issues = len(db.execute("PRAGMA foreign_key_check").fetchall())
        audit = store.verify_audit(db)
        failed_signins = db.execute("SELECT COUNT(*) FROM audit_log WHERE action IN ('security.login_failed','security.login_denied','security.login_throttled') AND occurred_at>=?", (cutoff_iso,)).fetchone()[0]
        pending = db.execute("SELECT COUNT(*) FROM users WHERE status='pending'").fetchone()[0]
        active = db.execute("SELECT COUNT(*) FROM users WHERE status='active'").fetchone()[0]
        clips = db.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
        backup = db.execute("SELECT id,created_at,size_bytes,sha256 FROM security_backups ORDER BY created_at DESC LIMIT 1").fetchone()
        full_check = db.execute("SELECT checked_at,clips_checked,mismatch_count FROM security_evidence_checks ORDER BY checked_at DESC LIMIT 1").fetchone()
    data_mode = _safe_mode(store.DATA)
    db_mode = _safe_mode(store.DB_PATH)
    return {
        "database": {"integrity": db_check, "foreignKeyViolations": foreign_key_issues,
                     "sizeBytes": store.DB_PATH.stat().st_size if store.DB_PATH.exists() else 0,
                     "directoryPermissions": data_mode, "filePermissions": db_mode},
        "audit": audit,
        "accounts": {"active": active, "pending": pending, "failedSignins24h": failed_signins},
        "evidence": {"clipCount": clips,
                     "lastFullCheck": ({"checkedAt": full_check["checked_at"], "clipsChecked": full_check["clips_checked"], "mismatchCount": full_check["mismatch_count"]} if full_check else None)},
        "backup": ({"id": backup["id"], "createdAt": backup["created_at"], "sizeBytes": backup["size_bytes"], "sha256": backup["sha256"]}
                   if backup else None),
        "hostEncryption": {"status": "verify", "message": "Enable FileVault, BitLocker, or LUKS on the host volume; this app does not manage the device key."},
        "networkBoundary": {"status": "loopback", "message": "The local runner binds to 127.0.0.1; keep reverse proxies and remote access disabled unless formally reviewed."},
    }


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
            mismatches.append({"clipId": clip["id"], "filename": clip["filename"],
                               "sourceMatches": bool(source_matches), "analysisMatches": bool(analysis_matches)})
    stamp = now()
    with store.connect() as db:
        store.append_audit(db, "security.evidence_batch_check", "all" if not payload.clip_ids else ",".join(payload.clip_ids)[:500],
                           f"Checked {checked} clips; {len(mismatches)} integrity mismatch(es)", stamp)
        db.execute("INSERT INTO security_evidence_checks(id,checked_by,checked_at,clips_checked,mismatch_count,details_json) VALUES(?,?,?,?,?,?)",
                   (uuid.uuid4().hex, request.state.session["user"]["id"], stamp, checked, len(mismatches), json.dumps(mismatches)))
        for mismatch in mismatches:
            db.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?,?)",
                       (uuid.uuid4().hex, None, mismatch["clipId"], "evidence.integrity_mismatch",
                        f"Full security check found changed or missing bytes for {mismatch['filename']}", "critical", stamp,
                        json.dumps({"sourceMatches": mismatch["sourceMatches"], "analysisMatches": mismatch["analysisMatches"]})))
    return {"checked": checked, "verified": checked - len(mismatches), "mismatches": mismatches, "checkedAt": stamp,
            "notice": "SHA-256 matches compare local bytes to ingest fingerprints; they do not attest the original recording source."}


@app.get("/api/security/database-backups")
def list_database_backups(request: Request) -> list[dict]:
    require_admin(request)
    with store.connect() as db:
        rows = db.execute("SELECT id,created_at,size_bytes,sha256 FROM security_backups ORDER BY created_at DESC LIMIT 20").fetchall()
    return [{"id": row["id"], "createdAt": row["created_at"], "sizeBytes": row["size_bytes"], "sha256": row["sha256"]} for row in rows]


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
            encrypted = encrypt_snapshot(snapshot.serialize(), payload.passphrase)
        finally:
            snapshot.close()
            source.close()
        path.write_bytes(encrypted)
        path.chmod(0o600)
        size, digest = path.stat().st_size, _file_sha256(path)
        created = now()
        with store.connect() as db:
            db.execute("INSERT INTO security_backups(id,filename,created_by,created_at,size_bytes,sha256) VALUES(?,?,?,?,?,?)",
                       (backup_id, filename, admin["id"], created, size, digest))
            store.append_audit(db, "security.database_backup_created", backup_id,
                               f"Encrypted SQLite quick_check=ok; AES-256-GCM; {size} bytes; SHA-256 {digest}", created)
        return {"id": backup_id, "createdAt": created, "sizeBytes": size, "sha256": digest,
                "downloadUrl": f"/api/security/database-backups/{backup_id}",
                "scope": "Passphrase-encrypted SQLite metadata snapshot only; video files and candidate images are not included."}
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
        store.append_audit(db, "security.database_backup_downloaded", backup_id, "Administrator downloaded metadata snapshot", now(), actor_id=admin["id"])
    return FileResponse(path, media_type="application/octet-stream", filename=row["filename"],
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@app.on_event("startup")
def startup() -> None:
    global analysis_pool
    store.init_db()
    analysis_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="drishti-analysis")
    with store.connect() as db:
        interrupted = db.execute("SELECT id FROM analyses WHERE status IN ('queued','running')").fetchall()
        for row in interrupted:
            db.execute("UPDATE analyses SET status='failed',error=?,updated_at=? WHERE id=?",
                       ("Processing stopped because the local service restarted. Start this analysis again.", now(), row["id"]))
            store.append_audit(db, "analysis.interrupted", row["id"], "Service restarted during analysis", now())


@app.on_event("shutdown")
def shutdown() -> None:
    global analysis_pool
    if analysis_pool is not None:
        analysis_pool.shutdown(wait=True, cancel_futures=True)
        analysis_pool = None


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "local",
        "service": APP_NAME,
        "models": analysis.model_status(),
        "ffmpeg": bool(__import__("shutil").which("ffmpeg")),
        "cloud": "disabled",
    }


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
    return [
        {"id": r["id"], "filename": r["filename"], "sizeBytes": r["size_bytes"],
         "duration": r["duration"], "width": r["width"], "height": r["height"],
         "fps": r["fps"], "codec": r["codec"], "playbackCodec": r["playback_codec"],
         "normalized": r["sha256"] != r["analysis_sha256"], "previewReady": bool(r["preview_ready"]),
         "cameraId": r["camera_id"],
         "sha256": r["sha256"], "uploadedAt": r["uploaded_at"],
         "videoUrl": f"/api/clips/{r['id']}/video", "posterUrl": f"/api/clips/{r['id']}/poster"}
        for r in rows
    ]


@app.get("/api/cameras")
def camera_slots() -> list[dict]:
    labels = {"ATM-01": "Entry view", "ATM-02": "Keypad view", "ATM-03": "Cash slot", "ATM-04": "Exit view"}
    clips = list_clips()
    return [
        {"id": camera_id, "label": label,
         "clips": [clip for clip in clips if clip["cameraId"] == camera_id],
         "status": "recorded" if any(clip["cameraId"] == camera_id for clip in clips) else "awaiting clip",
         "source": "local file"}
        for camera_id, label in labels.items()
    ]


@app.post("/api/clips", status_code=201)
async def upload_clip(request: Request, filename: str, camera_id: str = "ATM-01") -> dict:
    original = Path(filename).name.strip()
    suffix = Path(original).suffix.lower()
    if camera_id not in {"ATM-01", "ATM-02", "ATM-03", "ATM-04"}:
        raise HTTPException(422, "Choose one of the four local ATM camera channels.")
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, "Use MP4, AVI, MOV, MKV, WMV, FLV, MPEG, or MPG.")
    clip_id = uuid.uuid4().hex
    path = store.UPLOADS / f"{clip_id}{suffix}"
    normalized = store.UPLOADS / f"{clip_id}-normalized.mp4"
    size = 0
    source_digest = hashlib.sha256()
    try:
        with path.open("wb") as output:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "Maximum clip size is 500 MB.")
                output.write(chunk)
                source_digest.update(chunk)
        if size == 0:
            raise HTTPException(400, "The uploaded clip is empty.")
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
            browser_codec = ((suffix_name == ".mp4" and codec_name in {"avc1", "h264", "x264"})
                             or (suffix_name == ".webm" and codec_name in {"vp80", "vp90", "vp09", "av01"}))
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
        record = {
            "id": clip_id, "filename": original[:180], "camera_id": camera_id,
            "path": str(playable_path), "source_path": str(path), "size_bytes": size,
            "duration": round(duration, 3), "width": width, "height": height,
            "fps": round(fps, 3), "codec": codec, "playback_codec": playback_codec,
            "preview_ready": int(preview_ready), "sha256": source_digest.hexdigest(),
            "analysis_sha256": analysis_digest, "uploaded_at": now(),
        }
        with store.connect() as db:
            db.execute("""INSERT INTO clips(id,filename,camera_id,path,source_path,size_bytes,duration,
                         width,height,fps,codec,playback_codec,preview_ready,sha256,analysis_sha256,uploaded_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", tuple(record.values()))
            store.append_audit(db, "clip.uploaded", clip_id,
                               f"Local clip uploaded: {original[:100]} ({size} bytes, SHA-256 {record['sha256'][:16]}…)", now())
        return {"id": clip_id, "filename": record["filename"], "cameraId": camera_id,
                "sizeBytes": size, "duration": record["duration"], "width": width, "height": height,
                "fps": record["fps"], "codec": codec, "playbackCodec": playback_codec,
                "normalized": analysis_digest != record["sha256"], "previewReady": preview_ready,
                "uploadedAt": record["uploaded_at"],
                "sha256": record["sha256"],
                "videoUrl": f"/api/clips/{clip_id}/video", "posterUrl": f"/api/clips/{clip_id}/poster"}
    except Exception:
        path.unlink(missing_ok=True)
        if 'playable_path' in locals() and playable_path != path:
            playable_path.unlink(missing_ok=True)
        normalized.unlink(missing_ok=True)
        raise


@app.get("/api/clips/{clip_id}/video")
def clip_video(clip_id: str) -> FileResponse:
    clip = _clip_or_404(clip_id)
    media_type = mimetypes.guess_type(clip["path"])[0] or "video/mp4"
    return FileResponse(clip["path"], media_type=media_type, filename=clip["filename"],
                        content_disposition_type="inline", headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


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
        store.append_audit(db, "clip.integrity_checked", clip_id,
                           "SHA-256 verified against ingest fingerprints" if verified else "SHA-256 mismatch or missing local evidence file",
                           now())
        if not verified:
            db.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?,?)",
                       (uuid.uuid4().hex, None, clip_id, "evidence.integrity_mismatch",
                        f"SHA-256 verification failed for {clip['filename']}", "warning", now(),
                        json.dumps({"sourceMatches": source_ok, "analysisMatches": analyzed_ok})))
    return {"clipId": clip_id, "filename": clip["filename"], "verified": verified,
            "sourceMatches": source_ok, "analysisMatches": analyzed_ok,
            "sourceSha256": clip["sha256"], "analysisSha256": clip["analysis_sha256"],
            "normalized": clip["sha256"] != clip["analysis_sha256"], "checkedAt": now(),
            "notice": "Hash match shows these local bytes match their ingest fingerprints; it does not prove who recorded the source footage."}


@app.post("/api/analyses", status_code=202)
def create_analysis(payload: AnalysisRequest) -> dict:
    clip = _clip_or_404(payload.clip_id)
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
        db.execute("INSERT INTO analyses VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                   (job_id, clip["id"], payload.transaction_time, payload.time_mode,
                    payload.clip_start_time, payload.transaction_ref.strip(),
                    payload.window_seconds, "running", "{}", "", stamp, stamp))
        store.append_audit(db, "analysis.started", job_id,
                           f"Window ±{payload.window_seconds}s at {payload.transaction_time}", stamp)
    if analysis_pool is None:
        raise HTTPException(503, "Local analysis worker is not ready. Restart the service and retry.")
    analysis_context = contextvars.copy_context()
    analysis_pool.submit(analysis_context.run, analysis.run_analysis, job_id)
    return {"id": job_id, "status": "running", "clipId": clip["id"], "transactionTime": payload.transaction_time}


@app.get("/api/analyses")
def list_analyses() -> list[dict]:
    with store.connect() as db:
        rows = db.execute("""SELECT a.*, c.filename FROM analyses a JOIN clips c ON c.id=a.clip_id
                             ORDER BY a.created_at DESC LIMIT 100""").fetchall()
        analysis_ids = [r["id"] for r in rows]
        candidates_by_analysis: dict[str, list[dict]] = {key: [] for key in analysis_ids}
        if analysis_ids:
            marks = ",".join("?" for _ in analysis_ids)
            candidates = db.execute(f"SELECT * FROM candidates WHERE analysis_id IN ({marks}) ORDER BY score DESC", analysis_ids).fetchall()
            for candidate in candidates:
                candidates_by_analysis[candidate["analysis_id"]].append(_public_candidate(dict(candidate)))
    return [{"id": r["id"], "clipId": r["clip_id"], "clipName": r["filename"], "filename": r["filename"],
             "transactionTime": r["transaction_time"], "transactionRef": r["transaction_ref"],
             "timeMode": r["time_mode"], "clipStartTime": r["clip_start_time"],
             "windowSeconds": r["window_seconds"], "status": r["status"], "error": r["error"],
             "createdAt": r["created_at"], "result": store.json_load(r["result_json"], {}),
             "candidates": candidates_by_analysis[r["id"]]}
            for r in rows]


@app.get("/api/analyses/{analysis_id}")
def get_analysis(analysis_id: str) -> dict:
    with store.connect() as db:
        row = store.row_dict(db.execute("SELECT * FROM analyses WHERE id=?", (analysis_id,)).fetchone())
        if not row:
            raise HTTPException(404, "Analysis not found")
        clip = store.row_dict(db.execute("SELECT * FROM clips WHERE id=?", (row["clip_id"],)).fetchone())
        candidates = db.execute("SELECT * FROM candidates WHERE analysis_id=? ORDER BY score DESC", (analysis_id,)).fetchall()
    return {"id": row["id"], "clipId": row["clip_id"], "clipName": clip["filename"],
            "transactionTime": row["transaction_time"], "transactionRef": row["transaction_ref"],
            "timeMode": row["time_mode"], "clipStartTime": row["clip_start_time"],
            "windowSeconds": row["window_seconds"], "status": row["status"], "error": row["error"],
            "createdAt": row["created_at"], "result": store.json_load(row["result_json"], {}),
            "candidates": [_public_candidate(dict(c)) for c in candidates]}


@app.get("/api/candidates/{candidate_id}/image")
def candidate_image(candidate_id: str) -> FileResponse:
    candidate = _candidate_or_404(candidate_id)
    return FileResponse(candidate["image_path"], media_type="image/jpeg",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@app.patch("/api/candidates/{candidate_id}/review")
def review_candidate(candidate_id: str, payload: ReviewRequest) -> dict:
    candidate = _candidate_or_404(candidate_id)
    with store.connect() as db:
        db.execute("UPDATE candidates SET review_status=?, note=? WHERE id=?",
                   (payload.status, payload.note.strip(), candidate_id))
        store.append_audit(db, f"candidate.{payload.status}", candidate_id,
                           payload.note.strip() or f"Review marked {payload.status}", now())
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
               WHERE c.clip_id != ? ORDER BY c.score DESC LIMIT 1000""", (query["clip_id"],)
        ).fetchall()
    matches = []
    target_array = __import__("numpy").asarray(target, dtype=float)
    for row in rows:
        candidate = dict(row)
        vector = store.json_load(candidate["descriptor_json"], [])
        if len(vector) != len(target):
            continue
        score = float(__import__("numpy").dot(target_array, vector))
        if score >= 0.55:
            matches.append({**_public_candidate(candidate), "similarity": round(score * 100, 1),
                            "filename": candidate["filename"]})
    matches.sort(key=lambda item: item["similarity"], reverse=True)
    with store.connect() as db:
        store.append_audit(db, "candidate.search", query["id"],
                           f"Clip-only visual similarity search across {len({m['clipId'] for m in matches})} clips", now())
    return {"queryCandidateId": query["id"], "matches": matches[:payload.limit],
            "notice": "Appearance similarity only; not identity verification. Results require human review."}


@app.get("/api/events")
def list_events(limit: int = 100) -> list[dict]:
    with store.connect() as db:
        rows = db.execute("SELECT * FROM events ORDER BY occurred_at DESC LIMIT ?", (max(1, min(limit, 500)),)).fetchall()
    return [{"id": r["id"], "analysisId": r["analysis_id"], "clipId": r["clip_id"],
             "kind": r["kind"], "message": r["message"], "severity": r["severity"],
             "occurredAt": r["occurred_at"], "details": store.json_load(r["details_json"], {})}
            for r in rows]


@app.get("/api/audit")
def list_audit(limit: int = 100) -> list[dict]:
    with store.connect() as db:
        rows = db.execute("SELECT * FROM audit_log ORDER BY occurred_at DESC LIMIT ?", (max(1, min(limit, 500)),)).fetchall()
    return [{"id": r["id"], "action": r["action"], "subjectId": r["subject_id"],
             "note": r["note"], "occurredAt": r["occurred_at"], "entryHash": r["entry_hash"]} for r in rows]


@app.get("/api/audit/integrity")
def audit_integrity() -> dict:
    with store.connect() as db:
        return store.verify_audit(db)


@app.get("/api/reports")
def reports() -> dict:
    with store.connect() as db:
        analyses = db.execute("SELECT status, COUNT(*) count FROM analyses GROUP BY status").fetchall()
        reviews = db.execute("SELECT review_status, COUNT(*) count FROM candidates GROUP BY review_status").fetchall()
        quality = db.execute("SELECT AVG(score), MAX(score), MIN(score) FROM candidates").fetchone()
        event_rows = db.execute("SELECT kind, COUNT(*) count FROM events GROUP BY kind").fetchall()
    return {"analyses": {r["status"]: r["count"] for r in analyses},
            "reviews": {r["review_status"]: r["count"] for r in reviews},
            "quality": {"average": round(quality[0] or 0, 1), "best": round(quality[1] or 0, 1), "lowest": round(quality[2] or 0, 1)},
            "events": {r["kind"]: r["count"] for r in event_rows}}


@app.get("/api/evidence/{analysis_id}.pdf")
def evidence_pdf(analysis_id: str) -> StreamingResponse:
    record = get_analysis(analysis_id)
    if record["status"] != "completed":
        raise HTTPException(409, "Evidence sheet is available after analysis completes.")
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    page_w, page_h = A4
    navy = colors.HexColor("#142b45")
    amber = colors.HexColor("#c48b3a")
    pdf.setFillColor(navy)
    pdf.rect(0, page_h - 92, page_w, 92, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 19)
    pdf.drawString(42, page_h - 42, "DRISHTI  /  EVIDENCE REVIEW")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(42, page_h - 62, "LOCAL PRODUCT PILOT  •  HUMAN REVIEW REQUIRED")
    pdf.setFillColor(colors.HexColor("#263445"))
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(42, page_h - 122, "TRANSACTION CONTEXT")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(42, page_h - 143, f"Clip: {record['clipName'][:90]}")
    time_label = "clip-relative" if record["timeMode"] == "clip" else f"bank time; clip starts {record['clipStartTime']}"
    pdf.drawString(42, page_h - 160, f"Transaction time ({time_label}): {record['transactionTime']}   |   Window: ±{record['windowSeconds']} s")
    pdf.drawString(42, page_h - 177, f"Reference: {record['transactionRef'] or 'Not supplied'}   |   Analysis ID: {analysis_id[:16]}")
    clip = _clip_or_404(record["clipId"])
    pdf.setFont("Helvetica", 7)
    pdf.drawString(42, page_h - 191, f"Uploaded source SHA-256: {clip['sha256']}")
    pdf.drawString(42, page_h - 202, f"Analyzed file SHA-256: {clip['analysis_sha256']}")
    pdf.setStrokeColor(amber)
    pdf.setLineWidth(2)
    pdf.line(42, page_h - 212, page_w - 42, page_h - 212)
    y = page_h - 236
    for index, candidate in enumerate(record["candidates"][:8], start=1):
        if y < 135:
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
    pdf.drawString(42, 45, f"Generated locally at {now()} • Keep with the source clip and transaction record.")
    pdf.save()
    output.seek(0)
    safe_id = re.sub(r"[^a-zA-Z0-9-]", "", analysis_id)[:24]
    return StreamingResponse(output, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="evidence-{quote(safe_id)}.pdf"'})


FRONTEND_DIST = store.ROOT / "dist"
if (FRONTEND_DIST / "index.html").is_file():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    def frontend_root() -> FileResponse:
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend_route(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(404, "Route not found")
        return FileResponse(FRONTEND_DIST / "index.html")
