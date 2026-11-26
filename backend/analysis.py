from __future__ import annotations

import json
import math
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from backend import store

MODEL_DIR = store.ROOT / "models"
PERSON_MODEL = MODEL_DIR / "person_detection_mediapipe_2023mar.onnx"
FACE_MODEL = MODEL_DIR / "face_detection_yunet_2023mar.onnx"
SAMPLE_EVERY_SECONDS = 0.75
MAX_SAMPLED_FRAMES = 1600
_model_lock = threading.Lock()
_person_model = None
_hog_model = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _time_seconds(value: str) -> int:
    parts = value.split(":")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError("Transaction time must use HH:MM:SS clip time.")
    hours, minutes, seconds = map(int, parts)
    if hours > 99 or minutes > 59 or seconds > 59:
        raise ValueError("Transaction time is outside the supported range.")
    return hours * 3600 + minutes * 60 + seconds


def transaction_offset(analysis: dict) -> int:
    if analysis["time_mode"] == "clip":
        return _time_seconds(analysis["transaction_time"])
    if not analysis["clip_start_time"]:
        raise ValueError("Enter the CCTV clip start timestamp to link an absolute bank transaction time.")
    transaction = datetime.fromisoformat(analysis["transaction_time"].replace("Z", "+00:00"))
    clip_start = datetime.fromisoformat(analysis["clip_start_time"].replace("Z", "+00:00"))
    if transaction.tzinfo is None and clip_start.tzinfo is not None:
        transaction = transaction.replace(tzinfo=clip_start.tzinfo)
    elif transaction.tzinfo is not None and clip_start.tzinfo is None:
        clip_start = clip_start.replace(tzinfo=transaction.tzinfo)
    offset = int((transaction - clip_start).total_seconds())
    if offset < 0:
        raise ValueError("Transaction time is before the clip start. Check both timestamps.")
    return offset


def model_status() -> dict[str, str]:
    return {
        "person": "OpenCV Zoo MediaPipe person detector (ONNX)" if PERSON_MODEL.is_file() else "OpenCV HOG fallback",
        "face": "YuNet local weights" if FACE_MODEL.is_file() else "not installed",
    }


def _person_anchors() -> np.ndarray:
    # OpenCV Zoo MediaPipe detector anchors: 28x28x2 and 7x7x14.
    anchors = []
    for grid, copies in ((28, 2), (7, 14)):
        for row in range(grid):
            for column in range(grid):
                center_x, center_y = (column + 0.5) / grid, (row + 0.5) / grid
                anchors.extend([[center_x, center_y]] * copies)
    return np.asarray(anchors, dtype=np.float32)


def _mediapipe_person_boxes(frame: np.ndarray) -> list[tuple[int, int, int, int, float]]:
    global _person_model
    with _model_lock:
        if _person_model is None:
            _person_model = cv2.dnn.readNet(str(PERSON_MODEL))
    height, width = frame.shape[:2]
    scale = min(224 / height, 224 / width)
    resized_width, resized_height = int(width * scale), int(height * scale)
    resized = cv2.resize(frame, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR)
    left, top = (224 - resized_width) // 2, (224 - resized_height) // 2
    padded = cv2.copyMakeBorder(resized, top, 224 - resized_height - top,
                                left, 224 - resized_width - left, cv2.BORDER_CONSTANT,
                                value=(0, 0, 0))
    normalized = (cv2.cvtColor(padded, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0 - 0.5) * 2.0
    blob = np.transpose(normalized, (2, 0, 1))[None, ...]
    _person_model.setInput(blob)
    outputs = _person_model.forward(_person_model.getUnconnectedOutLayersNames())
    if len(outputs) < 2:
        raise RuntimeError("Person model returned unexpected outputs.")
    score_output = next((output for output in outputs if output.shape[-1] == 1), None)
    box_output = next((output for output in outputs if output.shape[-1] > 1), None)
    if score_output is None or box_output is None:
        raise RuntimeError("Person model output tensors are missing.")
    deltas = box_output[0]
    logits = np.clip(score_output[0, :, 0].astype(np.float64), -100, 100)
    scores = 1.0 / (1.0 + np.exp(-logits))
    anchors = _person_anchors()
    if len(anchors) != len(scores) or deltas.shape[0] != len(scores):
        raise RuntimeError("Person model output does not match its anchor configuration.")
    box_delta = deltas[:, :4]
    center = box_delta[:, :2] / 224.0
    size = box_delta[:, 2:4] / 224.0
    max_side = float(max(width, height))
    x1y1 = (center - size / 2 + anchors) * max_side
    x2y2 = (center + size / 2 + anchors) * max_side
    offset_x, offset_y = left / scale, top / scale
    xyxy = np.concatenate([x1y1, x2y2], axis=1) - np.array([offset_x, offset_y, offset_x, offset_y])
    boxes, confidences = [], []
    for (x1, y1, x2, y2), confidence in zip(xyxy, scores):
        if confidence < 0.5:
            continue
        x1, y1 = max(0, int(x1)), max(0, int(y1))
        x2, y2 = min(width, int(x2)), min(height, int(y2))
        if x2 > x1 and y2 > y1:
            boxes.append([x1, y1, x2 - x1, y2 - y1])
            confidences.append(float(confidence))
    keep = cv2.dnn.NMSBoxes(boxes, confidences, 0.5, 0.3, top_k=50) if boxes else []
    return [(boxes[int(i)][0], boxes[int(i)][1], boxes[int(i)][0] + boxes[int(i)][2],
             boxes[int(i)][1] + boxes[int(i)][3], confidences[int(i)]) for i in keep]


def _person_boxes(frame: np.ndarray) -> list[tuple[int, int, int, int, float]]:
    if PERSON_MODEL.is_file():
        return _mediapipe_person_boxes(frame)

    global _hog_model
    with _model_lock:
        if _hog_model is None:
            _hog_model = cv2.HOGDescriptor()
            _hog_model.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        hog = _hog_model
    rects, weights = hog.detectMultiScale(frame, winStride=(8, 8), padding=(8, 8), scale=1.08)
    return [(x, y, x + w, y + h, float(weights[i])) for i, (x, y, w, h) in enumerate(rects)]


def _new_face_detector():
    if not FACE_MODEL.is_file():
        raise RuntimeError(
            "YuNet face model is missing. Run `python scripts/download_models.py` while online, "
            "then restart the analysis."
        )
    return cv2.FaceDetectorYN.create(str(FACE_MODEL), "", (320, 320), 0.62, 0.3, 5000)


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = max(1, (a[2] - a[0]) * (a[3] - a[1]))
    area_b = max(1, (b[2] - b[0]) * (b[3] - b[1]))
    return inter / (area_a + area_b - inter)


def _match_tracks(boxes: list[tuple[int, int, int, int, float]], previous: dict[int, tuple[int, int, int, int]], next_id: int) -> tuple[list[tuple[int, tuple[int, int, int, int, float]]], dict[int, tuple[int, int, int, int]], int]:
    result = []
    updated = {}
    used: set[int] = set()
    for box in boxes:
        rect = box[:4]
        best_id, best_score = None, 0.0
        for track_id, old in previous.items():
            if track_id in used:
                continue
            score = _iou(rect, old)
            if score > best_score:
                best_id, best_score = track_id, score
        if best_id is None or best_score < 0.15:
            best_id, next_id = next_id, next_id + 1
        used.add(best_id)
        updated[best_id] = rect
        result.append((best_id, box))
    return result, updated, next_id


def _quality(face: np.ndarray, confidence: float, yaw: float) -> tuple[float, dict[str, float], list[str], list[float]]:
    gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    height, width = gray.shape[:2]
    face_size = float(min(1.0, math.sqrt(width * height) / 110.0))
    sharp_score = min(1.0, sharpness / 170.0)
    light_score = max(0.0, 1.0 - abs(brightness - 128) / 128.0)
    pose_score = max(0.0, 1.0 - min(1.0, abs(yaw) / 0.42))
    size_score = min(1.0, face_size)
    score = 100 * (0.34 * sharp_score + 0.24 * light_score + 0.20 * pose_score + 0.14 * size_score + 0.08 * confidence)
    flags = []
    if sharpness < 45:
        flags.append("soft focus")
    if brightness < 50:
        flags.append("low light")
    elif brightness > 215:
        flags.append("overexposed")
    if abs(yaw) > 0.23:
        flags.append("turned face")
    if min(width, height) < 40:
        flags.append("small face")
    if confidence < 0.75:
        flags.append("low face confidence")
    metrics = {
        "sharpness": round(sharp_score * 100),
        "illumination": round(light_score * 100),
        "faceSize": round(size_score * 100),
        "pose": round(pose_score * 100),
        "confidence": round(confidence * 100),
    }
    resized = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA)
    hist = cv2.calcHist([resized], [0], None, [32], [0, 256]).flatten().astype(np.float32)
    hist /= max(float(np.linalg.norm(hist)), 1e-6)
    return round(score, 1), metrics, flags, hist.tolist()


def run_analysis(analysis_id: str) -> None:
    with store.connect() as db:
        analysis = store.row_dict(db.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone())
        clip = store.row_dict(db.execute("SELECT * FROM clips WHERE id = ?", (analysis["clip_id"],)).fetchone()) if analysis else None
    if not analysis or not clip:
        return

    try:
        transaction = transaction_offset(analysis)
        start = max(0.0, transaction - analysis["window_seconds"])
        end = min(float(clip["duration"]), transaction + analysis["window_seconds"])
        if start >= end:
            raise ValueError("Transaction window does not overlap this clip. Check the clip-relative time.")
        detector = _new_face_detector()
        cap = cv2.VideoCapture(clip["path"])
        if not cap.isOpened():
            raise ValueError("OpenCV could not decode this clip. Try exporting it as MP4/H.264.")
        fps = float(clip["fps"]) or 25.0
        step = max(1, int(fps * SAMPLE_EVERY_SECONDS))
        cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
        frame_index = int(start * fps)
        sampled = 0
        next_track = 1
        previous: dict[int, tuple[int, int, int, int]] = {}
        candidates: list[dict] = []
        latest_time_by_track: dict[int, float] = {}

        while sampled < MAX_SAMPLED_FRAMES:
            ok, frame = cap.read()
            if not ok:
                break
            seconds = frame_index / fps
            if seconds > end:
                break
            frame_index += step
            sampled += 1
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            boxes = _person_boxes(frame)
            tracks, previous, next_track = _match_tracks(boxes, previous, next_track)
            height, width = frame.shape[:2]
            if not tracks:
                # Face fallback keeps low-contrast/small person boxes from hiding usable face frames.
                tracks = [(0, (0, 0, width, height, 1.0))]
            detector.setInputSize((width, height))
            found = []
            for track_id, (x1, y1, x2, y2, person_conf) in tracks:
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(width, x2), min(height, y2)
                roi = frame[y1:y2, x1:x2]
                if roi.size == 0:
                    continue
                detector.setInputSize((roi.shape[1], roi.shape[0]))
                _, faces = detector.detect(roi)
                if faces is None:
                    continue
                for face_row in faces:
                    fx, fy, fw, fh = map(int, face_row[:4])
                    confidence = float(face_row[14])
                    face = roi[max(0, fy):min(roi.shape[0], fy + fh), max(0, fx):min(roi.shape[1], fx + fw)]
                    if face.size == 0:
                        continue
                    left_eye_x, right_eye_x = float(face_row[4]), float(face_row[6])
                    nose_x = float(face_row[8])
                    eye_mid = (left_eye_x + right_eye_x) / 2
                    yaw = (nose_x - eye_mid) / max(fw, 1)
                    score, metrics, flags, descriptor = _quality(face, confidence, yaw)
                    image_name = f"{uuid.uuid4().hex}.jpg"
                    image_path = store.CANDIDATES / image_name
                    cv2.imwrite(str(image_path), face, [cv2.IMWRITE_JPEG_QUALITY, 93])
                    candidate_id = str(uuid.uuid4())
                    found.append({
                        "id": candidate_id,
                        "analysis_id": analysis_id,
                        "clip_id": clip["id"],
                        "clip_name": clip["filename"],
                        "time": round(seconds, 3),
                        "time_label": f"{int(seconds // 3600):02}:{int(seconds % 3600 // 60):02}:{int(seconds % 60):02}",
                        "track_id": track_id,
                        "score": score,
                        "metrics": metrics,
                        "flags": flags,
                        "image_path": str(image_path),
                        "descriptor": descriptor,
                        "confidence": confidence,
                    })
                    if track_id != 0:
                        latest_time_by_track[track_id] = seconds

            # Keep at most one candidate per person per 1.5 seconds, preferring a sharper view.
            for candidate in found:
                prior = next((c for c in candidates if c["track_id"] == candidate["track_id"] and candidate["time"] - c["time"] < 1.5), None)
                if prior is None:
                    candidates.append(candidate)
                elif candidate["score"] > prior["score"]:
                    candidates.remove(prior)
                    candidates.append(candidate)

        cap.release()
        candidates.sort(key=lambda item: item["score"], reverse=True)
        candidates = candidates[:40]
        result = {
            "transactionTime": analysis["transaction_time"],
            "transactionRef": analysis["transaction_ref"],
            "windowSeconds": analysis["window_seconds"],
            "windowStart": round(start, 3),
            "windowEnd": round(end, 3),
            "sampledFrames": sampled,
            "peopleSeen": len(latest_time_by_track),
            "candidateCount": len(candidates),
            "models": model_status(),
            "reviewNote": "Candidate ranking assists review. It does not identify the person or establish guilt.",
            "candidates": [{k: v for k, v in c.items() if k not in ("image_path", "descriptor", "analysis_id", "clip_id", "confidence")} for c in candidates],
        }
        with store.connect() as db:
            for c in candidates:
                db.execute(
                    """INSERT INTO candidates(id, analysis_id, clip_id, frame_seconds, track_id, score,
                       sharpness, illumination, face_size, pose, confidence, flags_json, image_path, descriptor_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (c["id"], analysis_id, clip["id"], c["time"], c["track_id"], c["score"],
                     c["metrics"]["sharpness"], c["metrics"]["illumination"], c["metrics"]["faceSize"],
                     c["metrics"]["pose"], c["confidence"], json.dumps(c["flags"]), c["image_path"],
                     json.dumps(c["descriptor"])),
                )
            db.execute("UPDATE analyses SET status='completed', result_json=?, updated_at=? WHERE id=?",
                       (json.dumps(result), utc_now(), analysis_id))
            db.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?,?)",
                       (str(uuid.uuid4()), analysis_id, clip["id"], "analysis.completed",
                        f"{len(candidates)} face candidates reviewed around {analysis['transaction_time']}",
                        "info", utc_now(), json.dumps({"peopleSeen": len(latest_time_by_track), "sampledFrames": sampled})))
            store.append_audit(db, "analysis.completed", analysis_id,
                               f"Processed {sampled} frames from local clip {clip['filename']}", utc_now())
    except Exception as exc:
        with store.connect() as db:
            db.execute("UPDATE analyses SET status='failed', error=?, updated_at=? WHERE id=?",
                       (str(exc)[:500], utc_now(), analysis_id))
            db.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?,?)",
                       (str(uuid.uuid4()), analysis_id, clip["id"], "analysis.failed", str(exc)[:500],
                        "warning", utc_now(), "{}"))
            store.append_audit(db, "analysis.failed", analysis_id, str(exc)[:300], utc_now())
    finally:
        # Remove orphaned crops created before an analysis failure or result cap.
        with store.connect() as db:
            referenced = {Path(row[0]).name for row in db.execute("SELECT image_path FROM candidates")}
        for path in store.CANDIDATES.glob("*.jpg"):
            if path.name not in referenced:
                path.unlink(missing_ok=True)
