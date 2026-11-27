# Environment configuration

Copy `.env.example` into the process environment using your deployment's secret manager. Do not commit real tokens, bridge keys, or credentials. An empty or invalid optional integration setting leaves that capability in mock mode; the health response at `/api/health` reports each capability and the overall runtime mode.

## Core settings

| Variable | Purpose | Default / behavior |
| --- | --- | --- |
| `DRISHTI_DATA_DIR` | Directory for SQLite and local evidence data | `backend/data` |
| `DRISHTI_DISABLE_AUTO_STREAMS` | Set to `1` to prevent automatic camera stream startup | Streams start by default |
| `DRISHTI_COOKIE_SECURE` | Set to `1` when served through HTTPS | Secure cookie off |
| `DRISHTI_MAX_VAULT_BYTES` | Maximum local data directory size | 20 GiB |
| `DRISHTI_CAMERA_NETWORKS` | Comma-separated private CIDRs allowed for IP cameras | No network camera allowed until configured |
| `DRISHTI_BRIDGE_KEY` | Shared secret for the security portal event bridge | No configured bridge secret |
| `DRISHTI_SECURITY_PORTAL_URL` | Portal bridge endpoint | `http://127.0.0.1:8100/sec-api/bridge/event` |

## Optional capabilities

| Variable(s) | Purpose | Fallback |
| --- | --- | --- |
| `DRISHTI_AUDIT_CHECKPOINT_URL`, `DRISHTI_AUDIT_CHECKPOINT_TOKEN`, `DRISHTI_AUDIT_CHECKPOINT_SIGNING_KEY` | HTTPS endpoint for signed audit chain-head checkpoint; signing key must be at least 32 characters and provisioned out-of-band to the receiver | Missing, incomplete, or non-HTTPS config stays mock; a remote 2xx is reported as accepted, not as independent audit certification |
| `DRISHTI_DISPATCH_WEBHOOK_URL`, `DRISHTI_DISPATCH_TOKEN` | HTTPS webhook for priority alert events | Missing, incomplete, or non-HTTPS config stays mock; a 2xx means endpoint accepted the event, not that SMS, police, or guards were contacted |
| `DRISHTI_RETENTION_DAYS` | Positive whole number of days before an uploaded clip is eligible for manual deletion | Missing/invalid value disables retention; no automatic deletion occurs |
| `DRISHTI_HOST_ENCRYPTION_CONFIRMED` | Operator assertion that the host volume is encrypted (`1`) | Informational only; does not enable application encryption or verify the device |
| `DRISHTI_CHAIN_RPC_URL`, `DRISHTI_CHAIN_ID`, `DRISHTI_CHAIN_SENDER`, `DRISHTI_CHAIN_DEMO` | Optional Ethereum-compatible anchoring/demo chain | No chain anchoring unless configured; demo mode is not an independent trust boundary |
| `DRISHTI_ADVANCED_VISION`, `DRISHTI_CAMERA_ZONES` | Optional advanced detector and camera-zone JSON | Disabled unless explicitly enabled and configured |

Retention has an administrator-only preview and run API at `/api/security/retention` and `/api/security/retention/run`. The run is destructive and manually triggered. It removes clips and clip-derived analysis, event, and candidate data; it does not apply to live identity or incident records. Take and verify an authorized backup before running it.

## Product readiness

There are no environment variables that turn this prototype into a production-ready system. OIDC/MFA, true case-level authorization, application-managed active evidence encryption, independently verifiable audit custody, tested recovery/retention policy, legal review, model validation, and real dispatch integrations remain incomplete. Until independently implemented and assessed, use only synthetic or explicitly authorized demonstration material. Mock mode is deliberately not a claim that data is encrypted or protected for public deployment.
