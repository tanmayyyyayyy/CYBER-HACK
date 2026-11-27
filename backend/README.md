# Local API

The API launch examples bind to loopback only. Uploads, SQLite records, candidate crops, and PDF exports stay under `backend/data/` (or `DRISHTI_DATA_DIR`). Cloud database and remote services are not configured.

Start it from the project root:

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Analysis accepts clip-relative `HH:MM:SS`. It samples only the configured transaction window. YuNet face weights and the OpenCV Zoo MediaPipe person detector are local ONNX assets; OpenCV HOG is the person-detection fallback. Run `python scripts/download_models.py` once while online to fetch pinned/checksummed assets. No model is fetched at runtime. License notices are at the repository root.

API routes require an approved local account session; only health and the first-run/auth endpoints are public. The first sign-up creates the administrator; later accounts require approval. Cookies are HTTP-only and same-site, and state-changing API requests require a CSRF token. Set `DRISHTI_COOKIE_SECURE=1` when serving through HTTPS. This is local account control, not enterprise identity management. Keep it bound to loopback; add approved SSO/MFA, managed RBAC, and TLS before organizational deployment.

The admin-only Security Center runs SQLite integrity/foreign-key checks, validates audit links, inspects local data modes, summarizes sign-in denials and lets administrators verify all clip hashes. Encrypted metadata snapshots use SQLite's online backup API plus AES-256-GCM and a 16-character minimum administrator-supplied passphrase. They exclude video and candidate media. Restore only with the server stopped: `python scripts/restore_database.py /path/to/backup.enc`. The active DB and media are not application-encrypted at rest; require host disk encryption.
