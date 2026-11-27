# Drishti — ATM CCTV Forensic Video Review & Local Surveillance Console

**Drishti** is an air-gapped, local-first video analytics and forensic evidence review workstation built for **Rajasthan Police Cyber Security Hackathon 2026 — PS04 (ATM CCTV Suspect Face Extraction for Card & ATM Fraud Investigation)**.

It links ATM CCTV recordings (and proprietary DVR/NVR exports) to bank transaction timestamps or Electronic Journal (EJ) logs, detects and tracks people near the terminal keypad and cash slot, ranks the clearest candidate face frames with occlusion/quality flags, searches across clips using **SFace 128-D** face embeddings, monitors up to 4 local/IP-webcam feeds against a case watchlist in real time, and exports cryptographically signed evidence sheets.

> **PS04 Scope & Compliance Notice:** The interface is Rajasthan Police-inspired and is **not** an official Rajasthan Police system. All processing runs locally on `127.0.0.1` with zero external APIs, cloud databases, telemetry, Aadhaar lookups, or criminal database connections. Live bank CCTV connections are never established; similarity scores and watchlist alerts are strictly investigative decision-support aids requiring human verification.

---

## Key Capabilities

### 1. Transaction-Time Forensic Analysis & Batch EJ Matcher
- **Flexible Transaction Linking:** Enter a clip-relative timestamp (`HH:MM:SS`) or an absolute bank timestamp paired with the CCTV clip start time, plus a configurable search window (`±5 seconds` to `±5 minutes`), FIR/Case reference, and Bank Transaction Reference / RRN.
- **ATM Electronic Journal (CSV) Matcher (`/api/journal/match`):** Upload a bank EJ CSV export to match transaction records against local clip wall-clock windows (with local timezone alignment) and queue disputed withdrawals directly for analysis.
- **Channel Management (`ATM-01` – `ATM-04`):** Assign, replace, or delete footage per channel (`Entry view`, `Keypad view`, `Cash slot`, `Exit view`). Clicking **Load Demo Case** loads 2 pilot ATM feeds (`ATM-01` & `ATM-02`) while leaving `ATM-03` & `ATM-04` open for live uploads.

### 2. Multi-Format & DVR/NVR Forensics
- **Supported Formats:** `MP4`, `AVI`, `MOV`, `MKV`, `WMV`, `FLV`, `MPEG`/`MPG`, plus compatible DVR/NVR exports (`H264`, `264`, `DAV`, `ASF`, `TS`, `M4V`, `VOB`).
- **Safe Normalization & Container Checks ([`backend/forensics.py`](backend/forensics.py)):** Probes streams via `ffprobe`, normalizes non-standard containers with local FFmpeg restricted via `-protocol_whitelist file,pipe`, inspects container metadata, and runs frame-continuity / luminance splice checks (`/api/dvr-guidance` reports conversion tips for unsupported proprietary formats).

### 3. Person Tracking, YuNet Face Extraction & SFace 128-D Embeddings
- **Lightweight Person-Only Tracking ([`backend/analysis.py`](backend/analysis.py)):** Runs local OpenCV Zoo **MediaPipe** person detection (`person_detection_mediapipe_2023mar.onnx`, with HOG fallback) and IoU track association under thread-safe inference locks (`_person_infer_lock`). Car, ANPR, and border-detection pipelines are intentionally omitted.
- **Face Detection & Quality Ranking:** Samples frames at `0.75s` intervals (up to `1,600` frames) inside the transaction window using **YuNet** (`face_detection_yunet_2023mar.onnx`), padding tight ROIs and scoring sharpness, illumination, face size, pose angle, and keypad/slot proximity.
- **Reliability & Behaviour Flags:** Flags `possible mask`, `possible cap / headgear`, `possible helmet`, `partial face`, `soft focus`, `low light`, `overexposed`, `turned face`, `small face`, `low resolution`, and `low face confidence`, alongside advisory **shoulder-surfing** (multi-person zone occupancy) and **card-slot skimming / tampering** cues.
- **True Deep Face Embeddings (`/api/search`):** Uses **SFace** (`face_recognition_sface_2021dec.onnx`) 128-D embeddings (`_sface_infer_lock`) for cross-clip cosine similarity search across clips in the local vault.

### 4. Inspection, Enhancement & Privacy Redaction (`Evidence review`)
- **Forensic Light Studio:** Live **Brightness** (`60–200%`) and **Contrast** (`60–220%`) inspection sliders directly in the evidence viewer.
- **Labelled Enhancement (`/api/candidates/{id}/enhanced`):** Toggle between **Original Raw** and deterministic **Enhanced (2× Lanczos4 + CLAHE + bilateral + unsharp)** — non-generative and visibly watermarked as an enhanced review aid.
- **Bystander Privacy Redaction (`/api/candidates/{id}/frame-redacted`):** Generates a **Privacy Frame** preview that Gaussian-blurs bystanders outside the target suspect while preserving the selected candidate and stamping SHA-256 provenance.
- **Human Review & Exports:** Mark candidates for review or exclusion with investigator notes, export a **Sealed PDF Evidence Sheet** (`/api/evidence/{id}.pdf`), and download an **HMAC-SHA256 Signed Manifest** (`/api/evidence/{id}/manifest.json`).

### 5. 4-Stream Surveillance Wall, Auto DB Evidence & Repeat-Person Alerting ([`backend/streams.py`](backend/streams.py))
- **Unified Control-Room View (`Live CCTV`):** Auto-starts on launch and displays 4 camera slots (`CAM-01` – `CAM-04`) side-by-side with **Live DB evidence & repeat tracker**, **Auto-captured incident snapshots**, **Live suspicious alerts**, and **Live detection log** on the same screen.
- **2 Default Feeds + 2 Open Slots:** Starts `CAM-01` and `CAM-02` on local pilot clips while leaving `CAM-03` and `CAM-04` ready for custom sources.
- **Add / Change / Delete & IP Webcam Support:** Attach local video clips, Android **IP Webcam** URLs (`http://<phone-ip>:8080/video`), local `rtsp://...` feeds, or Mac/USB camera indices (`0`–`4`) to any slot, and run **Capture to Case** straight from a `120`-frame rolling buffer.
- **Automatic DB Evidence Collection, Scene Incident Photos & Repeat Alerts (`/api/live-evidence`, `/api/live-incidents`):** As live feeds run, AI detects shoulder-surfing, extended loitering, mask/helmet occlusion, and keypad/card-slot surface tampering (`stream.tamper_skimming`), saving annotated scene snapshots + SHA-256 hashes into SQLite (`live_incidents`). Detected faces (`>= 0.56` normalized SFace threshold) are automatically cropped, hashed, and stored under `live_identities` + `live_sightings` (`SUB-001`, `SUB-002`, ...); returning or switching cameras immediately raises a **`stream.repeat_person` alert** (`REPEAT PERSON ALERT`) and saves a fresh evidence crop.
- **Raw-Frame Inference & Live Case Watchlist (`/api/watchlist`):** Runs MediaPipe + YuNet + SFace matching on **raw unannotated frames** before drawing HUD overlays to prevent false badge/text crops. Arm any extracted suspect face from **Evidence review** or **Live DB evidence** onto the local **Live Case Watchlist** for real-time cross-camera alerts.

### 6. Case Intel & Multi-Camera Suspect Journey (`/api/cases/journey`)
- Reconstructs cross-camera suspect appearances across uploaded clips (`ATM-01 → ATM-02`, filtering out same-camera self-links), summarizes watchlist hits, live repeat visitors, and displays an audit/chain-of-custody readiness brief.

---

## Navigation Tabs (UI Workspace)

The sticky top navigation bar exposes 9 role-aware workspace tabs (`App.tsx`):

| Tab | Role | Purpose |
| :--- | :--- | :--- |
| **Live CCTV** | All | Auto-started 4-camera live AI monitor (person, face, occlusion, tampering, shoulder-surfing, repeat visitor & watchlist), auto DB evidence & incident photos |
| **Case intel** | All | Multi-camera suspect journey graph, live DB repeat counts, armed SFace watchlist cards, & courtroom readiness summary |
| **Clip forensics** | All | 4 ATM channel slots (`ATM-01`–`04` add/change/delete), transaction linking, EJ CSV batch matcher, demo loader, & **Evidence review** |
| **Video library** | All | Multi-format ingestion, FFmpeg normalization, codec/continuity forensics, & per-clip SHA-256 verification |
| **Face search** | All | SFace 128-D embedding cosine similarity search across all local clips |
| **Reports** | All | Forensic throughput, quality/occlusion metrics, and 4-stream telemetry |
| **Audit** | All | Tamper-evident hash-chained operator actions, alert clearing, & CSV / signed JSON audit export (`/api/audit/export`) |
| **Access** | Admin | Local investigator registration approval, role inspection, and account enable/disable |
| **Security** | Admin | SQLite integrity checks, full SHA-256 vault sweep, AES-256-GCM DB snapshot backup/download, & **Manifest Seal Verifier** |

---

## Cyber Security & Chain-of-Custody Controls ([`backend/security.py`](backend/security.py), [`backend/auth.py`](backend/auth.py), [`backend/store.py`](backend/store.py))

- **Authentication & RBAC:** First user created in the sign-up portal becomes `administrator`; subsequent sign-ups remain pending until approved in **Access**. Passphrases use salted `scrypt` hashes; sessions use 8-hour `HttpOnly; SameSite=Strict` cookies with CSRF token verification on state-changing requests.
- **Brute-Force Protection:** Failed sign-ins are rate-limited using one-way hashed identifiers (no plaintext emails stored in throttle tables or denial events).
- **HTTP & CSP Hardening:** Strict Content Security Policy, `X-Frame-Options` / `frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Cross-Origin-Resource-Policy: same-origin`, `Permissions-Policy` disabling browser camera/microphone/geolocation APIs, and `Cache-Control: no-store` on API responses.
- **Cryptographic Integrity:**
  - Dual SHA-256 fingerprints (`original` upload bytes + `normalized` review bytes) checked on demand and via full-vault sweeps (`/api/security/evidence-check`).
  - Hash-chained SQLite audit ledger verifiable at `/api/audit/integrity`.
  - **HMAC-SHA256 Signed Manifests** (`signing.key` stored mode `0600` in data dir) verifiable anytime via `/api/security/verify-manifest` inside **Security**.
- **Encrypted Metadata Backups & Restore:** Downloads an in-memory SQLite online backup encrypted with **AES-256-GCM** using an operator passphrase (never stored). Restore while the service is stopped:
  ```bash
  python scripts/restore_database.py /path/to/drishti-db-....enc
  ```
- **Local Storage Hardening:** Data directory (`backend/data/`, overridable with `DRISHTI_DATA_DIR`) is created with mode `0700`, SQLite files with mode `0600`, and `PRAGMA secure_delete = ON`. Use full-disk encryption (FileVault / LUKS / BitLocker) for host volume protection.

---

## Quick Setup & Run (macOS / Linux)

**Prerequisites:** Python 3.11+, Node.js 18+ (`npm`), and local `ffmpeg` / `ffprobe` (recommended for DVR/NVR containers and codec probing).

```bash
./setup.sh
./start.sh
```

What `./setup.sh` runs automatically:
1. Creates `.venv` and installs Python dependencies from `requirements.txt`.
2. Installs Node packages via `npm install`.
3. Downloads pinned OpenCV Zoo ONNX models via `scripts/download_models.py` with strict SHA-256 verification.
4. Generates/prepares the 4 coherent local pilot feeds in `demo_feeds/` via `scripts/prepare_demo_feeds.py`.

What `./start.sh` runs:
- Executes `scripts/doctor.py` to verify dependencies and model checksums.
- Launches `scripts/run_local.py`:
  - **Frontend UI:** `http://127.0.0.1:5174`
  - **Backend API & OpenAPI Docs:** `http://127.0.0.1:8000/api/docs`

**Single-Bundle Production Serving:**
```bash
npm run build
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
When `dist/` is present, FastAPI serves the built SPA directly on loopback (`127.0.0.1:8000`).

---

## Local AI Models (Pinned & Checksummed)

[`scripts/download_models.py`](scripts/download_models.py) downloads and verifies these OpenCV Zoo weights into the git-ignored `models/` folder (no runtime downloads ever occur):

| Model | Purpose | SHA-256 |
| :--- | :--- | :--- |
| `person_detection_mediapipe_2023mar.onnx` | Local person detection & tracking | `47fd5599d6fa17608f03e0eb0ae230baa6e597d7e8a2c8199fe00abea55a701f` |
| `face_detection_yunet_2023mar.onnx` | Face & 5-point landmark detection | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` |
| `face_recognition_sface_2021dec.onnx` | SFace 128-D cross-clip & watchlist embeddings | `0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79` |

See [LICENSES.md](LICENSES.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

---

## Project Layout

```text
CYBER-HACK/
├── backend/
│   ├── main.py          # FastAPI routes, RBAC/CSRF middleware, journal matcher, evidence PDF/manifest exports
│   ├── analysis.py      # MediaPipe person tracking, YuNet faces, SFace 128-D embeddings, quality/occlusion flags
│   ├── forensics.py     # ffprobe metadata, FFmpeg DVR normalization, splice detection, CLAHE enhancement, privacy blur
│   ├── streams.py       # 4-stream local/IP-Webcam/RTSP manager, raw-frame watchlist matching, rolling 120-frame buffer
│   ├── store.py         # SQLite persistence, schema migrations, hash-chained audit ledger, watchlist & journey data
│   ├── security.py      # Path containment, security headers, AES-256-GCM backups, HMAC-SHA256 manifest signing/verify
│   └── auth.py          # scrypt password hashing, session cookies, CSRF tokens, login throttling
├── src/
│   ├── App.tsx          # React SPA (9 workspace tabs, Portaled Privacy Frame modal, Light studio, Slot Source modals)
│   ├── api.ts           # Typed API client & CSRF request helpers
│   └── styles.css       # Rajasthan Police-inspired light command theme & responsive breakpoints
├── scripts/
│   ├── doctor.py            # Environment & SHA-256 model integrity check
│   ├── download_models.py   # Pinned ONNX model downloader
│   ├── prepare_demo_feeds.py# Generates demo_feeds/ pilot CCTV MP4s
│   ├── run_local.py         # Launches Uvicorn (8000) + Vite (5174) locally
│   ├── smoke_test.py        # End-to-end automated verification across API, RBAC, FFmpeg, SFace, streams & manifests
│   ├── restore_database.py  # Encrypted AES-256-GCM SQLite snapshot restore CLI
│   └── run_ui_test_server.py# Local static/dev test harness
├── demo_feeds/          # 4 compact local pilot feeds (cam_01_vestibule.mp4 .. cam_04_exit.mp4)
└── docs/                # Pitch guide, architecture/integration notes, productization & UI test report
```

---

## Verification & Tests

Run the full verification suite:

```bash
python3 scripts/doctor.py
npm run build
python3 -m compileall -q backend scripts
python3 scripts/smoke_test.py
```

`scripts/smoke_test.py` spins up an isolated temporary data directory and synthetic clips to verify:
- Bootstrap admin signup, investigator approval, login throttling, RBAC enforcement, and CSRF protection
- Multi-format upload, metadata extraction, DVR guidance, container validation, and SHA-256 integrity checks
- Transaction timestamp linking, batch EJ CSV matching, 2-clip demo case loading, candidate extraction, SFace 128-D search, enhanced & privacy-redacted frame endpoints
- 4-stream pilot start/stop, custom source attachment, rolling-buffer capture, live watchlist arming/deletion, and cross-camera suspect journey reconstruction
- Audit hash-chain integrity & tamper detection, reports, sealed PDF evidence export, HMAC-SHA256 manifest generation/verification, and AES-256-GCM backup/wrong-passphrase rejection

---

## Documentation & Reference Architecture

- [Hackathon Pitch & 60-Second Demo Guide](docs/HACKATHON_PITCH_GUIDE.md)
- [Product Specification](PRODUCT.md) & [UI/UX Design Guide](DESIGN.md)
- [Integration Notes](docs/INTEGRATION_NOTES.md) & [Security Cell Productization Checklist](docs/PRODUCTIZATION.md)
- [UI Verification Report](docs/UI_TEST_REPORT.md)
- Reference repositories integrated conceptually (local-only, no cloud/external dependencies carried over):
  - `../sih-2026-raw`: local person detection, tracking, and video ingestion patterns.
  - `../gods-eye-view`: multi-stream camera wall and source catalog concepts adapted for 4 local ATM/IP-Webcam slots.

> Use only hackathon-provided sample clips or synthetic footage unless explicit authorization is obtained.
