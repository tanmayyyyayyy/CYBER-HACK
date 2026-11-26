from __future__ import annotations

import importlib
import shutil
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def port_state(port: int) -> str:
    with socket.socket() as probe:
        probe.settimeout(0.2)
        return "in use" if probe.connect_ex(("127.0.0.1", port)) == 0 else "available"


def main() -> int:
    failures = []
    python_ok = sys.version_info >= (3, 11)
    print(f"{'OK' if python_ok else 'FAIL'} Python {sys.version.split()[0]} (3.11+ required)")
    if not python_ok:
        failures.append("Python")
    for module in ("fastapi", "uvicorn", "cv2", "numpy", "reportlab", "cryptography"):
        try:
            imported = importlib.import_module(module)
            version = getattr(imported, "__version__", "available")
            print(f"OK {module} {version}")
        except ImportError:
            print(f"FAIL {module} missing")
            failures.append(module)
    for executable in ("node", "npm", "ffmpeg", "ffprobe"):
        path = shutil.which(executable)
        print(f"{'OK' if path else ('OPTIONAL' if executable in {'ffmpeg', 'ffprobe'} else 'FAIL')} {executable}: {path or 'not found'}")
        if not path and executable not in {"ffmpeg", "ffprobe"}:
            failures.append(executable)
    for name in ("face_detection_yunet_2023mar.onnx", "person_detection_mediapipe_2023mar.onnx", "face_recognition_sface_2021dec.onnx"):
        path = ROOT / "models" / name
        print(f"{'OK' if path.is_file() else 'MISSING'} model {name}")
    for port in (5174, 8000):
        print(f"INFO 127.0.0.1:{port}: {port_state(port)}")
    if failures:
        print("\nSetup is incomplete: " + ", ".join(failures))
        return 1
    print("\nEnvironment checks passed. FFmpeg is optional for clips OpenCV can decode directly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
