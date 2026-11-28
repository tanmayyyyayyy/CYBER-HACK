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

Keep this terminal open while working. Website changes refresh in the browser after saving. Changes to Python files in `backend/` or `security_portal/` restart their local services automatically; the page may briefly reconnect. Saving Python code during an active scan interrupts that scan, so start it again after the reload. `-NoWatch` turns automatic Python reloads off when you need an uninterrupted run. Changes to installed packages, models, or the startup scripts still need setup or a new launch.

If you only need to prepare the Python environment, run `.\setup-venv.ps1`. It checks installed Python through `uv`, the Windows Python launcher, and commands on `PATH`, creates `.venv`, and installs the packages from `requirements.txt`. It accepts Python 3.11 or newer, including 3.14. To choose a specific installed version, use `.\setup-venv.ps1 -PythonVersion 3.14`. To rebuild an existing environment, add `-Recreate`. The startup script calls this setup automatically with `-Setup`.

Optional switches: `-Check` checks dependencies without starting services; `-DownloadModels` rechecks model files; `-PrepareDemo` creates demo feeds; `-NoBrowser` leaves the browser closed; `-NoWatch` disables automatic Python reloads. You can combine switches, for example `.\start-tool.ps1 -Setup -PrepareDemo`. Press **Ctrl+C** in the startup terminal to stop all services. Service logs are in `.startup-logs/` and are ignored by Git. If ports 8000, 8100, or 5175 are occupied on Windows, startup shows the process names and asks `In processes ko stop karke Drishti chalu karein? [y/N]`. Enter `y` to stop those processes and continue, or `n`/Enter to leave them running and exit. Read the listed process names before choosing `y`, since another application may own a port.

Python 3.11+, Node.js 18+, npm, and preferably FFmpeg/FFprobe are required. PowerShell may require `Set-ExecutionPolicy -Scope Process Bypass` for the current terminal if script execution is disabled.
