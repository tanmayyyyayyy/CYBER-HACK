"""Supervise the guided UI, local API, and security portal on Windows."""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / ".startup-logs"
SERVICES = (
    ("API", 8000, "http://127.0.0.1:8000/api/health"),
    ("Security portal", 8100, "http://127.0.0.1:8100/sec-api/health"),
    ("Website", 5175, "http://127.0.0.1:5175/"),
)


def port_busy(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            return 200 <= response.status < 500
    except (OSError, urllib.error.URLError):
        return False


def tail(path: Path, lines: int = 14) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return "No log output yet."


def stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return
    process.terminate()
    try:
        process.wait(timeout=7)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    occupied = [f"{name} ({port})" for name, port, _ in SERVICES if port_busy(port)]
    if occupied:
        print("Ports already in use: " + ", ".join(occupied), file=sys.stderr)
        print("Close the old project/server and try again. No existing process was stopped.", file=sys.stderr)
        return 1

    LOG_DIR.mkdir(exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["DRISHTI_FRONTEND_PORT"] = "5175"
    env["DRISHTI_BACKEND_PORT"] = "8000"
    env["DRISHTI_PORTAL_PORT"] = "8100"
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    commands = (
        ("API", [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"]),
        ("Security portal", [sys.executable, "-m", "uvicorn", "security_portal.app:app", "--host", "127.0.0.1", "--port", "8100"]),
        ("Website", ["node", str(ROOT / "node_modules" / "vite" / "bin" / "vite.js"), "--host", "127.0.0.1", "--port", "5175"]),
    )
    processes: list[tuple[str, subprocess.Popen[bytes], Path, object]] = []
    try:
        for name, command in commands:
            log_path = LOG_DIR / (name.lower().replace(" ", "-") + ".log")
            handle = log_path.open("wb")
            try:
                process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT, creationflags=no_window)
            except OSError:
                handle.close()
                raise
            processes.append((name, process, log_path, handle))
            print(f"Starting {name} (PID {process.pid})")

        deadline = time.monotonic() + 45
        waiting = list(SERVICES)
        while waiting and time.monotonic() < deadline:
            for name, process, log_path, _ in processes:
                if process.poll() is not None:
                    print(f"{name} stopped during startup.\n{tail(log_path)}", file=sys.stderr)
                    return 1
            waiting = [item for item in waiting if not ready(item[2])]
            time.sleep(0.4)
        if waiting:
            for name, _, log_path, _ in processes:
                if any(item[0] == name for item in waiting):
                    print(f"{name} did not become ready.\n{tail(log_path)}", file=sys.stderr)
            return 1

        print("\nDrishti Tool: http://127.0.0.1:5175")
        print("Advanced tools: http://127.0.0.1:5175/legacy?tab=desk")
        print("Security portal: http://127.0.0.1:5175/security-portal")
        print(f"Logs: {LOG_DIR}")
        print("Press Ctrl+C to stop all three services.\n")
        if not args.no_browser:
            webbrowser.open("http://127.0.0.1:5175")
        while True:
            for name, process, log_path, _ in processes:
                if process.poll() is not None:
                    print(f"{name} stopped (exit {process.returncode}).\n{tail(log_path)}", file=sys.stderr)
                    return 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping Drishti Tool...")
        return 0
    finally:
        for _, process, _, _ in reversed(processes):
            stop(process)
        for _, _, _, handle in processes:
            handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
