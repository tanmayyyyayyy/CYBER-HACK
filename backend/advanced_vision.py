"""Optional YOLOv8 inference and a separate ByteTrack session per camera."""

import json
import logging
import os
import threading
from importlib.util import find_spec
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import numpy as np


LOG = logging.getLogger(__name__)
MODELS = Path(__file__).resolve().parents[1] / "models"
PERSON_WEIGHTS = MODELS / "yolov8n.pt"
POSE_WEIGHTS = MODELS / "yolov8n-pose.pt"
ROBBERY_WEIGHTS = MODELS / "atm_robbery.pt"
_inference_lock = threading.Lock()
_failed_inference: set[Path] = set()


@lru_cache(maxsize=3)
def _load_model(weights: Path):
    flag = "DRISHTI_ROBBERY_VISION" if weights == ROBBERY_WEIGHTS else "DRISHTI_ADVANCED_VISION"
    if os.environ.get(flag) != "1" or not weights.is_file():
        return None
    try:
        import torch
        from ultralytics import YOLO

        torch.set_num_threads(min(4, os.cpu_count() or 1))
        return YOLO(str(weights))
    except Exception:
        LOG.exception("Could not load optional model %s", weights.name)
        return None


def _predict(weights, frame, **kwargs):
    with _inference_lock:
        if weights in _failed_inference:
            return None
        model = _load_model(weights)
        if model is None:
            return None
        try:
            return model.predict(frame, device="cpu", verbose=False, **kwargs)[0]
        except Exception:
            _failed_inference.add(weights)
            LOG.exception("Optional model %s failed inference", weights.name)
            return None


def person_boxes(frame):
    result = _predict(PERSON_WEIGHTS, frame, classes=[0], conf=.10, imgsz=640)
    if result is None:
        return None
    return [(*map(int, row[:4]), float(row[4])) for row in result.boxes.data.cpu().numpy()]


def robbery_weapon(frame) -> str:
    result = _predict(ROBBERY_WEIGHTS, frame, conf=0.50, imgsz=640)
    if result is None:
        return ""
    labels = [result.names[int(index)].strip().lower() for index in result.boxes.cls.tolist()]
    if {"offender", "victim"}.issubset(labels):
        return next((label for label in labels if label in {"gun", "knife"}), "")
    return ""


def new_tracker():
    if find_spec("lap") is None:
        return None
    try:
        from ultralytics.trackers.byte_tracker import BYTETracker

        return BYTETracker(SimpleNamespace(track_high_thresh=.34, track_low_thresh=.10, new_track_thresh=.40,
                                           track_buffer=12, match_thresh=.80, fuse_score=True))
    except ImportError:
        LOG.exception("ByteTrack could not be loaded")
        return None


def track_people(tracker, detections, frame):
    from ultralytics.engine.results import Boxes

    values = np.array([(*box, 0) for box in detections], dtype=np.float32).reshape(-1, 6)
    results = tracker.update(Boxes(values, frame.shape[:2]), frame)
    return [(int(row[4]), (*map(int, row[:4]), float(row[5]))) for row in results]


def head_down(frame) -> bool:
    result = _predict(POSE_WEIGHTS, frame, conf=.4, imgsz=320) if frame.size else None
    if result is None or result.keypoints is None or len(result.keypoints) != 1:
        return False
    keypoints = result.keypoints.data[0].cpu().numpy()
    if keypoints.shape[1] != 3 or min(keypoints[[0, 5, 6, 11, 12], 2]) < .50:
        return False
    shoulders = keypoints[[5, 6], :2].mean(axis=0)
    hips = keypoints[[11, 12], :2].mean(axis=0)
    torso = float(np.linalg.norm(shoulders - hips))
    return torso > 12 and keypoints[0, 1] >= shoulders[1] - torso * .15


@dataclass(frozen=True)
class CameraZones:
    atm: tuple[float, float, float, float] = (.22, .16, .84, .94)
    guard: tuple[float, float, float, float] | None = None
    dwell_seconds: float = 90
    welfare_seconds: float = 30


@lru_cache(maxsize=8)
def camera_zones(camera_id: str) -> CameraZones:
    def rect(values):
        if len(values) != 4 or not (0 <= values[0] < values[2] <= 1 and 0 <= values[1] < values[3] <= 1) or min(values[2] - values[0], values[3] - values[1]) < .02:
            raise ValueError("Invalid normalized camera zone")
        return tuple(map(float, values))

    default = CameraZones()
    try:
        config = json.loads(os.environ.get("DRISHTI_CAMERA_ZONES", "{}"))[camera_id]
        return CameraZones(rect(config.get("atm", default.atm)), rect(config["guard"]) if "guard" in config else None,
                           min(3600, max(5, float(config.get("dwellSeconds", 90)))),
                           min(3600, max(10, float(config.get("welfareSeconds", 30)))))
    except KeyError:
        return default
    except (ValueError, TypeError, IndexError, AttributeError):
        LOG.warning("Ignoring invalid camera zone configuration for %s", camera_id)
        return default


def pixels(rect, width, height):
    return tuple(round(v * (width if i % 2 == 0 else height)) for i, v in enumerate(rect))


@dataclass
class ZoneDwell:
    times: dict[int, tuple[float, float]] = field(default_factory=dict)
    reported: set[int] = field(default_factory=set)

    def update(self, visible: set[int], inside: set[int], now: float, threshold: float) -> tuple[int, float] | None:
        for track_id, (_, seen) in list(self.times.items()):
            if track_id in visible - inside or now - seen > 2:
                del self.times[track_id]
                self.reported.discard(track_id)
        event = None
        for track_id in sorted(inside):
            start, _ = self.times.get(track_id, (now, now))
            self.times[track_id] = (start, now)
            if event is None and now - start >= threshold and track_id not in self.reported:
                self.reported.add(track_id)
                event = track_id, now - start
        return event
