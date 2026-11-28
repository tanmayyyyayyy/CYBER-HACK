# Drishti Tool

A guided interface for ATM video investigation. The new default screen follows one task at a time in simple Hinglish. The existing processing backend and specialist tools remain in this branch.

## Run locally

Start the backend using the existing `start.sh` or backend setup instructions in the original project. It must serve `http://127.0.0.1:8000`. Then run:

```powershell
npm install
npm run dev
```

Open `http://127.0.0.1:5175`. The guided UI proxies `/api` to the local backend. The existing workspace is at `/legacy?tab=desk`, and the separate security portal is at `/security-portal`. Those routes preserve advanced controls while they are migrated into simpler screens.

## Guided path

Login → Naya case → Video upload → File check → Transaction → Scan → Person chunein → Best frames → Dusri clips → Evidence sheet.

The supplied logo and color rules are in `assets/`, `public/assets/`, and `BRAND-KIT.md`.

## Existing feature access

The original backend, security portal, and advanced UI remain in the branch. Camera monitoring, case intel, response desk, video library, reports, audit trail, access control, security checks, journal matching, privacy frames, backups, and full evidence bundles are available from **Advanced tools**. The guided path uses the existing login, upload, normalization, analysis, candidate review, face search, and PDF export APIs.

## Current limits

This is a new UI over the existing backend. The backend's active dossier is global, so case number and ATM ID in the guided path are stored in this browser's local draft; the case number is also sent with analysis. The ATM ID is not yet written into a per-case backend record or the generated PDF. The person suggestion is derived from the backend's terminal track and ranked face frames, and still requires officer choice. A “Pakka nahi” observation is recorded, but the existing PDF format does not yet prominently show that choice. The old UI remains available until those backend records and exports are revised. Browser local storage is navigation progress only; the uploaded file and analysis are stored by the local backend.

Do not use this hackathon demonstrator for real investigative footage or treat generated output as legal proof without independent validation.
