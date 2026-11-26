# Drishti — ATM Forensic Video Review

Drishti is a local-first ATM video evidence review product for PS04. It narrows a clip to a supplied transaction time, detects people and faces, ranks candidate frames using visible quality signals, and lets an investigator record a review or compare appearance candidates across other uploaded clips.

The interface is Rajasthan Police-inspired and is not an official Rajasthan Police system. It has no live bank CCTV connection. Four channel cards organize **uploaded recordings**; they are not live feeds. No real personal data, Aadhaar/criminal database, identity watchlist, external API, cloud database, or telemetry is used.

## Quick setup (macOS/Linux)

Requirements: Python 3.11+, Node.js 18+, and npm. FFmpeg is optional for videos OpenCV decodes directly; it is used for local conversion of compatible DVR/NVR exports.

```bash
./setup.sh
./start.sh
```

Open `http://127.0.0.1:5174`. The API docs are at `http://127.0.0.1:8000/api/docs`.

On first launch, create the administrator account in the sign-up portal. The first account is administrator; later sign-ups stay pending until an administrator approves them under **Access control**. Passphrases are stored as salted scrypt hashes. Sessions use an HTTP-only, same-site cookie, expire after eight hours, and require a CSRF token for writes. Accounts and sessions are local to the configured data directory. Password recovery is not configured, so protect the administrator passphrase and back up the data directory securely.

Setup fetches the OpenCV Zoo MediaPipe person detector and YuNet face detector into the ignored `models/` directory. The downloader pins upstream revisions and verifies SHA-256 before use. The app makes no model or cloud requests at runtime. If the person model is unavailable, OpenCV HOG is used as a lower-accuracy fallback; YuNet is required for face candidates. See [LICENSES.md](LICENSES.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

To build one local-serving bundle: `npm run build`, then `.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`; FastAPI serves `dist/` when present. Keep the host bound to loopback for a single-workstation install.

## Workflow

1. Upload a supported MP4, AVI, MOV, MKV, WMV, FLV, MPEG, or MPG file to one of four local ATM view channels.
2. Enter either a clip-relative `HH:MM:SS` transaction time, or an absolute bank transaction time plus the CCTV clip start timestamp.
3. Choose the time window (±5 seconds to ±5 minutes) and run the local analysis.
4. Review candidate crops, quality components, reliability flags, track/time context, and the source clip. Mark a candidate for review or exclude it, add a note, search other uploaded clips for visual similarity, and export a PDF evidence sheet with source/analysis SHA-256 fingerprints.
5. Review reports and the local audit trail. Removing a clip removes its analyses and extracted crops.

All persistent records and uploads are stored under `backend/data/`. Override the location with `DRISHTI_DATA_DIR`.

The video library can recompute both file fingerprints to alert if local evidence bytes changed after ingest. A hash match detects byte changes; it does not prove who recorded or supplied the original footage.

## Security controls

- **Security Center (administrator only):** SQLite `quick_check`, foreign-key validation, audit-chain verification, local file-mode checks, pending-account/failed-sign-in signals, and host/network boundary reminders.
- **Browser/API hardening:** Content Security Policy, anti-framing and MIME-sniff headers, privacy/referrer policy, same-origin resource policy, disabled camera/microphone/location APIs, and no-store on API responses.
- **Evidence integrity sweep:** rehashes the original and analysis copy for each stored clip, records the sweep in the audit chain, and raises a warning event for mismatches.
- **Encrypted database snapshots:** SQLite's online backup API creates a consistent metadata snapshot in memory; the app encrypts it with AES-256-GCM and a passphrase-derived key. The passphrase is not stored. The snapshot excludes uploaded videos and candidate crops; protect those with a separate encrypted filesystem backup.
- **Restore command:** stop the app, then run `python scripts/restore_database.py /path/to/drishti-db-....enc`. It validates the passphrase, GCM authentication, SQLite integrity and foreign keys, and preserves the prior database before replacing it. Restore the matching media directories separately.
- The application hardens its local data directory to mode `0700`, the SQLite file to `0600`, and enables SQLite `secure_delete`. These OS permissions are defense-in-depth for a single-user local machine, not database encryption. Enable FileVault/BitLocker/LUKS for the host volume; the Security Center marks this as an operator check.
- Failed sign-ins are rate-limited; throttle records keep a one-way identifier hash rather than the submitted email. Authentication denials enter the audit chain without passwords or raw email addresses.

## Detection and reliability

- Person detection uses the local OpenCV Zoo MediaPipe ONNX detector and a lightweight IoU association to keep track IDs between sampled frames.
- Face detection uses OpenCV Zoo YuNet. Frames in the configured transaction window are sampled at 0.75-second intervals, with a 1,600-frame cap.
- Quality is a ranking aid built from sharpness, illumination, face size, face angle estimate, and detector confidence. Flags include soft focus, low light/overexposure, turned face, and small face.
- Cross-clip search uses normalized grayscale histograms as a lightweight baseline. It is **appearance similarity only**, not face recognition or identity verification; expect false matches and missed matches.
- No mask/helmet classifier or ATM interaction/action classifier is included. “Person at keypad/cash slot” is an investigator decision aided by the clip timeline; the product does not claim to infer transaction intent.
- Output quality depends on clip resolution, lighting, angle, codec, and the supplied timestamp. A human must verify the original footage and transaction record.
- Local audit entries are hash-linked and verifiable at `/api/audit/integrity`. This is tamper-evident against record edits or broken links; it is not immutable against a privileged rewrite of the local database. Operational deployments need signed, externally retained checkpoints and access controls.

## Integration and deployment boundary

- REST API and OpenAPI contract: `http://127.0.0.1:8000/api/docs`.
- Four channels are identifiers for uploaded file evidence, not camera adapters. For a bank deployment, add an approved DVR export connector or evidence-management adapter; do not enable a live feed without formal authorization.
- The portal provides local administrator/investigator roles, approval, account disable, session expiry, and CSRF protection. It does not provide enterprise SSO/MFA, password recovery, multi-workstation operation, or deployment-grade identity lifecycle management. Keep the server bound to loopback. Before a Cyber Security Cell pilot, integrate approved SSO/MFA and managed RBAC, add an evidence-storage policy, signed external audit checkpoints, tested backup/restore, and a security review.
- Active SQLite records and evidence files are not application-encrypted at rest. Use encrypted host storage. The encrypted export protects a database snapshot in transit/portable storage only; loss of its passphrase makes it unrecoverable.
- The API's file storage and SQLite database are under `backend/data/`; set `DRISHTI_DATA_DIR` to an access-controlled volume for a pilot. Back up the whole directory consistently while the service is stopped.
- Product integration points and security-cell rollout checklist: [docs/INTEGRATION_NOTES.md](docs/INTEGRATION_NOTES.md) and [docs/PRODUCTIZATION.md](docs/PRODUCTIZATION.md).

## Tests

```bash
python scripts/smoke_test.py
npm run build
python scripts/doctor.py
```

The smoke test creates only temporary synthetic video, exercises account bootstrap/approval/login/RBAC/CSRF plus the local API, then removes its temporary workspace. It checks database health, evidence rehashing, encrypted snapshot and wrong-passphrase rejection, upload/validation, metadata, timestamp analysis, four slots, review/search, hash-chain tampering, reports, PDF export, and deletion. It does not measure detection accuracy on ATM footage. A manual browser UI verification report is in [docs/UI_TEST_REPORT.md](docs/UI_TEST_REPORT.md).

## Repository references

- `../sih-2026-raw`: YOLO person detection, tracking, local video ingestion, React dashboard and FastAPI API patterns. Border-event, ANPR, face registry, Supabase and cloud transmission paths were left out of this product.
- `../gods-eye-view`: public CCTV source/catalog/provider architecture. Its city-camera catalog and external proxy streams are not ATM evidence and are not connected here.

Use only the hackathon sample dataset or synthetic clips for demos. Get explicit permission before using any other footage.
