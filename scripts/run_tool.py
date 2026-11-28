"""Supervise the guided UI, local API, and security portal on Windows."""

from __future__ import annotations

import argparse
import csv
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from io import StringIO
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


def listening_pids(ports: set[int]) -> dict[int, set[int]]:
    """Return Windows TCP listener PIDs for the requested local ports."""
    result = subprocess.run(
        ["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
        errors="replace", timeout=10, check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    owners: dict[int, set[int]] = {port: set() for port in ports}
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 5 or fields[0] != "TCP" or fields[3] != "LISTENING":
            continue
        try:
            port = int(fields[1].rsplit(":", 1)[1])
            pid = int(fields[4])
        except (ValueError, IndexError):
            continue
        if port in owners:
            owners[port].add(pid)
    return owners


def process_name(pid: int) -> str:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, errors="replace", timeout=10, check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        row = next(csv.reader(StringIO(result.stdout)), [])
        return row[0] if len(row) > 1 and row[1] == str(pid) else "unknown process"
    except (OSError, subprocess.SubprocessError):
        return "unknown process"


def clear_occupied_ports() -> bool:
    occupied = [(name, port) for name, port, _ in SERVICES if port_busy(port)]
    if not occupied:
        return True
    print("\nYe ports pehle se use ho rahe hain:")
    if os.name != "nt":
        print(", ".join(f"{name} ({port})" for name, port in occupied), file=sys.stderr)
        print("Existing service band karke dobara chalayein.", file=sys.stderr)
        return False
    ports = {port for _, port in occupied}
    try:
        owners = listening_pids(ports)
    except (OSError, subprocess.SubprocessError):
        print("Port use karne wale process ka pata nahi chal saka. Manually band karke dobara chalayein.", file=sys.stderr)
        return False
    if any(not owners[port] for port in ports):
        print("Kisi port ka process nahi mila. Manually band karke dobara chalayein.", file=sys.stderr)
        return False
    for name, port in occupied:
        for pid in sorted(owners[port]):
            print(f"  {name} ({port}): {process_name(pid)} (PID {pid})")
    pids = set().union(*owners.values())
    if any(pid <= 4 or pid in {os.getpid(), os.getppid()} for pid in pids):
        print("System ya current process mila; automatic stop allowed nahi hai.", file=sys.stderr)
        return False
    try:
        answer = input("In processes ko stop karke Drishti chalu karein? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if answer not in {"y", "yes", "haan", "ha"}:
        print("Theek hai. Koi existing process stop nahi hua.")
        return False
    # Do not stop a new process that took the port while the user was deciding.
    if listening_pids(ports) != owners:
        print("Port owner badal gaya. Dobara start karein.", file=sys.stderr)
        return False
    for pid in sorted(pids):
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True,
            errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            print(f"PID {pid} stop nahi hua: {result.stderr.strip() or result.stdout.strip()}", file=sys.stderr)
            return False
        print(f"Stopped PID {pid}.")
    for _ in range(20):
        if not any(port_busy(port) for port in ports):
            return True
        time.sleep(0.25)
    print("Ports abhi bhi busy hain. Dobara try karein.", file=sys.stderr)
    return False


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


def python_snapshot(directories: tuple[Path, ...]) -> dict[Path, tuple[int, int]]:
    """Track only source files; uploads, models, and cache changes must not restart servers."""
    snapshot = {}
    for directory in directories:
        for path in directory.rglob("*.py"):
            try:
                stat = path.stat()
                snapshot[path] = (stat.st_mtime_ns, stat.st_size)
            except OSError:
                continue  # An editor may be replacing the file right now.
    return snapshot


def restart_entry(entry: tuple, command: list[str], env: dict[str, str], no_window: int, port: int) -> tuple:
    name, process, log_path, handle = entry
    stop(process)
    handle.close()
    for _ in range(20):
        if not port_busy(port):
            break
        time.sleep(0.25)
    else:
        raise OSError(f"port {port} is still busy after stopping {name}")
    with log_path.open("ab") as marker:
        marker.write(b"\n--- Code changed; restarting service ---\n")
    new_handle = log_path.open("ab")
    try:
        new_process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=new_handle,
                                       stderr=subprocess.STDOUT, creationflags=no_window)
    except OSError:
        new_handle.close()
        raise
    print(f"Restarting {name} (PID {new_process.pid})", flush=True)
    return name, new_process, log_path, new_handle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-watch", action="store_true", help="Run without automatic code reloads.")
    args = parser.parse_args()
    if not clear_occupied_ports():
        return 1

    LOG_DIR.mkdir(exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["DRISHTI_FRONTEND_PORT"] = "5175"
    env["DRISHTI_BACKEND_PORT"] = "8000"
    env["DRISHTI_PORTAL_PORT"] = "8100"
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    api_command = [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"]
    portal_command = [sys.executable, "-m", "uvicorn", "security_portal.app:app", "--host", "127.0.0.1", "--port", "8100"]
    commands = (
        ("API", api_command),
        ("Security portal", portal_command),
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
        if not args.no_watch:
            print("Auto refresh is on: website and Python code changes apply after save.")
        print("Press Ctrl+C to stop all three services.\n")
        if not args.no_browser:
            webbrowser.open("http://127.0.0.1:5175")
        watch_dirs = (ROOT / "backend", ROOT / "security_portal")
        snapshot = python_snapshot(watch_dirs) if not args.no_watch else {}
        pending_change: float | None = None
        reported_stops: set[str] = set()
        while True:
            if not args.no_watch:
                current = python_snapshot(watch_dirs)
                if current != snapshot:
                    snapshot = current
                    pending_change = time.monotonic()
                if pending_change is not None and time.monotonic() - pending_change >= 0.8:
                    pending_change = None
                    print("Python code badla; API aur security portal restart ho rahe hain...", flush=True)
                    for index in (0, 1):
                        try:
                            processes[index] = restart_entry(processes[index], commands[index][1], env, no_window, SERVICES[index][1])
                        except OSError as exc:
                            print(f"{commands[index][0]} restart fail hua: {exc}", file=sys.stderr)
                    reported_stops.clear()
                    snapshot = python_snapshot(watch_dirs)
            for name, process, log_path, _ in processes:
                if process.poll() is not None:
                    if args.no_watch or name == "Website":
                        print(f"{name} stopped (exit {process.returncode}).\n{tail(log_path)}", file=sys.stderr)
                        return 1
                    if name not in reported_stops:
                        print(f"{name} stopped. Python file theek karke save karein; auto-restart hoga.\n{tail(log_path)}", file=sys.stderr)
                        reported_stops.add(name)
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
