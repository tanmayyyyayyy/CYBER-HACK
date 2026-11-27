# Drishti — PS04 ATM CCTV Suspect Face Extraction & Forensic Evidence Platform

**Drishti** is a local-first video analytics and forensic evidence review workstation built for **Rajasthan Police Cyber Security Hackathon 2026 — PS04 (ATM CCTV Suspect Face Extraction for Card & ATM Fraud Investigation)**.

> **Project status: hackathon demonstrator.** It is not approved for operational surveillance, handling real citizen footage, dispatching guards, or submitting generated files as statutory evidence. Demo outputs, face matches, alerts, and certificates require independent validation and authorized human review.

It ingests ATM CCTV footage (including proprietary DVR/NVR exports), links clips to bank transaction timestamps or Electronic Journal (EJ) logs, tracks people inside the ATM keypad/cash-slot zone, ranks the clearest candidate face frames with occlusion/quality flags, searches across clips via **SFace 128-D** deep face embeddings, and exports **BSA Section 63 Certificates**, **Sealed PDF Evidence Sheets**, **DPDP Bystander-Redacted Frames**, and **Offline Forensic Case Bundles (`.zip`)**.

Alongside the primary PS04 clip-forensic workflow, Drishti includes a sandboxed **Local Real-Time AI Console** (`Real-time AI`) capable of monitoring local clips, USB cameras, or Android IP Webcams—automatically collecting face evidence & suspicious incident snapshots into SQLite and alerting when the same person returns repeatedly.

> **PS04 scope:** The interface is Rajasthan Police-inspired and has no official affiliation. Video processing and evidence storage run locally. Optional blockchain verification contacts the configured node. The on-chain record contains a manifest fingerprint and format marker. Quality scores and watchlist alerts require human review.

Cryptographic hashes and local HMAC seals detect some changes but are not independent signatures or immutable chain-of-custody records. Generating a BSA Section 63 certificate PDF or a DPDP-labeled redacted frame does not establish legal compliance. The portal's siren is browser audio; there is no real SMS, phone, police, or guard dispatch integration.

---

## Key Capabilities

### 1. Transaction-Time Forensic Analysis & Batch EJ Matcher (`Case desk`)
- **Transaction Timestamp Linking:** Enter clip-relative time (`HH:MM:SS`) or absolute bank timestamp + CCTV clip start time across a configurable window (`±15s` to `±5m`), paired with FIR/Case ref and Bank TXN Ref / RRN.
- **ATM Electronic Journal (CSV) Matcher (`/api/journal/match`):** Upload or paste bank switch / ATM EJ CSV logs to match transactions against local clip wall-clock windows (timezone-aligned) and auto-queue disputed withdrawals.
- **4 ATM Evidence Channels (`ATM-01` – `ATM-04`):** Upload, replace, or delete footage per slot (`Entry view`, `Keypad view`, `Cash slot`, `Exit view`). **Load Demo (2 Clips)** loads pilot recordings onto `ATM-01` & `ATM-02` while leaving `ATM-03` & `ATM-04` open for custom uploads or IP Webcams.

### 2. Multi-Format & DVR/NVR Ingestion & Container Forensics ([`backend/forensics.py`](backend/forensics.py))
- **Supported Formats:** `MP4`, `AVI`, `MOV`, `MKV`, `WMV`, `FLV`, `MPEG`/`MPG`, plus DVR/NVR exports (`H264`, `264`, `DAV`, `ASF`, `TS`, `M4V`, `VOB`).
- **Safe Normalization & Validation:** Probes streams with `ffprobe`, validates codecs/resolution/FPS/duration, normalizes non-browser codecs locally via FFmpeg (`-protocol_whitelist file,pipe`), and checks frame continuity / luminance splice cues. Vendor conversion guidance for unsupported formats is served at `/api/dvr-guidance`.

### 3. Person Tracking, YuNet Face Extraction & SFace 128-D Embeddings ([`backend/analysis.py`](backend/analysis.py))
- **Lightweight Person-Only Tracking:** Uses OpenCV Zoo **MediaPipe** person detection (`person_detection_mediapipe_2023mar.onnx`, with HOG fallback) and IoU tracking under thread-safe locks (`_person_infer_lock`). Vehicle, ANPR, and border-fence detectors are excluded.
- **Face Detection & Quality Scoring:** Samples frames at `0.75s` intervals (up to `1,600` frames) inside the transaction window using **YuNet** (`face_detection_yunet_2023mar.onnx`), ranking frames by sharpness, illumination, face size, pose angle, and terminal proximity.
- **Reliability & Behaviour Flags:** Flags `possible mask`, `possible cap / headgear`, `possible helmet`, `partial face`, `soft focus`, `low light`, `overexposed`, `turned face`, `small face`, `low resolution`, and `low face confidence`, plus advisory **shoulder-surfing** (multi-person zone occupancy) and **card-slot / keypad tampering** cues.
- **Cross-Clip Face Search (`Face search` / `/api/search`):** Uses normalized **SFace** 128-D embeddings (`face_recognition_sface_2021dec.onnx` under `_sface_infer_lock`) for cosine-similarity search across other clips in the vault.

### 4. Inspection, Enhancement, Privacy Redaction & Court Exports (`Evidence review`)
- **Physical characteristics:** Every completed review includes the analyzed window's sample count, highest-ranked face crop, and quality flags. Inspect the full source frame at its timestamp. The panel explains the evidence required for height, weight, age, and gender assessments. It does not generate demographic predictions.
- **Forensic Light Studio:** Interactive **Brightness** (`60–200%`) and **Contrast** (`60–220%`) inspection sliders.
- **Labelled Enhancement (`/api/candidates/{id}/enhanced`):** Toggle **Original Raw** vs. deterministic **Enhanced (2× Lanczos4 + CLAHE + bilateral + unsharp)** — non-generative and clearly watermarked as a review aid.
- **DPDP Bystander Privacy Redaction (`/api/candidates/{id}/frame-redacted`):** Generates a downloadable **Privacy Frame** that Gaussian-blurs bystanders outside the target suspect while preserving the selected candidate and SHA-256 provenance.
- **Court & Compliance Exports:**
  - **Sealed PDF Evidence Sheet (`/api/evidence/{id}.pdf`):** Summarizes transaction link, dossier fields, ranked crops, quality metrics, flags, and SHA-256 hashes.
  - **BSA Section 63 Electronic Record Certificate PDF (`/api/evidence/{id}/bsa63.pdf`):** Generates a statutory Section 63 Bharatiya Sakshya Adhiniyam 2023 certificate naming local workstation hostname, IO credentials, FIR/NCRP 1930 IDs, dual SHA-256 hashes, audit head hash, and HMAC seal.
  - **HMAC-SHA256 Manifest JSON (`/api/evidence/{id}/manifest.json`):** Cryptographic payload + HMAC signature verifiable inside **Security**.
  - **Offline Forensic Case Bundle `.zip` (`/api/evidence/{id}/bundle.zip`):** Single-click archive containing both PDFs, signed `evidence-manifest.json`, `case-dossier.json`, signed `audit-trail.json`, raw & enhanced stills, top bystander-redacted DPDP frame, and `VERIFY-OFFLINE.txt`.

### 5. Local Real-Time AI Console, Auto DB Evidence & Repeat-Person Alerting ([`backend/streams.py`](backend/streams.py))
- **Sandboxed 4-Stream Control Room (`Real-time AI`):** Auto-starts on server boot across `CAM-01`–`CAM-04` (`2` local demo feeds + `2` open slots for video files, Android **IP Webcam** HTTP(S) URLs on an explicitly allowlisted private subnet, or Mac/USB camera indices `0–4`), plus `120`-frame rolling-buffer clip capture. RTSP is disabled pending redirect-safe handling. Zero live bank CCTV connection.
- **Automatic SQLite Evidence & Repeat-Person Alerting (`/api/live-evidence`):** Faces detected on clean raw frames (`>= 0.56` normalized SFace threshold) are automatically cropped, SHA-256 hashed, and stored under sequential IDs (`SUB-001`, `SUB-002`, ...) in `live_identities` + `live_sightings`. If the same person re-appears (`>= 8s` absence or `>= 2s` camera switch), Drishti increments their visit count, saves a fresh crop, and triggers a **`stream.repeat_person`** priority alert with 1-click **Arm** to the local watchlist.
- **Incident evidence (`/api/live-incidents`):** Review hashed scene snapshots from live monitoring, including camera interference (`stream.camera_tamper`), ATM-zone dwell (`stream.atm_zone_dwell`), and guard welfare cues (`stream.guard_welfare_check`). Dwell and welfare cues are local review alerts.
- **Camera interference:** A sustained obscured view, abrupt framing change, strong localized glare, or loss of a previously active feed can trigger an alert. The incident includes a timestamped snapshot and a recent face crop when available. The crop is context for review. It does not identify who caused the interference.

### 6. Case Intel, 1930 / FIR Dossier & Enterprise Compliance (`Case intel`, `Security`)
- **Indian Police / Bank Fraud Dossier (`/api/dossier`):** Capture FIR/GD Ref, NCRP `1930` Acknowledgement ID, Police Station/Unit, Investigating Officer Name & Badge, Bank / White-Label ATM Operator, Terminal ID, Fraud Typology, and Loss Amount (INR ₹) — without storing raw PANs or PINs — stamped automatically onto every exported report and certificate.
- **Multi-Camera Suspect Journey (`/api/cases/journey`):** Correlates SFace cross-camera appearances across `ATM-01..ATM-04` (filtering out same-camera self-links), live repeat visitors, and audit readiness.
- **Enterprise Compliance Matrix (`/api/security/compliance-report.json`):** Exports a signed inventory of evidence export, privacy and local security controls alongside the model inventory. It records whether the optional Ultralytics runtime is installed or enabled.

### 7. Separate Security, Guard Management & Priority Escalation Portal (`/security-portal` · `127.0.0.1:8100`)
Drishti AI integrates over authenticated loopback REST APIs (`POST /sec-api/bridge/event` via `X-Drishti-Service-Key`) with a **separate Security & Escalation Portal** (`security_portal/` + `/security-portal` UI):
- **Context-First Two-Stage Security Rules:**
  - **Rule 1 (`RULE_1_CONCEALMENT` — Observe Silently):** Helmet, mask, cap, or obscured face entry inside the ATM is recorded quietly in `rule_observations` (`RULE 1 MONITORING`) **without triggering any alarm/siren**.
  - **Rule 2 (`RULE_2_ATM_TAMPER_OR_FORCE` — Immediate Escalation):** Only if machine shaking, prying, structural panel tampering, torch/cutter flash, or sustained concealed manipulation occurs does the engine escalate (`Prior Rule 1 + Rule 2 Breach`) into a Priority-1 alert.
- **3-Tier Priority Escalation + Web Audio Siren:**
  `ATM Camera (Drishti) → Priority 1: Assigned On-Duty Guard (Siren + SLA Countdown) → Priority 2: ATM Admin / Owner → Priority 3: Backup Govt Security Official`.
- **Camera-interference delivery:** The assigned guard, ATM administrator, and police liaison can see these alerts in their portal accounts. The portal uses the ATM assignment to route the alert and verifies the snapshot hash before serving it. Production dispatch, SMS, and automatic selection of a police station are outside this local workflow.
- **Guard Management & 4-Role RBAC:** Separate password-based roles for `Guard`, `ATM Admin / Owner`, `Government / Security Official`, and `Super Admin`. Guard profiles hold Name, Employee/Guard ID, Mobile, Address, PIN Code, Assigned ATMs, Duty Timings, Emergency Contact, and an administrator-managed verification status. No SMS OTP or Aadhaar eKYC integration is implemented.

---

## Navigation Tabs (UI Workspace)

| Tab | Role | Purpose |
| :--- | :--- | :--- |
| **Case desk** *(default)* | All | **PS04 Core Workflow:** 4 ATM slots (`ATM-01`–`04` add/change/delete), transaction linking, EJ CSV batch matcher, demo loader, & **Evidence review** |
| **Real-time AI** | All | **Local Sandbox:** Auto-started 4-stream monitor (person, face, occlusion, tampering, shoulder-surfing, repeat visitor & watchlist), live DB tracker & auto-saved incident PDFs |
| **Case intel** | All | 1930 NCRP / FIR & Bank Dossier editor, cross-camera SFace links, live watchlist cards, & readiness timeline |
| **Video library** | All | Multi-format ingestion, FFmpeg normalization, container forensics, DVR guide, & per-clip SHA-256 verification |
| **Face search** | All | SFace 128-D embedding cosine similarity search across all local clips |
| **Reports** | All | Forensic throughput, quality/flag breakdowns, and 4-stream telemetry |
| **Audit** | All | Hash-chained operator actions & system alerts with CSV / signed JSON export (`/api/audit/export`) |
| **Access** | Admin | Local investigator approval, role inspection, and account enable/disable |
| **Security** | Admin | SQLite `WAL`/`quick_check`, full SHA-256 vault sweep, AES-256-GCM DB snapshot backup/download, **Manifest Verifier**, & **Compliance Report JSON** |

---

## Cyber Security & Chain-of-Custody Controls ([`backend/security.py`](backend/security.py), [`backend/auth.py`](backend/auth.py), [`backend/store.py`](backend/store.py))

- **Authentication & RBAC:** First user becomes `administrator`; later sign-ups remain `pending` until approved under **Access**. Passphrases use salted `scrypt` hashes; sessions use 8-hour `HttpOnly; SameSite=Strict` cookies with CSRF token checks on mutations. Failed logins are throttled using SHA-256 hashed identifiers.
- **HTTP & CSP Hardening:** Strict Content Security Policy, `frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Cross-Origin-Resource-Policy: same-origin`, disabled browser sensor APIs (`camera`/`microphone`/`geolocation`), and `Cache-Control: no-store` on API responses.
- **Cryptographic Custody & WAL Persistence:**
  - Dual SHA-256 fingerprints (`original` upload + `normalized` review bytes) + vault-wide integrity sweeps (`/api/security/evidence-check`).
  - Hash-chained SQLite audit log verifiable at `/api/audit/integrity`.
  - Audit entries show recorded subject and account IDs. Candidate reviews record the source timestamp and status transition. Live incident deletions record the camera and capture time. Camera configuration entries omit credentials and describe the configuration action.
  - **HMAC-SHA256 Manifests** signed with local `signing.key` (`0600`) and verifiable at `/api/security/verify-manifest`.
  - SQLite runs with `PRAGMA journal_mode = WAL`, `PRAGMA synchronous = NORMAL`, `PRAGMA secure_delete = ON`, file mode `0600`, inside `0700` `backend/data/` (overridable via `DRISHTI_DATA_DIR`).
- **Encrypted Backups & Restore:** In-memory SQLite online snapshots normalize WAL header bytes (`v1` rollback format) and encrypt with **AES-256-GCM** using an unstored operator passphrase. Restore while the app is stopped (cleans stale `-wal`/`-shm`/`-journal` sidecars safely):
  ```bash
  python3 scripts/restore_database.py /path/to/drishti-db-....enc
  ```

---

## Quick Setup & Run (macOS / Linux)

**Prerequisites:** Python 3.11+, Node.js 18+ (`npm`), and local `ffmpeg` / `ffprobe`.

```bash
./setup.sh
./start.sh
```

- `./setup.sh`: creates `.venv`, installs `requirements.txt` & `npm` dependencies, downloads pinned checksum-verified ONNX models (`scripts/download_models.py`), and prepares 4 local demo feeds (`scripts/prepare_demo_feeds.py`).
- `./start.sh`: runs `scripts/doctor.py` and starts Uvicorn (`127.0.0.1:8000`) + Vite (`127.0.0.1:5174`).
  - **UI:** `http://127.0.0.1:5174`
  - **OpenAPI Docs:** `http://127.0.0.1:8000/api/docs`

Before attaching a network camera, set `DRISHTI_CAMERA_NETWORKS` to the camera subnet (for example, `192.168.1.0/24` in PowerShell or `export DRISHTI_CAMERA_NETWORKS=192.168.1.0/24` in a shell). Camera URLs must use an IP inside that private CIDR; DNS names, public IPs, loopback, and link-local addresses are rejected. Local USB camera indexes do not need this setting.

Uploads are limited to 500 MB each and the local evidence directory defaults to a 20 GiB cap. Set `DRISHTI_MAX_VAULT_BYTES` to a positive byte count to change the cap. Keep adequate free disk space for temporary normalization copies.

**Single-Bundle Local Serving:**
```bash
npm run build
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

The Security Portal does not create demo accounts. For a local demonstration, provision the first portal super admin interactively with `python scripts/provision_portal_admin.py`, then add other personnel from the portal. Do not use synthetic contact details or accounts for operational deployments.

---

## Quick setup on Windows

From PowerShell in the repository folder, with Python, Node.js, FFmpeg, and FFprobe on your command path:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm.cmd ci
.\.venv\Scripts\python.exe scripts/download_models.py
.\.venv\Scripts\python.exe scripts/doctor.py
npm.cmd run build
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

For the blockchain demo, use `npm.cmd run blockchain:demo` to start the app on port `8001` with the local chain.

On the maintainer's Windows workstation, the ignored local helper `start-demo.ps1` starts/reuses the three local services and opens each prototype view plus the Security Portal in a separate browser tab. Run it from the repository folder with `powershell -ExecutionPolicy Bypass -File .\start-demo.ps1`. The helper and its logs are intentionally excluded from Git; on a fresh clone, follow the setup commands above and start the services manually.

## Default OpenCV Zoo models

| Model | Purpose | SHA-256 |
| :--- | :--- | :--- |
| `person_detection_mediapipe_2023mar.onnx` | Local person detection & tracking | `47fd5599d6fa17608f03e0eb0ae230baa6e597d7e8a2c8199fe00abea55a701f` |
| `face_detection_yunet_2023mar.onnx` | Face & 5-point landmark detection | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` |
| `face_recognition_sface_2021dec.onnx` | SFace 128-D cross-clip & live matching embeddings | `0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79` |

See [LICENSES.md](LICENSES.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

---

## Project Layout

```text
CYBER-HACK/
├── backend/
│   ├── main.py          # FastAPI lifespan API, RBAC/CSRF middleware, EJ matcher, PDF/BSA63/Bundle ZIP exports
│   ├── analysis.py      # MediaPipe person tracking, YuNet faces, SFace 128-D embeddings, quality/occlusion flags
│   ├── forensics.py     # ffprobe metadata, FFmpeg DVR normalization, splice cues, CLAHE enhancement, DPDP blur
│   ├── streams.py       # 4-stream local/HTTP camera monitor, DB evidence & repeat alerts, incident snapshots
│   ├── store.py         # SQLite WAL persistence, migrations, audit chain, dossier, watchlist & live evidence
│   ├── security.py      # Path containment, security headers, AES-256-GCM backups, HMAC-SHA256 signing/verify
│   └── auth.py          # scrypt password hashing, session cookies, CSRF tokens, hashed login throttling
├── src/
│   ├── App.tsx          # React SPA (9 workspace tabs, portaled modals, Light sliders, 1930 Dossier, Watchlist)
│   ├── api.ts           # Typed API client & CSRF request helpers
│   └── styles.css       # Rajasthan Police-inspired light command theme & responsive breakpoints
├── scripts/
│   ├── doctor.py            # Dependency & SHA-256 model integrity check
│   ├── download_models.py   # Pinned ONNX model downloader
│   ├── prepare_demo_feeds.py# Generates demo_feeds/ pilot CCTV MP4s
│   ├── run_local.py         # Launches Uvicorn (8000) + Vite (5174) locally
│   ├── smoke_test.py        # End-to-end automated verification across API, RBAC, WAL, SFace, streams & bundles
│   ├── restore_database.py  # Encrypted AES-256-GCM SQLite snapshot restore CLI
│   └── run_ui_test_server.py# Local test server harness
├── demo_feeds/          # 4 compact local pilot feeds (cam_01_vestibule.mp4 .. cam_04_exit.mp4)
├── PS04_demo_data/      # RPH26 PS04 Demo Dataset Builder, format samples, ATM master & consent forms
└── docs/                # Pitch guide, architecture/integration notes, productization & UI test report
```

---

## PS04 Demo Dataset Builder (`PS04_demo_data/`)

To test Drishti against realistic Rajasthan Police Hackathon 2026 (PS04) test cases — multi-codec DVR exports (`MP4`, `AVI MJPEG`, `MKV H.265`, `MOV`, `WMV`, `FLV`, `MPEG-2`, raw `.264`), clock offsets up to `+1h`, Dahua `.dav` (`DHAV`) error handling, and Electronic Journals (`_ej.txt` / bank CSVs):

1. Copy raw ATM-style videos into [`PS04_demo_data/raw_videos/`](PS04_demo_data/raw_videos/PUT_YOUR_VIDEOS_HERE.txt).
2. Generate the clip manifest:
   ```bash
   python3 PS04_demo_data/_tools/build_ps04.py init PS04_demo_data/
   ```
3. Fill in `person_id`, `role`, and second offsets in `PS04_demo_data/clip_manifest.csv` (see [`clip_manifest_TEMPLATE.csv`](PS04_demo_data/00_format_samples/clip_manifest_TEMPLATE.csv) and [`HOW_TO_USE_YOUR_VIDEOS.md`](PS04_demo_data/HOW_TO_USE_YOUR_VIDEOS.md)).
4. Build the formatted clips, transaction logs, cases, and answer key:
   ```bash
   python3 PS04_demo_data/_tools/build_ps04.py build PS04_demo_data/
   ```
5. **Analyze in Drishti:**
   - Upload clips from `PS04_demo_data/02_videos/<ATM_ID>/` (or `format_coverage/`) into **Case desk** / **Video library** — raw `.264` elementary streams are automatically normalized with accurate duration/FPS, and `02_videos/proprietary/UDR0019.export.dav` (`DHAV`) triggers vendor conversion instructions.
   - Paste any generated `03_transactions/<ATM_ID>_ej.txt`, `<ATM_ID>_bank_statement.csv`, or standard CSV directly into **ATM Transaction Journal Matcher (`/api/journal/match`)** — Drishti parses `DD/MM/YYYY HH:MM:SS` EJ blocks, `DD-MM-YYYY` bank CSVs, and ISO timestamps natively.
   - Cross-check extracted suspects via **Face search** (SFace 128-D) and **Sealed PDF / BSA Sec. 63 / Bundle `.zip`** exports against `99_answer_key/answer_key.csv`.

---

## Covered-face evidence handoff

Open a completed analysis and use **Face visibility and case handoff**. New analyses report sampled frames with a detected person and no face detection. Use the source player to review a timestamp, save a visibility observation, and optionally link an incident from the same camera channel. The signed manifest records the transaction offset, observation timestamp, and operator account. **Case bundle with original footage** includes the original bytes after a SHA-256 check and any linked snapshots that still match their recorded fingerprints. Earlier analyses can accept observations. Rerun them to collect visibility sampling counts.

## Optional YOLOv8 and ByteTrack monitoring

The default OpenCV Zoo models remain available. To enable the optional Ultralytics models on Windows, run these commands from the project folder. Review the [Ultralytics license](https://www.ultralytics.com/license) before distributing an integration that uses its software or weights.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-vision.txt
.\.venv\Scripts\python.exe scripts/download_models.py --advanced-vision
$env:DRISHTI_ADVANCED_VISION = '1'
npm.cmd run build
npm.cmd run blockchain:demo
```

YOLOv8n detects people and ByteTrack keeps a separate tracking session for each camera or clip. YuNet and SFace still handle face evidence. On the live wall, ATM-zone dwell generates a review alert after 90 seconds by default. A recorded feed uses clip time for the timer. Dwell and welfare observations stay in the local alert log.

To enable YOLOv8n-Pose welfare cues, set a guard zone for the installed camera and restart. This example shows the configuration format. Adjust each rectangle to the actual camera view. Coordinates are normalized `[left, top, right, bottom]`.

```powershell
$env:DRISHTI_CAMERA_ZONES = '{"CAM-03":{"atm":[0.22,0.16,0.84,0.94],"guard":[0.02,0.15,0.20,0.95],"dwellSeconds":90,"welfareSeconds":30}}'
```

A welfare cue requires one tracked occupant, usable upper-body keypoints, and sustained head-down posture with limited movement. It cannot establish that someone is asleep. VideoMAE and SlowFast are not enabled. A CCTV action model needs annotated positive and ordinary-activity examples, plus separate validation footage. CVAT can label the action intervals and tracks for that work without putting annotation software on the live processing path.

## Blockchain evidence verification

Build the frontend and run `npm run blockchain:demo`. Open `http://127.0.0.1:8001` and sign in as an administrator. The runner starts a persistent, loopback-only Anvil demo chain. Its data lives in `backend/data/demo-blockchain/` by default. It reuses the local case vault and leaves live camera processing paused on startup.

1. Open a completed case and choose **Anchor manifest on blockchain**. Save the downloaded JSON bundle.
2. Open **Security → Evidence verifier**, paste the bundle, and choose **Verify evidence**.
3. Duplicate the bundle, edit a value inside `manifest`, and verify the copy. The original must match the blockchain transaction. The edited copy must fail.

Only a version marker and SHA-256 fingerprint of the signed manifest are written to the chain. The bundle contains evidence metadata and must be handled as local evidence. Verification establishes that the canonical block contains the fingerprint. The separate vault integrity check compares the current footage against its stored fingerprints.

The local demo chain is controlled by the same workstation. For an independent checkpoint, configure an approved Ethereum-compatible network using `DRISHTI_CHAIN_RPC_URL`, `DRISHTI_CHAIN_ID` (hexadecimal), and `DRISHTI_CHAIN_SENDER`. Publishing requires an RPC provider configured to sign `eth_sendTransaction` for that authorized account. Use a separate independently operated RPC endpoint for independent verification. Drishti neither stores blockchain private keys nor deploys a smart contract.

## Verification & Tests

```bash
npx tsc --noEmit
npm run build
python3 -m compileall -q backend scripts
python3 scripts/doctor.py
python3 scripts/smoke_test.py
```

`scripts/smoke_test.py` exercises an isolated temporary workspace across:
- Bootstrap admin signup, investigator approval, login throttling, RBAC, and CSRF enforcement
- Video upload/validation, DVR guidance, SHA-256 integrity sweep, and timestamp/EJ CSV journal matching
- Person/face extraction, SFace 128-D cross-clip search, labelled enhancement, and DPDP bystander redaction
- 4-stream monitoring, live DB evidence capture, repeat-person alert triggering, live incidents, watchlist promotion, and cross-camera journey
- Sealed PDF, BSA Section 63 Certificate PDF, HMAC-SHA256 manifest generation/tamper rejection, Offline Case Bundle `.zip`, 1930/FIR Dossier CRUD, Compliance JSON, WAL-normalized AES-256-GCM backup/restore, and wrong-passphrase rejection

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
