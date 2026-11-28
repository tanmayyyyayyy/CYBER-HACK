# Drishti Tool

A guided interface for ATM video investigation. The new default screen follows one task at a time in simple Hinglish. The existing processing backend and specialist tools remain in this branch.

## Run locally

On Windows, use the startup script below. It runs the local backend and both interfaces from this repository. Open `http://127.0.0.1:5175` after it starts. The existing workspace is at `/legacy?tab=desk`, and the separate security portal is at `/security-portal`.

## Guided path

Login → Naya case → Video upload → File check → Transaction → Scan → Person chunein → Best frames → Dusri clips → Evidence sheet.

The supplied logo and color rules are in `assets/`, `public/assets/`, and `BRAND-KIT.md`.

## Existing feature access

The original backend, security portal, and advanced UI remain in the branch. Camera monitoring, case intel, response desk, video library, reports, audit trail, access control, security checks, journal matching, privacy frames, backups, and full evidence bundles are available from **Advanced tools**. The guided path uses the existing login, upload, normalization, analysis, candidate review, face search, and PDF export APIs.

## Current limits

This is a new UI over the existing backend. The backend's active dossier is global, so case number and ATM ID in the guided path are stored in this browser's local draft; the case number is also sent with analysis. The ATM ID is not yet written into a per-case backend record or the generated PDF. The person suggestion is derived from the backend's terminal track and ranked face frames, and still requires officer choice. A “Pakka nahi” observation is recorded, but the existing PDF format does not yet prominently show that choice. The old UI remains available until those backend records and exports are revised. Browser local storage is navigation progress only; the uploaded file and analysis are stored by the local backend.

Do not use this hackathon demonstrator for real investigative footage or treat generated output as legal proof without independent validation.

## One-command Windows startup

From PowerShell in this repository:

```powershell
.\start-tool.ps1 -Setup
```

The first run creates `.venv`, installs Python and website packages, checks/downloads the pinned AI models, then starts the API (`8000`), security portal (`8100`), and guided website (`5175`). It opens the guided site in the browser. Later runs only need:

```powershell
.\start-tool.ps1
```

Optional switches: `-Check` checks dependencies without starting services; `-DownloadModels` rechecks model files; `-PrepareDemo` creates demo feeds; `-NoBrowser` leaves the browser closed. You can combine switches, for example `.\start-tool.ps1 -Setup -PrepareDemo`. Press **Ctrl+C** in the startup terminal to stop all services. Service logs are in `.startup-logs/` and are ignored by Git. If ports 8000, 8100, or 5175 are already occupied, the script stops with a message and leaves the existing process alone.

Python 3.11+, Node.js 18+, npm, and preferably FFmpeg/FFprobe are required. PowerShell may require `Set-ExecutionPolicy -Scope Process Bypass` for the current terminal if script execution is disabled.
