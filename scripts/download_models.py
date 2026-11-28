from __future__ import annotations

import sys
import argparse
import ssl
import hashlib
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
ASSETS = {
    "face_detection_yunet_2023mar.onnx": (
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        100_000,
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    "person_detection_mediapipe_2023mar.onnx": (
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/person_detection_mediapipe/person_detection_mediapipe_2023mar.onnx",
        10_000_000,
        "47fd5599d6fa17608f03e0eb0ae230baa6e597d7e8a2c8199fe00abea55a701f",
    ),
    "face_recognition_sface_2021dec.onnx": (
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        30_000_000,
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
}

ADVANCED_ASSETS = {
    "yolov8n.pt": ("https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt", 5_000_000,
                   "f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36"),
    "yolov8n-pose.pt": ("https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n-pose.pt", 5_000_000,
                        "c6fa93dd1ee4a2c18c900a45c1d864a1c6f7aba75d84f91648a30b7fb641d212"),
}

FALLBACK_URLS = {
    "face_recognition_sface_2021dec.onnx":
        "https://huggingface.co/opencv/opencv_zoo/resolve/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Download checksum-pinned local model weights.")
    parser.add_argument("--advanced-vision", action="store_true", help="Also download optional Ultralytics YOLOv8 weights.")
    args = parser.parse_args()
    MODELS.mkdir(parents=True, exist_ok=True)
    assets = ASSETS | ADVANCED_ASSETS if args.advanced_vision else ASSETS
    for name, (url, minimum_size, expected_sha256) in assets.items():
        target = MODELS / name
        if target.is_file() and target.stat().st_size >= minimum_size:
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            if digest == expected_sha256:
                print(f"verified  {name} ({target.stat().st_size:,} bytes)")
                continue
            print(f"checksum mismatch for {name}; replacing the local copy", file=sys.stderr)
        sources = [url]
        if name in FALLBACK_URLS:
            sources.append(FALLBACK_URLS[name])
        for attempt, source in enumerate(sources, start=1):
            print(f"downloading {name} from official source {attempt}/{len(sources)}", flush=True)
            temporary = MODELS / f"{name}.part-{uuid.uuid4().hex}"
            try:
                import certifi
                request = urllib.request.Request(source, headers={"User-Agent": "Drishti-Local-Prototype/0.1"})
                context = ssl.create_default_context(cafile=certifi.where())
                digest = hashlib.sha256()
                size = 0
                with urllib.request.urlopen(request, timeout=45, context=context) as response, temporary.open("wb") as output:
                    while chunk := response.read(1024 * 1024):
                        output.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                if size < minimum_size:
                    raise RuntimeError("download was smaller than the expected model size")
                if digest.hexdigest() != expected_sha256:
                    raise RuntimeError(f"SHA-256 mismatch: received {digest.hexdigest()}")
                temporary.replace(target)
                print(f"ready  {name} ({target.stat().st_size:,} bytes)")
                break
            except Exception as exc:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass  # Another Windows process may briefly hold a downloaded file.
                print(f"source {attempt} failed for {name}: {exc}", file=sys.stderr)
                if attempt == len(sources):
                    return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
