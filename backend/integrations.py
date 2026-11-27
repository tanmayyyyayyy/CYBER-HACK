from __future__ import annotations

import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit


def _https_pair(url_name: str, token_name: str) -> tuple[str, str, str]:
    url = os.environ.get(url_name, "").strip()
    token = os.environ.get(token_name, "").strip()
    if not url and not token:
        return "mock", "not_configured", "External service settings are missing; local mock mode is active."
    if not url or not token:
        return "mock", "incomplete_configuration", f"Set both {url_name} and {token_name}; local mock mode is active."
    try:
        parsed = urlsplit(url)
    except ValueError:
        return "mock", "invalid_configuration", f"{url_name} is malformed; local mock mode is active."
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return "mock", "invalid_configuration", f"{url_name} must be an HTTPS URL; local mock mode is active."
    return "configured", "ready", "Configured HTTPS endpoint; remote receipt is checked per request."


def capability_status() -> dict[str, Any]:
    audit_mode, audit_reason, audit_message = _https_pair("DRISHTI_AUDIT_CHECKPOINT_URL", "DRISHTI_AUDIT_CHECKPOINT_TOKEN")
    audit_signing_key = os.environ.get("DRISHTI_AUDIT_CHECKPOINT_SIGNING_KEY", "").strip()
    if audit_mode == "configured" and len(audit_signing_key) < 32:
        audit_mode, audit_reason = "mock", "incomplete_configuration"
        audit_message = "Set DRISHTI_AUDIT_CHECKPOINT_SIGNING_KEY to at least 32 characters; local mock mode is active."
    dispatch_mode, dispatch_reason, dispatch_message = _https_pair("DRISHTI_DISPATCH_WEBHOOK_URL", "DRISHTI_DISPATCH_TOKEN")
    retention_raw = os.environ.get("DRISHTI_RETENTION_DAYS", "").strip()
    try:
        retention_days = int(retention_raw)
        retention_ready = retention_days > 0
    except ValueError:
        retention_days = 0
        retention_ready = False
    encryption_confirmed = os.environ.get("DRISHTI_HOST_ENCRYPTION_CONFIRMED") == "1"
    features = {
        "authentication": {"mode": "local", "status": "available", "message": "Local password accounts are active; OIDC and MFA are not implemented."},
        "federatedIdentity": {"mode": "mock", "status": "not_implemented", "message": "OIDC/SSO and MFA need an approved identity provider integration."},
        "activeStorageEncryption": {
            "mode": "self_reported" if encryption_confirmed else "mock",
            "status": "unverified",
            "message": "The host volume must use BitLocker, FileVault, or LUKS. The environment flag is an operator assertion, not a technical check.",
        },
        "remoteAuditCheckpoint": {"mode": audit_mode, "status": audit_reason, "message": audit_message},
        "externalDispatch": {"mode": dispatch_mode, "status": dispatch_reason, "message": dispatch_message},
        "retention": {
            "mode": "configured" if retention_ready else "mock",
            "status": "ready" if retention_ready else "not_configured",
            "days": retention_days if retention_ready else None,
            "message": "Manual clip-retention runs are available." if retention_ready else "Set a positive DRISHTI_RETENTION_DAYS value; no records are deleted automatically.",
        },
        "legalAndModelValidation": {"mode": "unvalidated", "status": "not_assessed", "message": "Legal admissibility and model accuracy have not been independently validated."},
        "caseIsolation": {"mode": "workspace", "status": "incomplete", "message": "The main evidence workspace still needs case-level access controls."},
    }
    product_ready = all(features[name]["mode"] not in {"mock", "unvalidated", "workspace"} for name in features)
    return {"mode": "product" if product_ready else "mock", "features": features}


def _post_https(url_name: str, token_name: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    mode, state, message = _https_pair(url_name, token_name)
    if mode != "configured":
        return {"mode": "mock", "status": state, "message": message}
    url = os.environ[url_name].strip()
    token = os.environ[token_name].strip()
    request_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        **(headers or {}),
    }
    req = urllib.request.Request(url, data=json.dumps(payload, separators=(",", ":")).encode(), headers=request_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            if not 200 <= response.status < 300:
                return {"mode": "configured", "status": "rejected", "httpStatus": response.status}
            return {"mode": "configured", "status": "accepted", "httpStatus": response.status}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"mode": "configured", "status": "unavailable", "message": type(exc).__name__}


def dispatch_alert(alert: dict[str, Any]) -> dict[str, Any]:
    return _post_https(
        "DRISHTI_DISPATCH_WEBHOOK_URL",
        "DRISHTI_DISPATCH_TOKEN",
        {"schemaVersion": 1, "event": "drishti.alert", **alert},
        {"Idempotency-Key": str(alert["alertId"])},
    )


def send_audit_checkpoint(checkpoint: dict[str, Any]) -> dict[str, Any]:
    status = capability_status()["features"]["remoteAuditCheckpoint"]
    if status["mode"] != "configured":
        return {"mode": "mock", "status": status["status"], "message": status["message"]}
    payload = json.dumps(checkpoint, sort_keys=True, separators=(",", ":")).encode("utf-8")
    envelope = {
        "checkpoint": checkpoint,
        "payloadSha256": hashlib.sha256(payload).hexdigest(),
        "signature": hmac.new(os.environ["DRISHTI_AUDIT_CHECKPOINT_SIGNING_KEY"].strip().encode("utf-8"), payload, hashlib.sha256).hexdigest(),
        "algorithm": "HMAC-SHA256",
    }
    return _post_https("DRISHTI_AUDIT_CHECKPOINT_URL", "DRISHTI_AUDIT_CHECKPOINT_TOKEN", envelope)
