# Productization plan for a Cyber Security Cell pilot

Drishti's product wedge is **transaction-time-first evidence triage**: narrow hours of CCTV to a bank-supplied time window, surface reviewable face frames with transparent quality signals, preserve local evidence fingerprints, and export a human-reviewed evidence sheet. It does not identify a person from external databases.

## What works today

- Local MP4/AVI/MOV/MKV/WMV/FLV/MPEG/MPG upload, clip metadata, and four named ATM evidence channels.
- Clip-relative and bank-time-to-clip-time linking with configurable analysis windows.
- Local person/face detection, basic track continuity, ranked face crops, review labels and notes.
- Cross-clip *appearance histogram* search with explicit non-identity language.
- Source and normalized-file SHA-256, audit hash-chain verification, timestamped system events, reports, and a PDF evidence sheet.
- Local FastAPI/OpenAPI endpoints and a one-machine React client.
- Local administrator/investigator accounts, pending-account approval, account disable, eight-hour HTTP-only sessions, and CSRF protection for write requests.
- Admin-only Security Center checks SQLite integrity/foreign keys, audit links, private file modes, denied sign-ins, and network boundary; full evidence rehash sweeps are recorded and alert on mismatch.
- AES-256-GCM, passphrase-derived SQLite metadata snapshots with an integrity-checked restore utility; portable backups do not contain the large video/candidate media tree.
- Security Portal accounts are no longer demo-seeded at startup. The first portal super admin must be provisioned locally with `python scripts/provision_portal_admin.py`; subsequent accounts are created by an authenticated super admin.
- The portal no longer exposes simulated SMS/Aadhaar OTP verification. Portal login throttles by hashed account identifier and client address. `DRISHTI_COOKIE_SECURE=1` enables Secure cookies when deployed behind HTTPS; MFA and a real identity-verification provider remain future integrations.
- Network cameras require an explicit private CIDR allowlist in `DRISHTI_CAMERA_NETWORKS`. HTTP redirects are revalidated, system proxy settings are bypassed, and camera status output strips credentials and URL query strings. RTSP is disabled because its redirect behavior cannot be constrained through the current reader. HTTP camera transport is not encrypted; use a protected camera network.

## Before any operational pilot

1. **Identity and authorization:** the local portal supports workspace-level administrator/investigator access only. Integrate the Cell's approved identity provider and enforce case-level roles for intake, review, export, and administration before operational use. Keep the local pilot bound to loopback.
2. **Evidence custody:** record verified operator identity, collection source, collection/transfer timestamps, purpose, device/camera details, and every custody transfer. Export an externally signed audit checkpoint to independently controlled storage. Current SQLite hash chaining detects edits and broken links but is not immutable or a complete chain-of-custody record.
3. **Privacy and retention:** define purpose limitation, case retention/deletion, redaction, access review, legal authority, breach response, and backup encryption with the Cell's legal/security teams before ingesting real footage.
4. **Validation:** obtain authorized, representative ATM clips and transaction journals; define acceptance metrics with investigators; measure detection recall, false candidate rate, frame-quality ranking utility, timestamp tolerance, throughput, and performance across camera/lighting conditions. A synthetic smoke test is a software-path check, not an accuracy benchmark.
5. **Operations:** move from SQLite and an in-process single-worker queue to an approved database and durable job queue for multi-user installations; implement health metrics, storage quotas, retention jobs, recovery-tested backups, signed releases, dependency/model SBOM and vulnerability management. App-level encryption-at-rest, centralized key custody, MFA and remote incident alerting are not implemented in this local pilot; require approved host encryption and identity controls.
6. **Integrations:** implement an approved evidence-management/DVR export adapter. Keep the first connector file-based and auditable; the upstream God's Eye View city streams are not ATM evidence and are not connected.
7. **Licensing:** preserve the included model notices; complete a legal review of all software, model, and training-data licenses before redistribution or commercial use.

## Integration contract

The REST API is documented by FastAPI at `/api/docs`. Local session endpoints are `POST /api/auth/signup`, `POST /api/auth/login`, and `POST /api/auth/logout`; protected write calls require the CSRF token returned by `GET /api/auth/me`. Core evidence interfaces are `POST /api/clips`, `GET /api/clips`, `POST /api/analyses` (returns a job ID), `GET /api/analyses/{id}` (poll job status), `PATCH /api/candidates/{id}/review`, `POST /api/search`, `GET /api/audit/integrity`, and `GET /api/evidence/{id}.pdf`. Keep adapters outside the detection module and send files through the same ingest, hash, validation, and audit path. Use transaction references only when policy permits; do not put card numbers, PINs, or account credentials in case metadata.

## Responsible value story

The measurable value hypothesis is less investigator time spent manually scrubbing clips, with clearer provenance and review records. Validate that claim in a controlled pilot by comparing manual review time and frame-selection outcomes against the current workflow. Avoid quoting savings or accuracy until measured on an approved set. The differentiation is local processing, traceable evidence handling, explicit limitations, and investigator control—not automatic identity claims.

## Research references

- NIST describes chain of custody in terms of who handled evidence, when it was collected/transferred, and why: [NIST CSRC glossary](https://csrc.nist.gov/glossary/term/chain_of_custody).
- OWASP recommends validating upload names/content/size and controlling access to uploaded files: [File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).
- OWASP recommends protecting audit logs from unauthorized modification/deletion and adding tamper detection: [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet).
- OWASP's database guidance recommends regular backups protected by appropriate permissions and ideally encryption: [Database Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Database_Security_Cheat_Sheet.html). Snapshot encryption uses authenticated AES-GCM and a user-held passphrase; there is no centrally managed key recovery.
- OWASP recommends authenticated encryption modes and careful key handling: [Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html), [Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html).
- NIST SP 800-88 Rev. 2 requires strong preconditions for cryptographic erase; Drishti does not claim secure erase of active footage or unencrypted host storage: [NIST media sanitization guidance](https://csrc.nist.gov/pubs/sp/800/88/r2/final).
- FFmpeg supports input protocol allowlists; Drishti limits normalization to `file,pipe`: [FFmpeg protocol documentation](https://ffmpeg.org/ffmpeg-protocols.html).
- Ultralytics states YOLO code/models are under AGPL-3.0 or an Enterprise License: [Ultralytics license guidance](https://www.ultralytics.com/license). Drishti removed that runtime in favor of the pinned OpenCV Zoo detector, but all dependencies still need a release-time license review.
