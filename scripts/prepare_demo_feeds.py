from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEMO_FEEDS = ROOT / "demo_feeds"

FEED_NAMES = [
    ("cam_01_vestibule.mp4", "ATM VESTIBULE NORTH"),
    ("cam_02_keypad.mp4", "KEYPAD & CARD SLOT"),
    ("cam_03_lobby.mp4", "CASH DISPENSER & QUEUE"),
    ("cam_04_exit.mp4", "EXTERIOR & EXIT CORRIDOR"),
]


def _make_synthetic_feed(target: Path, title: str, seed: int) -> None:
    writer = cv2.VideoWriter(str(target), cv2.VideoWriter_fourcc(*"mp4v"), 10, (640, 360))
    if not writer.isOpened():
        raise RuntimeError(f"Could not create {target}")
    for i in range(80):
        frame = np.full((360, 640, 3), (24, 38, 52), dtype=np.uint8)
        cv2.rectangle(frame, (360, 50), (580, 330), (88, 74, 54), -1)
        cv2.rectangle(frame, (400, 120), (540, 200), (22, 28, 36), -1)
        x = 120 + ((i * 3 + seed * 35) % 260)
        cv2.circle(frame, (x, 110), 22, (195, 208, 220), -1)
        cv2.line(frame, (x, 132), (x, 265), (195, 208, 220), 12)
        cv2.putText(frame, f"PILOT SANDBOX: {title}", (18, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (232, 236, 240), 2)
        writer.write(frame)
    writer.release()


def main() -> int:
    DEMO_FEEDS.mkdir(parents=True, exist_ok=True)
    for idx, (filename, title) in enumerate(FEED_NAMES):
        target = DEMO_FEEDS / filename
        if not target.is_file():
            _make_synthetic_feed(target, title, idx)
            print(f"created synthetic {target.name}")
        else:
            print(f"ready   {target.name} ({target.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

