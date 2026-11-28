from __future__ import annotations

import json
import math
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from backend import advanced_vision, store

MODEL_DIR = store.ROOT / "models"
PERSON_MODEL = MODEL_DIR / "person_detection_mediapipe_2023mar.onnx"
FACE_MODEL = MODEL_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_MODEL = MODEL_DIR / "face_recognition_sface_2021dec.onnx"
SAMPLE_EVERY_SECONDS = 0.75
MAX_SAMPLED_FRAMES = 1600
_model_lock = threading.Lock()
_person_infer_lock = threading.Lock()
_sface_infer_lock = threading.Lock()
_person_model = None
_hog_model = None
_sface_model = None


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
        clip_start = clip_start.replace(tzinfo=None)
    elif transaction.tzinfo is not None and clip_start.tzinfo is None:
        transaction = transaction.replace(tzinfo=None)
    offset = int((transaction - clip_start).total_seconds())
    if offset < 0:
        raise ValueError("Transaction time is before the clip start. Check both timestamps.")
    return offset


def model_status() -> dict[str, str]:
    return {
        "person": "OpenCV Zoo MediaPipe person detector (ONNX)" if PERSON_MODEL.is_file() else "OpenCV HOG fallback",
        "face": "YuNet local weights" if FACE_MODEL.is_file() else "not installed",
        "embedding": "SFace 128-D local embeddings (ONNX)" if SFACE_MODEL.is_file() else "Histogram fallback",
    }


def _person_anchors() -> np.ndarray:
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
        net = _person_model
    height, width = frame.shape[:2]
    scale = min(224 / height, 224 / width)
    resized_width, resized_height = int(width * scale), int(height * scale)
    resized = cv2.resize(frame, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR)
    left, top = (224 - resized_width) // 2, (224 - resized_height) // 2
    padded = cv2.copyMakeBorder(
        resized, top, 224 - resized_height - top, left, 224 - resized_width - left, cv2.BORDER_CONSTANT, value=(0, 0, 0)
    )
    normalized = (cv2.cvtColor(padded, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0 - 0.5) * 2.0
    blob = np.transpose(normalized, (2, 0, 1))[None, ...]
    with _person_infer_lock:
        net.setInput(blob)
        outputs = net.forward(net.getUnconnectedOutLayersNames())
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
    return [
        (
            boxes[int(i)][0],
            boxes[int(i)][1],
            boxes[int(i)][0] + boxes[int(i)][2],
            boxes[int(i)][1] + boxes[int(i)][3],
            confidences[int(i)],
        )
        for i in keep
    ]


def detect_person_boxes(frame: np.ndarray) -> list[tuple[int, int, int, int, float]]:
    """Lightweight person-only detection (MediaPipe ONNX with OpenCV HOG fallback)."""
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


def new_face_detector():
    if not FACE_MODEL.is_file():
        raise RuntimeError(
            "YuNet face model is missing. Run `python scripts/download_models.py` while online, "
            "then restart the analysis."
        )
    return cv2.FaceDetectorYN.create(str(FACE_MODEL), "", (320, 320), 0.54, 0.3, 5000)


def _get_sface_recognizer():
    global _sface_model
    if not SFACE_MODEL.is_file():
        return None
    with _model_lock:
        if _sface_model is None:
            _sface_model = cv2.FaceRecognizerSF.create(str(SFACE_MODEL), "")
        return _sface_model


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = max(1, (a[2] - a[0]) * (a[3] - a[1]))
    area_b = max(1, (b[2] - b[0]) * (b[3] - b[1]))
    return inter / (area_a + area_b - inter)


def match_tracks(
    boxes: list[tuple[int, int, int, int, float]],
    previous: dict[int, tuple[int, int, int, int]],
    next_id: int,
) -> tuple[list[tuple[int, tuple[int, int, int, int, float]]], dict[int, tuple[int, int, int, int]], int]:
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


def _extract_embedding(roi: np.ndarray, face_row: np.ndarray, face_crop: np.ndarray) -> tuple[list[float], str]:
    recognizer = _get_sface_recognizer()
    if recognizer is not None:
        try:
            with _sface_infer_lock:
                aligned = recognizer.alignCrop(roi, face_row)
                feature = recognizer.feature(aligned).flatten().astype(np.float32)
            norm = float(np.linalg.norm(feature))
            if norm > 1e-6:
                feature = feature / norm
            return [round(float(v), 6) for v in feature.tolist()], "sface_128d"
        except cv2.error:
            pass
    gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA)
    hist = cv2.calcHist([resized], [0], None, [32], [0, 256]).flatten().astype(np.float32)
    hist /= max(float(np.linalg.norm(hist)), 1e-6)
    return hist.tolist(), "hist_32"


def descriptor_similarity(query_vec: list[float], cand_vec: list[float]) -> float | None:
    """Compute normalized cosine similarity; refuses cross-type dimension mismatches."""
    if not query_vec or not cand_vec or len(query_vec) != len(cand_vec):
        return None
    a = np.asarray(query_vec, dtype=np.float32)
    b = np.asarray(cand_vec, dtype=np.float32)
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < 1e-6 or nb < 1e-6:
        return None
    cosine = float(np.dot(a / na, b / nb))
    if len(query_vec) == 128:
        # Map SFace cosine (-1..1, >=0.363 recommended threshold) into 0..1 review percentage
        return max(0.0, min(1.0, (cosine + 0.1) / 0.85))
    return max(0.0, min(1.0, cosine))


def _occlusion_and_quality(
    roi: np.ndarray,
    face_row: np.ndarray,
    face: np.ndarray,
    confidence: float,
    yaw: float,
) -> tuple[float, dict[str, float], list[str]]:
    gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    height, width = gray.shape[:2]
    face_size = float(min(1.0, math.sqrt(width * height) / 110.0))
    sharp_score = min(1.0, sharpness / 170.0)
    light_score = max(0.0, 1.0 - abs(brightness - 128) / 128.0)
    pose_score = max(0.0, 1.0 - min(1.0, abs(yaw) / 0.42))
    size_score = min(1.0, face_size)

    fx, fy, fw, fh = map(int, face_row[:4])
    roi_h, roi_w = roi.shape[:2]
    flags: list[str] = []

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

    # Partial face / edge clipping check
    if fx <= 2 or fy <= 2 or (fx + fw) >= (roi_w - 2) or (fy + fh) >= (roi_h - 2):
        flags.append("partial face")

    # Inter-ocular distance check
    eye_dist = math.hypot(float(face_row[4]) - float(face_row[6]), float(face_row[5]) - float(face_row[7]))
    if eye_dist < 18.0:
        flags.append("low resolution")

    # Occlusion heuristics (lower-face mask vs upper-face cap/helmet)
    occlusion_penalty = 0.0
    if height >= 28 and width >= 24:
        upper = gray[: height // 2, :]
        lower = gray[height // 2 :, :]
        upper_var = float(cv2.Laplacian(upper, cv2.CV_64F).var())
        lower_var = float(cv2.Laplacian(lower, cv2.CV_64F).var())
        lower_bgr = face[height // 2 :, :]
        lower_hsv = cv2.cvtColor(lower_bgr, cv2.COLOR_BGR2HSV)
        lower_sat = float(lower_hsv[:, :, 1].mean())
        lower_std = float(lower.std())

        # Surgical/cloth masks typically have much lower texture detail or saturated uniform fabric in lower half
        if (upper_var > 25.0 and lower_var < upper_var * 0.38 and lower_std < 28.0) or (
            lower_sat > 70.0 and lower_std < 32.0
        ):
            flags.append("possible mask")
            occlusion_penalty += 0.14

        # Check crown/forehead band above face inside person ROI for cap brim shadow or helmet dome
        crown_y1 = max(0, fy - int(fh * 0.45))
        crown_y2 = max(crown_y1 + 1, fy + int(fh * 0.12))
        crown = roi[crown_y1:crown_y2, max(0, fx) : min(roi_w, fx + fw)]
        if crown.size > 0:
            crown_gray = cv2.cvtColor(crown, cv2.COLOR_BGR2GRAY)
            crown_mean = float(crown_gray.mean())
            crown_std = float(crown_gray.std())
            if crown_mean < max(35.0, brightness * 0.55) and crown_std < 36.0:
                flags.append("possible cap / headgear")
                occlusion_penalty += 0.08
            elif crown_std < 18.0 and (fy - crown_y1) >= int(fh * 0.25) and crown_mean > 150.0:
                flags.append("possible helmet")
                occlusion_penalty += 0.12

    raw_score = 100 * (
        0.32 * sharp_score
        + 0.22 * light_score
        + 0.20 * pose_score
        + 0.14 * size_score
        + 0.12 * confidence
    )
    score = max(0.0, raw_score * (1.0 - occlusion_penalty))

    metrics = {
        "sharpness": round(sharp_score * 100),
        "illumination": round(light_score * 100),
        "faceSize": round(size_score * 100),
        "pose": round(pose_score * 100),
        "confidence": round(confidence * 100),
        "occlusionFree": round(max(0.0, 1.0 - occlusion_penalty * 3.0) * 100),
    }
    return round(score, 1), metrics, flags


def _in_atm_zone(box: tuple[int, int, int, int], width: int, height: int) -> bool:
    """Default ATM keypad / cash-slot interaction zone (central 22%..85% X, 18%..96% Y)."""
    cx = (box[0] + box[2]) / (2.0 * max(width, 1))
    cy = (box[1] + box[3]) / (2.0 * max(height, 1))
    return 0.20 <= cx <= 0.86 and 0.18 <= cy <= 0.96


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
        detector = new_face_detector()
        cap = cv2.VideoCapture(clip["path"])
        if not cap.isOpened():
            raise ValueError("OpenCV could not decode this clip. Try exporting it as MP4/H.264.")
        fps = float(clip["fps"]) or 25.0
        interval = 0.35 if end - start <= 120 else SAMPLE_EVERY_SECONDS
        step = max(1, round(fps * interval))
        frame_index = math.ceil(start * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        sampled = 0
        next_track = 1
        previous: dict[int, tuple[int, int, int, int]] = {}
        candidates: list[dict] = []
        latest_time_by_track: dict[int, float] = {}
        track_first_time: dict[int, float] = {}
        track_terminal_hits: dict[int, int] = {}
        shoulder_surf_frames = 0
        shoulder_surf_times: list[float] = []
        occlusion_alert_sent = False
        embedding_type = "sface_128d" if SFACE_MODEL.is_file() else "hist_32"

        # Baseline keypad/card-slot ROI luminance/edge tracker for tampering/skimming review cue
        baseline_keypad_edges: float | None = None
        tamper_cues = 0
        person_frames = 0
        person_without_face_samples = []
        byte_tracker = None
        tracking_engine = "OpenCV person detector + IoU"

        while sampled < MAX_SAMPLED_FRAMES and frame_index / fps <= end:
            ok, frame = cap.read()
            if not ok:
                break
            seconds = frame_index / fps
            frame_index += step
            sampled += 1
            for _ in range(step - 1):
                if not cap.grab():
                    break

            boxes = advanced_vision.person_boxes(frame)
            if boxes is None:
                if tracking_engine != "OpenCV person detector + IoU":
                    tracking_engine = "OpenCV person detector + IoU"
                    previous.clear()
                    byte_tracker = None
                boxes = detect_person_boxes(frame)
                tracks, previous, next_track = match_tracks(boxes, previous, next_track)
            else:
                if byte_tracker is None:
                    byte_tracker = advanced_vision.new_tracker()
                if byte_tracker is None:
                    tracking_engine = "YOLOv8n + IoU"
                    tracks, previous, next_track = match_tracks([box for box in boxes if box[4] >= .34], previous, next_track)
                else:
                    tracking_engine = "YOLOv8n + ByteTrack"
                    tracks = advanced_vision.track_people(byte_tracker, boxes, frame)
                    previous = {track_id: box[:4] for track_id, box in tracks}
            height, width = frame.shape[:2]

            # Track terminal presence & shoulder-surfing proximity
            terminal_tracks = [
                tid for tid, box in tracks if tid != 0 and _in_atm_zone(box[:4], width, height)
            ]
            for tid in terminal_tracks:
                track_terminal_hits[tid] = track_terminal_hits.get(tid, 0) + 1
                track_first_time.setdefault(tid, seconds)
                latest_time_by_track[tid] = seconds

            if len(terminal_tracks) >= 2:
                shoulder_surf_frames += 1
                if len(shoulder_surf_times) < 5:
                    shoulder_surf_times.append(round(seconds, 1))

            # Card-slot / keypad ROI structural change heuristic when terminal is unoccupied
            if not terminal_tracks:
                kx1, ky1 = int(width * 0.35), int(height * 0.42)
                kx2, ky2 = int(width * 0.72), int(height * 0.78)
                keypad_roi = frame[ky1:ky2, kx1:kx2]
                if keypad_roi.size > 0:
                    edges = float(cv2.Canny(cv2.cvtColor(keypad_roi, cv2.COLOR_BGR2GRAY), 60, 150).mean())
                    if baseline_keypad_edges is None:
                        baseline_keypad_edges = edges
                    elif abs(edges - baseline_keypad_edges) > 12.0:
                        tamper_cues += 1

            if tracks:
                person_frames += 1
            if not tracks:
                tracks = [(0, (0, 0, width, height, 1.0))]
            found = []
            for track_id, (x1, y1, x2, y2, person_conf) in tracks:
                pad = 14 if track_id != 0 else 0
                x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
                x2, y2 = min(width, x2 + pad), min(height, y2 + pad)
                roi = frame[y1:y2, x1:x2]
                if roi.size == 0:
                    continue
                detector.setInputSize((roi.shape[1], roi.shape[0]))
                _, faces = detector.detect(roi)
                if faces is None:
                    continue
                at_terminal = track_id != 0 and _in_atm_zone((x1, y1, x2, y2), width, height)
                for face_row in faces:
                    fx, fy, fw, fh = map(int, face_row[:4])
                    confidence = float(face_row[14])
                    face = roi[max(0, fy) : min(roi.shape[0], fy + fh), max(0, fx) : min(roi.shape[1], fx + fw)]
                    if face.size == 0:
                        continue
                    left_eye_x, right_eye_x = float(face_row[4]), float(face_row[6])
                    nose_x = float(face_row[8])
                    eye_mid = (left_eye_x + right_eye_x) / 2
                    yaw = (nose_x - eye_mid) / max(fw, 1)
                    score, metrics, flags = _occlusion_and_quality(roi, face_row, face, confidence, yaw)
                    if at_terminal:
                        score = min(100.0, round(score + 4.0, 1))
                    descriptor, embedding_type = _extract_embedding(roi, face_row, face)
                    landmarks = face_row[4:14].reshape(5, 2) - (max(0, fx), max(0, fy))
                    metrics["landmarks"] = landmarks.tolist()
                    image_name = f"{uuid.uuid4().hex}.jpg"
                    image_path = store.CANDIDATES / image_name
                    cv2.imwrite(str(image_path), face, [cv2.IMWRITE_JPEG_QUALITY, 93])
                    candidate_id = str(uuid.uuid4())
                    abs_bbox = [x1 + max(0, fx), y1 + max(0, fy), x1 + min(roi.shape[1], fx + fw), y1 + min(roi.shape[0], fy + fh)]
                    found.append(
                        {
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
                            "at_terminal": at_terminal,
                            "bbox": abs_bbox,
                            "image_path": str(image_path),
                            "descriptor": descriptor,
                            "confidence": confidence,
                        }
                    )
                    if track_id != 0:
                        latest_time_by_track[track_id] = seconds
                        track_first_time.setdefault(track_id, seconds)

            if any(track_id != 0 for track_id, _ in tracks) and not found:
                person_without_face_samples.append(round(seconds, 3))

            for candidate in found:
                prior = next(
                    (c for c in candidates if candidate["track_id"] != 0 and c["track_id"] == candidate["track_id"] and candidate["time"] - c["time"] < 1.5),
                    None,
                )
                if prior is None:
                    candidates.append(candidate)
                elif candidate["score"] > prior["score"]:
                    candidates.remove(prior)
                    candidates.append(candidate)

        cap.release()
        candidates.sort(key=lambda item: item["score"], reverse=True)
        candidates = candidates[:40]

        suspicious_alerts: list[dict] = []
        if shoulder_surf_frames >= 2:
            suspicious_alerts.append(
                {
                    "kind": "suspicious.shoulder_surfing",
                    "severity": "warning",
                    "message": f"Multiple persons ({len(latest_time_by_track)} tracks) simultaneously near ATM keypad zone near t={shoulder_surf_times[0]}s (possible shoulder-surfing).",
                }
            )
        if tamper_cues >= 3:
            suspicious_alerts.append(
                {
                    "kind": "suspicious.skimming_check",
                    "severity": "warning",
                    "message": "Card-slot/keypad zone structural anomaly detected across baseline frames — inspect for potential skimming overlay.",
                }
            )
        occluded = [c for c in candidates if any(f in c["flags"] for f in ("possible mask", "possible helmet", "possible cap / headgear"))]
        if occluded and not occlusion_alert_sent:
            occlusion_alert_sent = True
            top_flags = sorted({f for c in occluded for f in c["flags"] if f.startswith("possible ")})
            suspicious_alerts.append(
                {
                    "kind": "suspicious.occlusion_detected",
                    "severity": "warning",
                    "message": f"Face reliability flags raised ({', '.join(top_flags)}) on {len(occluded)} candidate frame(s).",
                }
            )

        primary_track = max(track_terminal_hits.items(), key=lambda kv: kv[1])[0] if track_terminal_hits else None

        result = {
            "transactionTime": analysis["transaction_time"],
            "transactionRef": analysis["transaction_ref"],
            "windowSeconds": analysis["window_seconds"],
            "windowStart": round(start, 3),
            "windowEnd": round(end, 3),
            "sampledFrames": sampled,
            "personFrames": person_frames,
            "personWithoutFaceSamples": person_without_face_samples,
            "trackingEngine": tracking_engine,
            "peopleSeen": len(latest_time_by_track),
            "primaryTerminalTrack": primary_track,
            "candidateCount": len(candidates),
            "embeddingModel": embedding_type,
            "alerts": suspicious_alerts,
            "models": model_status(),
            "reviewNote": "Candidate ranking assists review. It does not identify the person or establish guilt.",
            "candidates": [
                {
                    k: v
                    for k, v in c.items()
                    if k not in ("image_path", "descriptor", "analysis_id", "clip_id", "confidence")
                }
                for c in candidates
            ],
        }
        with store.connect() as db:
            for c in candidates:
                db.execute(
                    """INSERT INTO candidates(id, analysis_id, clip_id, frame_seconds, track_id, score,
                       sharpness, illumination, face_size, pose, confidence, flags_json, image_path, descriptor_json, bbox_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        c["id"],
                        analysis_id,
                        clip["id"],
                        c["time"],
                        c["track_id"],
                        c["score"],
                        c["metrics"]["sharpness"],
                        c["metrics"]["illumination"],
                        c["metrics"]["faceSize"],
                        c["metrics"]["pose"],
                        c["confidence"],
                        json.dumps(c["flags"]),
                        c["image_path"],
                        json.dumps(c["descriptor"]),
                        json.dumps(c["bbox"]),
                    ),
                )
            db.execute(
                "UPDATE analyses SET status='completed', result_json=?, updated_at=? WHERE id=?",
                (json.dumps(result), utc_now(), analysis_id),
            )
            db.execute(
                "INSERT INTO events VALUES(?,?,?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    analysis_id,
                    clip["id"],
                    "analysis.completed",
                    f"{len(candidates)} face candidates reviewed around {analysis['transaction_time']} ({embedding_type})",
                    "info",
                    utc_now(),
                    json.dumps({"peopleSeen": len(latest_time_by_track), "sampledFrames": sampled}),
                ),
            )
            for alert in suspicious_alerts:
                db.execute(
                    "INSERT INTO events VALUES(?,?,?,?,?,?,?,?)",
                    (
                        str(uuid.uuid4()),
                        analysis_id,
                        clip["id"],
                        alert["kind"],
                        alert["message"],
                        alert["severity"],
                        utc_now(),
                        json.dumps({"transactionRef": analysis["transaction_ref"]}),
                    ),
                )
            store.append_audit(
                db,
                "analysis.completed",
                analysis_id,
                f"Processed {sampled} frames from local clip {clip['filename']} ({len(candidates)} candidates, {len(suspicious_alerts)} review alert(s))",
                utc_now(),
            )
    except Exception as exc:
        with store.connect() as db:
            db.execute(
                "UPDATE analyses SET status='failed', error=?, updated_at=? WHERE id=?",
                (str(exc)[:500], utc_now(), analysis_id),
            )
            db.execute(
                "INSERT INTO events VALUES(?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), analysis_id, clip["id"], "analysis.failed", str(exc)[:500], "warning", utc_now(), "{}"),
            )
            store.append_audit(db, "analysis.failed", analysis_id, str(exc)[:300], utc_now())
    finally:
        with store.connect() as db:
            referenced = {Path(row[0]).name for row in db.execute("SELECT image_path FROM candidates")}
        for path in store.CANDIDATES.glob("*.jpg"):
            if path.name not in referenced:
                path.unlink(missing_ok=True)


def fuse_candidate_frames(candidate: dict, reference: np.ndarray) -> tuple[np.ndarray, list[str]]:
    """Blend compatible crops into the selected crop without inventing detail."""
    sources = [candidate["id"]]
    descriptor = np.asarray(store.json_load(candidate.get("descriptor_json"), []))
    if not candidate["track_id"] or descriptor.shape != (128,):
        return reference, sources

    with store.connect() as db:
        result = db.execute("SELECT result_json FROM analyses WHERE id=?", (candidate["analysis_id"],)).fetchone()
        rows = db.execute(
            """SELECT * FROM candidates WHERE analysis_id=? AND track_id=? AND id<>?
               AND ABS(frame_seconds - ?) BETWEEN 0.1 AND 8
               ORDER BY score DESC, frame_seconds, id LIMIT 8""",
            (candidate["analysis_id"], candidate["track_id"], candidate["id"], candidate["frame_seconds"]),
        ).fetchall()
    details = store.json_load(result["result_json"], {}) if result else {}
    landmarks = {
        item["id"]: np.asarray(item["metrics"].get("landmarks", []), dtype=np.float32)
        for item in (details or {}).get("candidates", [])
    }
    target = landmarks.get(candidate["id"])
    if target is None or target.shape != (5, 2):
        return reference, sources

    height, width = reference.shape[:2]
    eye_distance = float(np.linalg.norm(target[0] - target[1]))
    if eye_distance < 10:
        return reference, sources
    total = reference.astype(np.float32)
    weights = np.ones((height, width, 1), dtype=np.float32)
    gray_reference = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY).astype(np.float32)

    for row in rows:
        points = landmarks.get(row["id"])
        other_descriptor = np.asarray(store.json_load(row["descriptor_json"], []))
        if points is None or points.shape != (5, 2) or other_descriptor.shape != (128,):
            continue
        norm = np.linalg.norm(descriptor) * np.linalg.norm(other_descriptor)
        if norm <= 0 or float(descriptor @ other_descriptor / norm) < 0.65:
            continue
        if any(flag in store.json_load(row["flags_json"], []) for flag in ("possible mask", "possible helmet", "partial face")):
            continue
        matrix, _ = cv2.estimateAffinePartial2D(points, target, method=cv2.LMEDS)
        if matrix is None or np.max(np.linalg.norm(cv2.transform(points[None], matrix)[0] - target, axis=1)) > eye_distance * 0.10:
            continue
        image = cv2.imread(row["image_path"])
        if image is None:
            continue
        aligned = cv2.warpAffine(image, matrix, (width, height))
        valid = cv2.warpAffine(np.ones(image.shape[:2], np.float32), matrix, (width, height)) > 0.99
        difference = np.abs(cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY).astype(np.float32) - gray_reference)
        agreement = valid & (difference < 28)
        if np.mean(agreement) < 0.60:
            continue
        weight = (agreement * 0.25).astype(np.float32)[..., None]
        total += aligned * weight
        weights += weight
        sources.append(row["id"])
        if len(sources) == 4:
            break
    return np.rint(total / weights).astype(np.uint8), sources
