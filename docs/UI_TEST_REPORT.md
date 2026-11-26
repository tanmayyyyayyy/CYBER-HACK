# UI Test Report

**Date:** 26 November 2026  
**Environment:** Local Vite + FastAPI, disposable SQLite/storage, in-app browser  
**Data:** Synthetic eight-second stick-figure clip only

## Manual browser checks

- Opened the Case Desk and navigated to Reports and Audit.
- Checked the responsive navigation drawer at 390 × 844 and returned to desktop viewport.
- Switched between clip-start and bank-transaction timestamps; the corresponding time fields appeared and disappeared.
- Uploaded a synthetic MP4V clip. The app retained the source and produced a browser-compatible H.264 review copy; the rendered video played in the clip panel.
- Started transaction analysis. The job reached **Ready for review**, sampled 11 frames, and correctly showed the no-candidate state for this stick-figure input.
- Opened the generated evidence PDF from the case workflow.
- Verified the audit page reported the local audit hash chain intact.
- Checked cross-clip search empty state: search remains unavailable until an investigator selects a face candidate.
- Confirmed Reports reflected the completed analysis job.
- Created the initial administrator, signed out and back in, and verified the first-run form does not reappear.
- Submitted a second investigator sign-up, verified pending approval prevents sign-in, approved that account in Access Control, and confirmed the investigator role has no Access Control navigation.
- Checked the sign-in portal at 390 × 844; the form fits the mobile viewport and the authenticated dashboard returns to the sign-in screen after sign-out.
- Opened Security Center and verified live database, foreign-key, audit-chain, account-signal, storage-mode, host-encryption reminder, and loopback cards.
- Created an encrypted SQLite metadata snapshot from Security Center; the passphrase cleared from the form, and the recent snapshot row displayed with its hash and download action.
- The full-file sweep control remained disabled for the empty test vault. Automated API checks exercised mismatch detection and recovery after restoring the synthetic file.

## Limits

The synthetic clip contains no real face/person imagery and does not measure detector recall, face quality, or transaction-person linking accuracy. A representative, authorised hackathon dataset is needed for those evaluations. Candidate review/search routes, evidence rehash, encrypted backup decryption/tamper rejection, and PDF output are also exercised by the automated backend smoke test. The host-volume encryption card is an operator reminder, not an automatic OS encryption detector.
