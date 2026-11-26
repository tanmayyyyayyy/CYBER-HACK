from __future__ import annotations

import sys
import ssl
import hashlib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
ASSETS = {
    "face_detection_yunet_2023mar.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/refs/heads/3cce3b223f17fcce4d86d01dd4502840bf036019/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        100_000,
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    "person_detection_mediapipe_2023mar.onnx": (
        "https://huggingface.co/opencv/opencv_zoo/resolve/39a1451/models/person_detection_mediapipe/person_detection_mediapipe_2023mar.onnx",
        10_000_000,
        "47fd5599d6fa17608f03e0eb0ae230baa6e597d7e8a2c8199fe00abea55a701f",
    ),
    "face_recognition_sface_2021dec.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        30_000_000,
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
}


def main() -> int:
    MODELS.mkdir(parents=True, exist_ok=True)
    for name, (url, minimum_size, expected_sha256) in ASSETS.items():
        target = MODELS / name
        if target.is_file() and target.stat().st_size >= minimum_size:
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            if digest == expected_sha256:
                print(f"verified  {name} ({target.stat().st_size:,} bytes)")
                continue
            print(f"checksum mismatch for {name}; replacing the local copy", file=sys.stderr)
        print(f"downloading {name} from its upstream project")
        temporary = target.with_suffix(target.suffix + ".part")
        try:
            import certifi
            request = urllib.request.Request(url, headers={"User-Agent": "Drishti-Local-Prototype/0.1"})
            context = ssl.create_default_context(cafile=certifi.where())
            with urllib.request.urlopen(request, timeout=45, context=context) as response, temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            if temporary.stat().st_size < minimum_size:
                raise RuntimeError("download was smaller than the expected model size")
            digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
            if digest != expected_sha256:
                raise RuntimeError(f"SHA-256 mismatch: received {digest}")
            temporary.replace(target)
            print(f"ready  {name} ({target.stat().st_size:,} bytes)")
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            print(f"failed {name}: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
