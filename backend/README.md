# Local API

The API binds to loopback only. Uploads, SQLite records, candidate crops, and PDF exports stay under `backend/data/` (or `DRISHTI_DATA_DIR`). Cloud database and remote services are not configured.

Start it from the project root:

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Analysis accepts clip-relative `HH:MM:SS`. It samples only the configured transaction window. InsightFace SCRFD-10GF is the primary face detector, with YuNet as the fallback when the SCRFD weights are absent. MediaPipe detects people and ByteTrack associates detections across frames. YOLO11n-pose supplies the live head-down cue. Run `python scripts/download_models.py --insightface --advanced-vision` once while online to fetch checksum-pinned assets. Inference runs locally. License notices are at the repository root.

API routes require an approved local account session; only health and the first-run/auth endpoints are public. The first sign-up creates the administrator; later accounts require approval. Cookies are HTTP-only and same-site, and state-changing API requests require a CSRF token. This is local account control, not enterprise identity management. Keep it bound to loopback; add approved SSO/MFA, managed RBAC, and TLS before organizational deployment.

The admin-only Security Center runs SQLite integrity/foreign-key checks, validates audit links, inspects local data modes, summarizes sign-in denials and lets administrators verify all clip hashes. Encrypted metadata snapshots use SQLite's online backup API plus AES-256-GCM and a 16-character minimum administrator-supplied passphrase. They exclude video and candidate media. Restore only with the server stopped: `python scripts/restore_database.py /path/to/backup.enc`. The active DB and media are not application-encrypted at rest; require host disk encryption.
