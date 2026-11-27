from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if not (ROOT / "node_modules" / "vite").exists():
        print("Frontend packages are missing. Run `npm install` first.", file=sys.stderr)
        return 1
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=ROOT, env=env,
    )
    security_portal = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "security_portal.app:app", "--host", "127.0.0.1", "--port", "8100"],
        cwd=ROOT, env=env,
    )
    time.sleep(0.8)
    if backend.poll() is not None:
        return int(backend.returncode or 1)
    frontend = subprocess.Popen(["npm", "run", "dev", "--", "--host", "127.0.0.1"], cwd=ROOT, env=env)
    print("Drishti is running at http://127.0.0.1:5174", flush=True)
    print("API docs: http://127.0.0.1:8000/api/docs", flush=True)
    print("Security Portal API: http://127.0.0.1:8100/sec-api/docs", flush=True)
    print("Guard & Admin Portal UI: http://127.0.0.1:5174/security-portal", flush=True)
    try:
        while backend.poll() is None and security_portal.poll() is None and frontend.poll() is None:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for process in (frontend, security_portal, backend):
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
        for process in (frontend, security_portal, backend):
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
    return int(frontend.returncode or security_portal.returncode or backend.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
