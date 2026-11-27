from __future__ import annotations

import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from security_portal import router as portal_router
from security_portal import store

_STOP = threading.Event()
_WORKER: threading.Thread | None = None


def _escalation_loop() -> None:
    while not _STOP.wait(2.0):
        try:
            portal_router.process_escalations()
        except Exception:
            pass


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _WORKER
    store.init_db()
    with store.connect() as db:
        db.execute("""UPDATE atm_assignments SET
            guard_user_id = CASE WHEN guard_user_id IN ('guard-101','guard-102') THEN '' ELSE guard_user_id END,
            admin_user_id = CASE WHEN admin_user_id = 'atm-admin-201' THEN '' ELSE admin_user_id END,
            govt_user_id = CASE WHEN govt_user_id IN ('govt-301','govt-302') THEN '' ELSE govt_user_id END,
            backup_govt_user_id = CASE WHEN backup_govt_user_id = 'govt-302' THEN '' ELSE backup_govt_user_id END""")
        db.execute("""DELETE FROM portal_users WHERE employee_id IN
            ('EMP-GRD-101','EMP-GRD-102','EMP-ADM-201','EMP-GOV-301','EMP-GOV-302','EMP-SUP-001')""")
    _STOP.clear()
    _WORKER = threading.Thread(target=_escalation_loop, name="security-portal-sla", daemon=True)
    _WORKER.start()
    try:
        yield
    finally:
        _STOP.set()
        if _WORKER is not None:
            _WORKER.join(timeout=2.0)


app = FastAPI(
    title="Drishti Security & Escalation Portal",
    version="1.0.0",
    docs_url="/sec-api/docs",
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5174", "http://localhost:5174", "http://127.0.0.1:8000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-Portal-CSRF", "X-Drishti-Service-Key"],
)

app.include_router(portal_router.router)

