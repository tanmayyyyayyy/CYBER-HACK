# Drishti — Rajasthan Police Cyber Security Hackathon 2026 (PS04) Pitch & Demo Guide

## 1. Problem Solved (PS04 · ATM CCTV Suspect Face Extraction)
In card-skimming, card-swapping, stolen-card, and mule cash-out cases, cyber cell officers spend hours manually scrubbing low-resolution ATM DVR footage. **Drishti** turns that workflow into a **sub-minute, forensically auditable, air-gapped local workstation pipeline**:

1. **Transaction-Time-First Linking & Batch EJ Journal Matcher**: Accepts either clip-relative `HH:MM:SS` or absolute bank timestamp + clip start time, plus bulk ATM Electronic Journal (CSV) matching to auto-flag disputed/fraud withdrawals.
2. **Multi-Format + Proprietary DVR/NVR Support**: Validates MP4, AVI, MOV, MKV, WMV, FLV, MPEG, MPG, plus unencrypted `.dav`, `.h264`, `.ts`, `.m4v`, `.asf`, `.vob` via protocol-restricted local FFmpeg normalization (`-protocol_whitelist file,pipe`), `ffprobe` container forensics, and frame luminance splice checks.
3. **Person-Only Detection + YuNet + SFace 128-D Deep Embeddings**:
   - Local MediaPipe ONNX person detector + IoU tracking (no AGPL/cloud dependencies, no unnecessary car/border models).
   - YuNet face detection + 5-point landmark alignment + **SFace 128-D deep face embeddings** for genuine cross-clip suspect similarity search.
4. **Quality Scoring, Reliability Flags & Behaviour Cues**:
   - Scores sharpness, illumination, pose, face size, and occlusion-free clarity.
   - Raises explicit reliability flags: `possible mask`, `possible cap / headgear`, `possible helmet`, `partial face`, `low resolution`, `soft focus`, `low light`, `overexposed`, `turned face`.
   - Raises advisory alerts for **shoulder-surfing** (multiple tracks inside ATM keypad zone) and **card-slot/keypad tampering (skimming check)**.
5. **Clearly Labelled Forensic Enhancement & DPDP Privacy Redaction**:
   - Toggle **Original Raw** vs. **Enhanced (2× CLAHE + Bilateral + Unsharp)** — deterministic, non-hallucinating, and visibly watermarked as a review aid.
   - **Bystander Privacy Frame**: Gaussian-blurs innocent bystanders while preserving the target candidate and stamping SHA-256 provenance (DPDP Act 2023 privacy-by-design).
6. **God's Eye 4-Stream Surveillance Wall (Local Pilot)**:
   - Integrates 4 concurrent local CCTV streams (`CAM-01`..`CAM-04`) with live person-only bounding boxes, track IDs, dwell timers, suspicious activity alerts, and 1-click **Send to Case Desk**.
7. **Cyber Security & Courtroom Chain-of-Custody**:
   - Dual SHA-256 fingerprints (original upload + normalized review copy) with on-demand & full-vault sweeps.
   - **Tamper-evident hash-chained SQLite audit log** (`/api/audit/integrity`) + CSV/Signed JSON export.
   - **HMAC-SHA256 Signed Evidence Manifest** (`manifest.json`) + PDF Evidence Sheet + in-app **Manifest Seal Verifier** in Security Center.
   - Salted `scrypt` passphrases, 8-hour `HttpOnly; SameSite=Strict` cookies, CSRF tokens, RBAC (`administrator` / `investigator`), rate-limited login with hashed identifiers, and **AES-256-GCM encrypted database snapshots**.
   - Strictly adheres to PS04 out-of-scope boundaries: no Aadhaar/criminal watchlist matching, no autonomous ID without human verification, no live bank CCTV connection.

## 2. 60-Second Live Hackathon Demo Script
1. Open `http://127.0.0.1:5174` and sign in (first run creates the local Administrator account).
2. Open **Surveillance wall** -> click **Start 4-Stream Live AI** -> point out 4 live feeds with person-only bounding boxes, track IDs, and automatic shoulder-surfing/loitering alert logging -> click **Send to Case Desk** on `CAM-02`.
3. On **Case desk**, click **Load Demo Case** -> show **ATM Transaction Journal (EJ / Bank CSV) Matcher** -> click **Auto-Queue Disputed**.
4. In **Evidence review**, showcase ranked face candidates, **Original Raw vs. Enhanced (2×)** toggle, **Privacy Frame (Bystander Redaction)** modal, reliability flags, **Evidence PDF**, and **Manifest JSON**.
5. Open **Cross-clip search** to demonstrate **SFace 128-D embedding cosine similarity** across clips.
6. Open **Security center** -> run **Evidence integrity sweep**, show **AES-256-GCM Backup**, and paste the downloaded `manifest.json` into **Manifest Verifier** (change 1 character to prove immediate tamper detection).

