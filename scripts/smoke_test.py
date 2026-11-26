from __future__ import annotations

import json
import hashlib
import os
import sqlite3
import sys
import tempfile
import time
import uuid
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def make_synthetic_clip(path: Path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 8, (640, 360))
    if not writer.isOpened():
        raise RuntimeError("OpenCV could not create the synthetic MP4 fixture.")
    for frame_no in range(64):
        frame = np.full((360, 640, 3), (31, 42, 54), dtype=np.uint8)
        cv2.rectangle(frame, (380, 48), (585, 330), (100, 82, 58), -1)
        cv2.rectangle(frame, (420, 122), (545, 197), (29, 34, 40), -1)
        cv2.circle(frame, (150 + frame_no, 105), 25, (190, 205, 220), -1)
        cv2.line(frame, (150 + frame_no, 130), (150 + frame_no, 270), (190, 205, 220), 12)
        cv2.line(frame, (150 + frame_no, 165), (205 + frame_no, 205), (190, 205, 220), 9)
        cv2.line(frame, (150 + frame_no, 270), (118 + frame_no, 333), (190, 205, 220), 9)
        cv2.line(frame, (150 + frame_no, 270), (182 + frame_no, 333), (190, 205, 220), 9)
        cv2.putText(frame, "SYNTHETIC TEST CLIP", (18, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (228, 232, 236), 2)
        writer.write(frame)
    writer.release()


def run() -> None:
    with tempfile.TemporaryDirectory(prefix="drishti-smoke-") as temp:
        os.environ["DRISHTI_DATA_DIR"] = str(Path(temp) / "data")
        fixture = Path(temp) / "synthetic-atm.mp4"
        make_synthetic_clip(fixture)

        from backend import store
        with store.connect() as db:
            db.execute("CREATE TABLE auth_attempts(email TEXT NOT NULL,attempted_at TEXT NOT NULL)")
            db.execute("CREATE INDEX idx_auth_attempts_time ON auth_attempts(email,attempted_at)")
            db.execute("INSERT INTO auth_attempts(email,attempted_at) VALUES(?,?)",
                       ("legacy@example.test", "2026-01-01T00:00:00+00:00"))
        from backend.main import app
        from backend.security import MAGIC, decrypt_snapshot
        from scripts.restore_database import restore_backup

        with TestClient(app) as client:
            health = client.get("/api/health").json()
            assert health["status"] == "local" and health["cloud"] == "disabled"
            assert health["models"]["face"] == "YuNet local weights"
            assert client.get("/api/auth/bootstrap").json()["needsAdministrator"] is True
            assert client.get("/api/clips").status_code == 401
            assert client.get("/api/health").headers["x-content-type-options"] == "nosniff"
            frontend = client.get("/")
            if frontend.status_code == 200:
                assert "frame-ancestors 'none'" in frontend.headers["content-security-policy"]
            with store.connect() as db:
                migrated = db.execute("SELECT COUNT(*) FROM auth_attempts WHERE identifier_hash=?",
                                      (hashlib.sha256(b"legacy@example.test").hexdigest(),)).fetchone()[0]
                assert migrated == 1
            created_admin = client.post("/api/auth/signup", json={"display_name": "Local Admin", "email": "admin@example.test", "password": "LocalStrongPassphrase2026"})
            assert created_admin.status_code == 201, created_admin.text
            admin_user = created_admin.json()["user"]
            assert admin_user["role"] == "administrator" and admin_user["status"] == "active"
            csrf = created_admin.json()["csrfToken"]
            assert client.get("/api/auth/me").json()["user"]["id"] == admin_user["id"]
            assert client.post("/api/auth/logout").status_code == 403
            client.post("/api/auth/login", json={"email": "admin@example.test", "password": "wrong"})
            with store.connect() as db:
                attempt = db.execute("SELECT * FROM auth_attempts ORDER BY attempted_at DESC LIMIT 1").fetchone()
                assert attempt and "identifier_hash" in attempt.keys() and "email" not in attempt.keys()
            pending = client.post("/api/auth/signup", json={"display_name": "Local Investigator", "email": "investigator@example.test", "password": "InvestigatorPassphrase2026"})
            assert pending.status_code == 202 and pending.json()["approvalRequired"] is True
            assert client.post("/api/auth/login", json={"email": "investigator@example.test", "password": "InvestigatorPassphrase2026"}).status_code == 403
            account = next(row for row in client.get("/api/auth/users").json() if row["email"] == "investigator@example.test")
            assert client.patch(f"/api/auth/users/{account['id']}", json={"status": "active"}, headers={"X-CSRF-Token": csrf}).status_code == 200
            signed_in = client.post("/api/auth/login", json={"email": "investigator@example.test", "password": "InvestigatorPassphrase2026"})
            assert signed_in.status_code == 200
            assert client.get("/api/clips").status_code == 200
            assert client.get("/api/auth/users").status_code == 403
            assert client.get("/api/security/overview").status_code == 403
            assert client.post("/api/security/evidence-check", headers={"X-CSRF-Token": signed_in.json()["csrfToken"]}, json={}).status_code == 403
            client.post("/api/auth/logout", headers={"X-CSRF-Token": signed_in.json()["csrfToken"]})
            admin_login = client.post("/api/auth/login", json={"email": "admin@example.test", "password": "LocalStrongPassphrase2026"})
            assert admin_login.status_code == 200
            csrf = admin_login.json()["csrfToken"]
            assert len(client.get("/api/cameras").json()) == 4
            posture = client.get("/api/security/overview")
            assert posture.status_code == 200, posture.text
            assert posture.json()["database"]["integrity"] == "ok"
            assert posture.json()["database"]["filePermissions"]["restricted"] is True
            assert posture.json()["accounts"]["failedSignins24h"] >= 1

            headers = {"Content-Type": "application/octet-stream", "X-CSRF-Token": csrf}
            rejected = client.post("/api/clips?filename=notes.txt", content=b"not video", headers=headers)
            assert rejected.status_code == 415

            uploaded = client.post(
                "/api/clips?filename=synthetic-atm.mp4&camera_id=ATM-02",
                content=fixture.read_bytes(),
                headers=headers,
            )
            assert uploaded.status_code == 201, uploaded.text
            clip = uploaded.json()
            upload_audit = next(row for row in client.get("/api/audit").json() if row["action"] == "clip.uploaded")
            assert f"operator={admin_user['id']}" in upload_audit["note"]
            assert clip["cameraId"] == "ATM-02" and clip["duration"] >= 7.5
            assert clip["normalized"] is True and clip["previewReady"] is True
            assert clip["playbackCodec"].lower() in {"avc1", "h264"}
            assert client.get(clip["videoUrl"]).headers["content-type"].startswith("video/mp4")
            assert client.get(clip["videoUrl"]).headers["cache-control"] == "no-store"
            assert clip["sha256"] == hashlib.sha256(fixture.read_bytes()).hexdigest()
            assert client.get(clip["posterUrl"]).status_code == 200
            with store.connect() as db:
                playable_path = Path(db.execute("SELECT path FROM clips WHERE id=?", (clip["id"],)).fetchone()[0])
            original_bytes = playable_path.read_bytes()
            assert client.get(f"/api/clips/{clip['id']}/integrity").json()["verified"] is True
            playable_path.write_bytes(original_bytes + b"tamper")
            assert client.get(f"/api/clips/{clip['id']}/integrity").json()["verified"] is False
            sweep = client.post("/api/security/evidence-check", headers={"X-CSRF-Token": csrf}, json={"clip_ids": [clip["id"]]})
            assert sweep.status_code == 200 and sweep.json()["mismatches"][0]["analysisMatches"] is False
            playable_path.write_bytes(original_bytes)
            assert client.get(f"/api/clips/{clip['id']}/integrity").json()["verified"] is True
            assert client.get("/api/clips").json()[0]["cameraId"] == "ATM-02"
            sweep = client.post("/api/security/evidence-check", headers={"X-CSRF-Token": csrf}, json={})
            assert sweep.status_code == 200 and sweep.json()["checked"] == 1 and sweep.json()["verified"] == 1

            bad_time = client.post("/api/analyses", headers={"X-CSRF-Token": csrf}, json={"clip_id": clip["id"], "transaction_time": "99:99:99"})
            assert bad_time.status_code == 422
            created = client.post("/api/analyses", headers={"X-CSRF-Token": csrf}, json={
                "clip_id": clip["id"], "transaction_time": "00:00:04", "window_seconds": 5,
                "transaction_ref": "SYNTH-TXN-0042",
            })
            assert created.status_code == 202, created.text
            analysis_id = created.json()["id"]
            deadline = time.time() + 90
            analysis_result = None
            while time.time() < deadline:
                analysis_result = client.get(f"/api/analyses/{analysis_id}").json()
                if analysis_result["status"] in {"completed", "failed"}:
                    break
                time.sleep(0.25)
            assert analysis_result and analysis_result["status"] == "completed", analysis_result
            assert analysis_result["result"]["sampledFrames"] > 0
            assert analysis_result["result"]["windowStart"] == 0
            completed_audit = next(row for row in client.get("/api/audit").json() if row["action"] == "analysis.completed")
            assert f"operator={admin_user['id']}" in completed_audit["note"]

            # Synthetic fixture rows exercise the review/search/export routes without real identities.
            second = client.post(
                "/api/clips?filename=synthetic-atm-2.mp4&camera_id=ATM-03",
                content=fixture.read_bytes(),
                headers=headers,
            ).json()
            second_analysis = uuid.uuid4().hex
            stamp = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
            image_path = Path(temp) / "synthetic-crop.jpg"
            cap = cv2.VideoCapture(str(fixture))
            ok, frame = cap.read()
            cap.release()
            assert ok and cv2.imwrite(str(image_path), frame)
            descriptor = [0.1767767] * 32
            candidate_ids = [uuid.uuid4().hex, uuid.uuid4().hex]
            with store.connect() as db:
                db.execute("""INSERT INTO analyses(id,clip_id,transaction_time,time_mode,clip_start_time,transaction_ref,
                              case_ref,window_seconds,status,result_json,error,created_at,updated_at)
                              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                           (second_analysis, second["id"], "00:00:04", "clip", "", "SYNTH-2", "FIR-TEST-01", 5,
                            "completed", "{}", "", stamp, stamp))
                for candidate_id, clip_id, analysis_fk in [
                    (candidate_ids[0], clip["id"], analysis_id),
                    (candidate_ids[1], second["id"], second_analysis),
                ]:
                    db.execute("""INSERT INTO candidates(id,analysis_id,clip_id,frame_seconds,track_id,score,
                        sharpness,illumination,face_size,pose,confidence,flags_json,image_path,descriptor_json)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (candidate_id, analysis_fk, clip_id, 3.5, 1, 82.0, 82, 91, 77, 88, .93,
                         json.dumps([]), str(image_path), json.dumps(descriptor)))

            reviewed = client.patch(f"/api/candidates/{candidate_ids[0]}/review", headers={"X-CSRF-Token": csrf},
                                    json={"status": "selected", "note": "Synthetic review check"})
            assert reviewed.status_code == 200
            search = client.post("/api/search", headers={"X-CSRF-Token": csrf}, json={"candidate_id": candidate_ids[0]})
            assert search.status_code == 200 and search.json()["matches"][0]["similarity"] > 99
            assert "not identity verification" in search.json()["notice"]
            pdf = client.get(f"/api/evidence/{analysis_id}.pdf")
            assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
            enhanced_res = client.get(f"/api/candidates/{candidate_ids[0]}/enhanced")
            assert enhanced_res.status_code == 200 and enhanced_res.headers.get("x-forensic-enhancement")
            redacted_res = client.get(f"/api/candidates/{candidate_ids[0]}/frame-redacted")
            assert redacted_res.status_code == 200 and redacted_res.content[:2] == b"\xff\xd8"

            manifest_res = client.get(f"/api/evidence/{analysis_id}/manifest.json")
            assert manifest_res.status_code == 200
            manifest_json = manifest_res.json()
            assert manifest_json["seal"]["algorithm"] == "HMAC-SHA256"
            assert client.post("/api/security/verify-manifest", headers={"X-CSRF-Token": csrf}, json={"manifest": manifest_json}).json()["verified"] is True
            tampered_manifest = json.loads(json.dumps(manifest_json))
            tampered_manifest["caseRef"] = "TAMPERED"
            assert client.post("/api/security/verify-manifest", headers={"X-CSRF-Token": csrf}, json={"manifest": tampered_manifest}).json()["verified"] is False

            assert client.get("/api/dvr-guidance").status_code == 200
            streams_res = client.get("/api/streams")
            assert streams_res.status_code == 200 and len(streams_res.json()["streams"]) == 4
            assert client.get("/api/streams/CAM-01/frame.jpg").status_code == 200
            assert client.post("/api/streams/CAM-01/source", headers={"X-CSRF-Token": csrf}, json={"source": "bad://url"}).status_code == 422
            assert client.post("/api/streams/CAM-01/source", headers={"X-CSRF-Token": csrf}, json={"source": "http://127.0.0.1:8080/video"}).status_code == 200
            assert client.post("/api/streams/CAM-01/source", headers={"X-CSRF-Token": csrf}, json={"source": "default"}).status_code == 200
            assert client.post("/api/streams/toggle", headers={"X-CSRF-Token": csrf}, json={"running": True}).json()["running"] is True
            assert client.post("/api/streams/toggle", headers={"X-CSRF-Token": csrf}, json={"running": False}).json()["running"] is False

            journal_res = client.post(
                "/api/journal/match",
                headers={"X-CSRF-Token": csrf},
                json={
                    "clip_id": clip["id"],
                    "clip_start_time": "2026-11-26T14:20:00+00:00",
                    "csv_text": "timestamp,txn_ref,atm_id,status\n2026-11-26T14:20:03+00:00,TXN-1,ATM-02,DISPUTED\n",
                    "window_seconds": 5,
                    "auto_queue": False,
                },
            )
            assert journal_res.status_code == 200 and journal_res.json()["inClipCount"] == 1
            assert client.get("/api/audit/export?format=csv").status_code == 200
            assert client.get("/api/audit/export?format=json").status_code == 200
            wl = client.post("/api/watchlist", headers={"X-CSRF-Token": csrf}, json={"candidate_id": candidate_ids[0], "label": "Suspect-Demo", "case_ref": "FIR-1"})
            assert wl.status_code == 201
            wl_id = wl.json()["id"]
            assert len(client.get("/api/watchlist").json()) == 1
            assert client.get(f"/api/watchlist/{wl_id}/image").status_code == 200
            journey = client.get("/api/cases/journey")
            assert journey.status_code == 200 and "readinessScore" in journey.json()
            assert client.delete(f"/api/watchlist/{wl_id}", headers={"X-CSRF-Token": csrf}).status_code == 200
            assert client.post("/api/events/clear-stream-alerts", headers={"X-CSRF-Token": csrf}).status_code == 200
            backup = client.post("/api/security/database-backups", headers={"X-CSRF-Token": csrf}, json={"passphrase": "SecureBackupPassphrase2026"})
            assert backup.status_code == 201, backup.text
            encrypted_copy = client.get(backup.json()["downloadUrl"])
            assert encrypted_copy.status_code == 200 and encrypted_copy.content.startswith(MAGIC)
            plaintext = decrypt_snapshot(encrypted_copy.content, "SecureBackupPassphrase2026")
            restored = sqlite3.connect(":memory:")
            restored.deserialize(plaintext)
            assert restored.execute("PRAGMA quick_check").fetchone()[0] == "ok"
            restored.close()
            try:
                decrypt_snapshot(encrypted_copy.content, "wrong backup passphrase")
                raise AssertionError("Wrong backup passphrase was accepted.")
            except ValueError:
                pass
            restore_target = Path(temp) / "restore-target" / "drishti.sqlite3"
            restore_target.parent.mkdir(parents=True)
            restore_target.write_bytes(b"prior database placeholder")
            with store.connect() as db:
                backup_filename = db.execute("SELECT filename FROM security_backups WHERE id=?", (backup.json()["id"],)).fetchone()[0]
            backup_path = store.BACKUPS / backup_filename
            restore_backup(backup_path, "SecureBackupPassphrase2026", restore_target)
            with sqlite3.connect(restore_target) as checked_restore:
                assert checked_restore.execute("PRAGMA quick_check").fetchone()[0] == "ok"
            assert restore_target.with_name("drishti.sqlite3.pre-restore").read_bytes() == b"prior database placeholder"
            restored_digest = hashlib.sha256(restore_target.read_bytes()).hexdigest()
            try:
                restore_backup(backup_path, "incorrect passphrase", restore_target)
                raise AssertionError("Restore accepted an incorrect passphrase.")
            except ValueError:
                pass
            assert hashlib.sha256(restore_target.read_bytes()).hexdigest() == restored_digest
            assert client.get("/api/security/overview").json()["backup"]["id"] == backup.json()["id"]
            assert client.get("/api/events").status_code == 200
            assert any(row["action"] == "candidate.selected" for row in client.get("/api/audit").json())
            assert client.get("/api/audit/integrity").json()["verified"] is True
            with store.connect() as db:
                changed = db.execute("SELECT id,note FROM audit_log ORDER BY rowid LIMIT 1").fetchone()
                db.execute("UPDATE audit_log SET note='tampered test record' WHERE id=?", (changed["id"],))
            assert client.get("/api/audit/integrity").json()["verified"] is False
            with store.connect() as db:
                db.execute("UPDATE audit_log SET note=? WHERE id=?", (changed["note"], changed["id"]))
            assert client.get("/api/audit/integrity").json()["verified"] is True
            assert client.get("/api/reports").status_code == 200
            assert client.delete(f"/api/clips/{clip['id']}", headers={"X-CSRF-Token": csrf}).status_code == 200
            assert client.get(f"/api/clips/{clip['id']}/video").status_code == 404

        print("PASS: account bootstrap, approval, login/RBAC/CSRF, redacted auth throttling, SQLite checks,")
        print("      evidence integrity sweep, encrypted DB backup/restore and passphrase validation, upload, 4 channels, metadata,")
        print("      SHA-256/tamper check, timestamp validation,")
        print("      person/face analysis, candidate review/search, audit tamper check, report, PDF export, and delete.")


if __name__ == "__main__":
    run()
