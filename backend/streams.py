from __future__ import annotations

import collections
import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

import cv2
import numpy as np

from backend import analysis, store


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Only CAM-01 and CAM-02 carry default demo feeds so CAM-03 and CAM-04 remain open
# for the investigator / presenter to attach their own IP Webcams or local clips.
STREAM_CATALOG: list[dict[str, str]] = [
    {
        "id": "CAM-01",
        "channelId": "ATM-01",
        "name": "ATM Vestibule North",
        "zone": "Entry & Lobby",
        "feedFile": "cam_01_vestibule.mp4",
        "sourceAdapter": "gods-eye-local-adapter",
    },
    {
        "id": "CAM-02",
        "channelId": "ATM-02",
        "name": "Keypad & Card Slot",
        "zone": "Terminal Zone",
        "feedFile": "cam_02_keypad.mp4",
        "sourceAdapter": "gods-eye-local-adapter",
    },
    {
        "id": "CAM-03",
        "channelId": "ATM-03",
        "name": "Cash Dispenser & Queue",
        "zone": "Dispenser Zone",
        "feedFile": "",
        "sourceAdapter": "gods-eye-local-adapter",
    },
    {
        "id": "CAM-04",
        "channelId": "ATM-04",
        "name": "Exterior & Exit Corridor",
        "zone": "Exit Perimeter",
        "feedFile": "",
        "sourceAdapter": "gods-eye-local-adapter",
    },
]

_ALLOWED_STREAM_URL = re.compile(r"^(https?|rtsp)://[^\s]+$", re.IGNORECASE)


@dataclass
class StreamState:
    meta: dict[str, str]
    status: str = "standby"
    person_count: int = 0
    face_count: int = 0
    fps: float = 0.0
    frames_processed: int = 0
    active_tracks: int = 0
    alert_state: str = "clear"
    last_alert: str = ""
    last_frame_at: str = ""
    latest_jpeg: bytes = b""
    latest_face_jpeg: bytes = b""
    latest_face_score: float = 0.0
    latest_face_flags: list[str] = field(default_factory=list)
    latest_face_at: str = ""
    watchlist_hit: str = ""
    custom_source: str = ""
    cleared: bool = False
    source_path: str = ""
    source_label: str = "Slot available"
    previous_boxes: dict[int, tuple[int, int, int, int]] = field(default_factory=dict)
    next_track_id: int = 1
    track_start_ts: dict[int, float] = field(default_factory=dict)
    last_alert_ts: float = 0.0
    last_log_ts: float = 0.0
    ring_buffer: collections.deque[np.ndarray] = field(default_factory=lambda: collections.deque(maxlen=120))


class LocalSurveillanceManager:
    """
    4-stream surveillance manager inspired by God's Eye View's source/health
    registry and SIH MultiCameraManager — runs MediaPipe person detection,
    YuNet face + occlusion analysis, and SFace 128-D live watchlist matching
    on raw unannotated frames before rendering clean HUD overlays.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._face_detector = None
        self._streams: dict[str, StreamState] = {
            item["id"]: StreamState(meta=dict(item)) for item in STREAM_CATALOG
        }

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def _get_face_detector(self):
        if self._face_detector is None:
            try:
                self._face_detector = analysis.new_face_detector()
            except RuntimeError:
                return None
        return self._face_detector

    def set_custom_source(self, stream_id: str, source: str) -> dict[str, Any]:
        state = self._streams.get(stream_id)
        if not state:
            raise KeyError(stream_id)
        cleaned = source.strip()
        if cleaned.lower() == "clear":
            with self._lock:
                state.custom_source = ""
                state.cleared = True
                state.ring_buffer.clear()
                state.latest_jpeg = b""
                state.latest_face_jpeg = b""
                state.person_count = 0
                state.face_count = 0
                state.alert_state = "clear"
                state.last_alert = ""
                state.watchlist_hit = ""
                state.previous_boxes.clear()
                state.track_start_ts.clear()
            return self.status()

        if not cleaned or cleaned.lower() == "default":
            with self._lock:
                state.custom_source = ""
                state.cleared = False
                state.ring_buffer.clear()
                state.latest_jpeg = b""
                state.latest_face_jpeg = b""
                state.last_alert = ""
                state.watchlist_hit = ""
            return self.status()

        is_index = cleaned.isdigit() and 0 <= int(cleaned) <= 4
        if not is_index and not _ALLOWED_STREAM_URL.match(cleaned):
            raise ValueError("Enter a valid IP Webcam URL (http://... or rtsp://...), local camera index (0-4), 'default', or 'clear'.")
        with self._lock:
            state.custom_source = cleaned
            state.cleared = False
            state.ring_buffer.clear()
            state.latest_jpeg = b""
            state.latest_face_jpeg = b""
            state.last_alert = ""
            state.watchlist_hit = ""
            state.previous_boxes.clear()
            state.track_start_ts.clear()
        return self.status()

    def _resolve_source(self, state: StreamState) -> tuple[str | int | None, str, bool]:
        if state.custom_source:
            if state.custom_source.isdigit():
                return int(state.custom_source), f"Live Camera #{state.custom_source}", True
            return state.custom_source, f"IP Webcam ({state.custom_source[:36]})", True

        if state.cleared:
            return None, "Slot empty (add footage or IP Webcam)", False

        channel_id = state.meta["channelId"]
        try:
            with store.connect() as db:
                row = db.execute(
                    "SELECT path, filename FROM clips WHERE camera_id=? ORDER BY uploaded_at DESC LIMIT 1",
                    (channel_id,),
                ).fetchone()
                if row and Path(row["path"]).is_file():
                    return str(row["path"]), f"Uploaded ({row['filename'][:26]})", False
        except Exception:
            pass

        feed_file = state.meta.get("feedFile", "")
        if feed_file:
            demo_path = store.DEMO_FEEDS / feed_file
            if demo_path.is_file():
                return str(demo_path), "God's Eye local pilot feed", False
        return None, "Slot empty (add footage or IP Webcam)", False

    def _load_watchlist(self) -> list[dict[str, Any]]:
        try:
            with store.connect() as db:
                rows = db.execute("SELECT id, label, case_ref, embedding_json FROM case_watchlist").fetchall()
            out = []
            for r in rows:
                vec = store.json_load(r["embedding_json"], [])
                if vec:
                    out.append({"id": r["id"], "label": r["label"], "caseRef": r["case_ref"], "vec": vec})
            return out
        except Exception:
            return []

    def _annotate_frame(self, state: StreamState, frame: np.ndarray, detect: bool = True) -> np.ndarray:
        raw = cv2.resize(frame, (640, 360), interpolation=cv2.INTER_AREA)
        state.ring_buffer.append(raw.copy())
        canvas = raw.copy()
        h, w = raw.shape[:2]
        frame_area = float(w * h)
        now_mono = time.monotonic()

        zx1, zy1, zx2, zy2 = int(w * 0.22), int(h * 0.16), int(w * 0.84), int(h * 0.94)

        alert_msg = ""
        alert_kind = ""
        tracks: list[tuple[int, tuple[int, int, int, int, float]]] = []
        face_boxes_to_draw: list[tuple[int, int, int, int, str, tuple[int, int, int]]] = []
        face_hits = 0
        watchlist_match_label = ""

        if detect:
            # 1) Run person detector on CLEAN raw frame (never on overlay graphics!)
            raw_boxes = analysis.detect_person_boxes(raw)
            filtered_boxes = []
            for x1, y1, x2, y2, conf in raw_boxes:
                bw, bh = max(0, x2 - x1), max(0, y2 - y1)
                if conf >= 0.60 and (bw * bh) >= frame_area * 0.022 and bh >= 48 and bw >= 24:
                    filtered_boxes.append((x1, y1, x2, y2, conf))

            tracks, state.previous_boxes, state.next_track_id = analysis.match_tracks(
                filtered_boxes, state.previous_boxes, state.next_track_id
            )
            active_ids = {tid for tid, _ in tracks}
            for old_id in list(state.track_start_ts):
                if old_id not in active_ids:
                    state.track_start_ts.pop(old_id, None)
            for tid in active_ids:
                state.track_start_ts.setdefault(tid, now_mono)

            max_dwell = max((now_mono - ts for ts in state.track_start_ts.values()), default=0.0)
            in_zone = [
                tid
                for tid, box in tracks
                if zx1 <= (box[0] + box[2]) / 2 <= zx2 and zy1 <= (box[1] + box[3]) / 2 <= zy2
            ]

            if len(in_zone) >= 2:
                alert_kind = "stream.shoulder_surfing"
                alert_msg = f"Shoulder-surfing risk on {state.meta['id']}: {len(in_zone)} persons in ATM zone"
            elif max_dwell >= 10.0 and tracks:
                alert_kind = "stream.loitering"
                alert_msg = f"Extended dwell ({max_dwell:.0f}s) detected on {state.meta['id']}"

            # 2) Run YuNet face detection on CLEAN raw frame ROIs
            detector = self._get_face_detector()
            best_face_crop = None
            best_face_score = -1.0
            best_face_flags: list[str] = []
            watchlist = self._load_watchlist()

            if detector is not None:
                search_rois: list[tuple[int, int, np.ndarray]] = []
                if tracks:
                    for _, (x1, y1, x2, y2, _) in tracks[:3]:
                        px1, py1 = max(0, x1 - 14), max(0, y1 - 14)
                        px2, py2 = min(w, x2 + 14), min(h, y2 + 14)
                        crop = raw[py1:py2, px1:px2]
                        if crop.size > 0:
                            search_rois.append((px1, py1, crop))
                elif state.custom_source:
                    search_rois.append((0, 0, raw))

                for ox, oy, roi in search_rois:
                    detector.setInputSize((roi.shape[1], roi.shape[0]))
                    _, faces = detector.detect(roi)
                    if faces is None:
                        continue
                    for face_row in faces:
                        fx, fy, fw, fh = map(int, face_row[:4])
                        conf = float(face_row[14])
                        # Reject tiny / low-confidence background texture false hits
                        if conf < 0.68 or fw < 22 or fh < 22:
                            continue
                        face_img = roi[max(0, fy) : min(roi.shape[0], fy + fh), max(0, fx) : min(roi.shape[1], fx + fw)]
                        if face_img.size == 0:
                            continue
                        face_hits += 1
                        eye_mid = (float(face_row[4]) + float(face_row[6])) / 2
                        yaw = (float(face_row[8]) - eye_mid) / max(fw, 1)
                        q_score, _, q_flags = analysis._occlusion_and_quality(roi, face_row, face_img, conf, yaw)

                        # Check live face against flagged Case Watchlist via SFace 128-D
                        matched_label = ""
                        matched_sim = 0.0
                        if watchlist:
                            emb, _ = analysis._extract_embedding(roi, face_row, face_img)
                            for entry in watchlist:
                                sim = analysis.descriptor_similarity(emb, entry["vec"])
                                if sim is not None and sim >= 0.56 and sim > matched_sim:
                                    matched_sim = sim
                                    matched_label = entry["label"]

                        ax1, ay1 = ox + max(0, fx), oy + max(0, fy)
                        ax2, ay2 = ax1 + fw, ay1 + fh
                        has_occ = any(f in q_flags for f in ("possible mask", "possible helmet", "possible cap / headgear"))

                        if matched_label:
                            f_color = (56, 68, 228)
                            flabel = f"SUSPECT MATCH: {matched_label} ({int(matched_sim * 100)}%)"
                            alert_kind = "stream.suspect_match"
                            alert_msg = f"WATCHLIST MATCH on {state.meta['id']}: {matched_label} ({int(matched_sim * 100)}% SFace match)"
                            watchlist_match_label = f"{matched_label} ({int(matched_sim * 100)}%)"
                        elif has_occ:
                            occ_tag = next(f for f in q_flags if f.startswith("possible "))
                            f_color = (56, 128, 235)
                            flabel = f"FACE {int(q_score)}% · {occ_tag.upper()}"
                            if not alert_kind:
                                alert_kind = "stream.occlusion_detected"
                                alert_msg = f"{occ_tag.title()} flagged on {state.meta['id']} (Q {int(q_score)}/100)"
                        else:
                            f_color = (90, 198, 240)
                            flabel = f"FACE {int(q_score)}%"

                        face_boxes_to_draw.append((ax1, ay1, ax2, ay2, flabel, f_color))
                        if q_score > best_face_score:
                            best_face_score = q_score
                            best_face_crop = face_img
                            best_face_flags = q_flags

            if best_face_crop is not None:
                ok_f, f_jpg = cv2.imencode(".jpg", best_face_crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
                if ok_f:
                    state.latest_face_jpeg = f_jpg.tobytes()
                    state.latest_face_score = round(best_face_score, 1)
                    state.latest_face_flags = best_face_flags
                    state.latest_face_at = _now_iso()

            state.person_count = len(tracks)
            state.face_count = face_hits
            state.active_tracks = len(state.previous_boxes)
            state.watchlist_hit = watchlist_match_label
            state.alert_state = "alert" if alert_kind else ("active" if (tracks or face_hits) else "clear")
            if alert_msg:
                state.last_alert = alert_msg

            has_activity = bool(tracks or face_hits)
            if has_activity and (now_mono - state.last_log_ts >= 5.0 or (alert_kind and now_mono - state.last_alert_ts >= 10.0)):
                stamp = _now_iso()
                state.last_log_ts = now_mono
                try:
                    with store.connect() as db:
                        top_tid, top_box = tracks[0] if tracks else (0, (0, 0, 0, 0, 0.8))
                        db.execute(
                            "INSERT INTO stream_detections VALUES(?,?,?,?,?,?,?,?)",
                            (
                                uuid.uuid4().hex,
                                state.meta["id"],
                                top_tid,
                                max(len(tracks), 1 if face_hits else 0),
                                round(float(top_box[4]), 3),
                                alert_kind,
                                stamp,
                                json.dumps({"zone": state.meta["zone"], "source": state.source_label, "faces": face_hits, "watchlist": watchlist_match_label}),
                            ),
                        )
                        if alert_kind and now_mono - state.last_alert_ts >= 10.0:
                            state.last_alert_ts = now_mono
                            db.execute(
                                "INSERT INTO events VALUES(?,?,?,?,?,?,?,?)",
                                (
                                    uuid.uuid4().hex,
                                    None,
                                    None,
                                    alert_kind,
                                    alert_msg,
                                    "critical" if alert_kind == "stream.suspect_match" else "warning",
                                    stamp,
                                    json.dumps({"cameraId": state.meta["id"], "personCount": len(tracks), "faces": face_hits}),
                                ),
                            )
                except Exception:
                    pass

        # 3) Now draw crisp overlays AFTER all AI inference is done
        cv2.rectangle(canvas, (zx1, zy1), (zx2, zy2), (72, 138, 178), 1, cv2.LINE_AA)
        cv2.putText(canvas, "ATM ZONE", (zx1 + 8, zy1 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (150, 205, 235), 1, cv2.LINE_AA)

        for tid, (x1, y1, x2, y2, conf) in tracks:
            dwell = now_mono - state.track_start_ts.get(tid, now_mono)
            color = (72, 145, 240) if alert_kind else (78, 200, 155)
            cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
            tag = f"PERSON #{tid} {int(conf * 100)}% ({dwell:.0f}s)"
            cv2.rectangle(canvas, (x1, max(0, y1 - 20)), (min(w, x1 + 175), y1), color, -1)
            cv2.putText(canvas, tag, (x1 + 4, max(14, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (12, 24, 36), 1, cv2.LINE_AA)

        for ax1, ay1, ax2, ay2, flabel, f_color in face_boxes_to_draw:
            cv2.rectangle(canvas, (ax1, ay1), (ax2, ay2), f_color, 2)
            cv2.putText(canvas, flabel, (ax1, max(16, ay1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.42, f_color, 1, cv2.LINE_AA)

        ts_str = datetime.now().strftime("%H:%M:%S")
        cv2.rectangle(canvas, (w - 92, h - 22), (w, h), (12, 34, 54), -1)
        cv2.putText(canvas, ts_str, (w - 82, h - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (228, 236, 242), 1, cv2.LINE_AA)

        if alert_kind:
            bar_color = (182, 42, 42) if alert_kind == "stream.suspect_match" else (165, 62, 46)
            cv2.rectangle(canvas, (0, h - 26), (w - 94, h), bar_color, -1)
            cv2.putText(canvas, f"ALERT: {alert_msg[:58]}", (8, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
        return canvas

    def _placeholder_jpeg(self, state: StreamState, message: str) -> bytes:
        canvas = np.full((360, 640, 3), (17, 36, 52), dtype=np.uint8)
        cv2.putText(canvas, f"{state.meta['id']} - {state.meta['name']}", (28, 165), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (236, 240, 244), 2, cv2.LINE_AA)
        cv2.putText(canvas, message, (28, 205), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (225, 178, 96), 1, cv2.LINE_AA)
        ok, jpg = cv2.imencode(".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, 82])
        return jpg.tobytes() if ok else b""

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, name="drishti-streams", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._running = False
            for state in self._streams.values():
                state.status = "standby"

    def _run_loop(self) -> None:
        caps: dict[str, cv2.VideoCapture] = {}
        active_sources: dict[str, str] = {}
        try:
            while self.is_running():
                loop_start = time.monotonic()
                for stream_id, state in self._streams.items():
                    src_val, src_label, is_live = self._resolve_source(state)
                    if src_val is None:
                        if stream_id in caps:
                            caps[stream_id].release()
                            caps.pop(stream_id, None)
                            active_sources.pop(stream_id, None)
                        state.status = "no_source"
                        state.source_label = src_label
                        state.latest_jpeg = self._placeholder_jpeg(state, "Slot available · Add Footage or IP Webcam")
                        continue
                    src_key = str(src_val)
                    if active_sources.get(stream_id) != src_key or stream_id not in caps or not caps[stream_id].isOpened():
                        if stream_id in caps:
                            caps[stream_id].release()
                        cap = cv2.VideoCapture(src_val)
                        if is_live:
                            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        caps[stream_id] = cap
                        active_sources[stream_id] = src_key
                        state.source_path = src_key
                        state.source_label = src_label

                    cap = caps[stream_id]
                    if is_live:
                        cap.grab()
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        if is_live:
                            state.status = "reconnecting"
                            state.latest_jpeg = self._placeholder_jpeg(state, f"Connecting to {src_label}...")
                            cap.release()
                            active_sources.pop(stream_id, None)
                            continue
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ok, frame = cap.read()
                    if not ok or frame is None:
                        state.status = "decode_error"
                        state.latest_jpeg = self._placeholder_jpeg(state, "Could not decode local stream")
                        continue

                    if not is_live:
                        for _ in range(2):
                            cap.grab()

                    annotated = self._annotate_frame(state, frame, detect=True)
                    ok_jpg, jpg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 78])
                    if ok_jpg:
                        with self._lock:
                            state.latest_jpeg = jpg.tobytes()
                            state.status = "streaming"
                            state.frames_processed += 1
                            state.last_frame_at = _now_iso()
                            elapsed = max(0.15, time.monotonic() - loop_start)
                            state.fps = round(min(15.0, 1.0 / elapsed), 1)
                sleep_for = max(0.03, 0.14 - (time.monotonic() - loop_start))
                time.sleep(sleep_for)
        finally:
            for cap in caps.values():
                cap.release()

    def export_live_buffer(self, stream_id: str, output_path: Path) -> bool:
        state = self._streams.get(stream_id)
        if not state:
            return False
        with self._lock:
            frames = list(state.ring_buffer)
        if len(frames) < 8:
            return False
        h, w = frames[0].shape[:2]
        writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), 8.0, (w, h))
        if not writer.isOpened():
            return False
        try:
            for frame in frames:
                writer.write(frame)
        finally:
            writer.release()
        return output_path.is_file() and output_path.stat().st_size > 0

    def snapshot_jpeg(self, stream_id: str) -> bytes:
        state = self._streams.get(stream_id)
        if not state:
            raise KeyError(stream_id)
        src_val, src_label, is_live = self._resolve_source(state)
        state.source_label = src_label
        if src_val is None:
            return self._placeholder_jpeg(state, "Slot available · Add Footage or IP Webcam")
        with self._lock:
            if state.latest_jpeg and self.is_running():
                return state.latest_jpeg
        if is_live and not self.is_running():
            return self._placeholder_jpeg(state, f"Ready: {src_label}. Click Start Live AI.")
        state.source_path = str(src_val)
        cap = cv2.VideoCapture(src_val)
        try:
            ok, frame = cap.read()
            if not ok or frame is None:
                return self._placeholder_jpeg(state, "Preview unavailable")
            annotated = self._annotate_frame(state, frame, detect=True)
            ok_jpg, jpg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 82])
            if ok_jpg:
                with self._lock:
                    state.latest_jpeg = jpg.tobytes()
                return jpg.tobytes()
        finally:
            cap.release()
        return self._placeholder_jpeg(state, "Preview unavailable")

    def latest_face_jpeg(self, stream_id: str) -> bytes | None:
        state = self._streams.get(stream_id)
        if not state:
            raise KeyError(stream_id)
        with self._lock:
            return state.latest_face_jpeg or None

    def mjpeg_generator(self, stream_id: str) -> Generator[bytes, None, None]:
        self.start()
        while True:
            frame = self.snapshot_jpeg(stream_id)
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            time.sleep(0.14)
            if not self.is_running():
                break

    def status(self) -> dict[str, Any]:
        items = []
        for stream_id, state in self._streams.items():
            src_val, src_label, is_live = self._resolve_source(state)
            items.append(
                {
                    "id": stream_id,
                    "channelId": state.meta["channelId"],
                    "name": state.meta["name"],
                    "zone": state.meta["zone"],
                    "status": state.status if (self.is_running() and src_val is not None) else ("ready" if src_val is not None else "no_source"),
                    "sourceAdapter": state.meta["sourceAdapter"],
                    "sourceLabel": src_label,
                    "customSource": state.custom_source,
                    "isLiveCamera": is_live,
                    "sourceAvailable": src_val is not None,
                    "personCount": state.person_count,
                    "faceCount": state.face_count,
                    "activeTracks": state.active_tracks,
                    "fps": state.fps,
                    "framesProcessed": state.frames_processed,
                    "alertState": state.alert_state,
                    "lastAlert": state.last_alert,
                    "watchlistHit": state.watchlist_hit,
                    "lastFrameAt": state.last_frame_at,
                    "hasFaceCapture": bool(state.latest_face_jpeg),
                    "latestFaceScore": state.latest_face_score,
                    "latestFaceFlags": state.latest_face_flags,
                    "latestFaceAt": state.latest_face_at,
                    "latestFaceUrl": f"/api/streams/{stream_id}/latest-face.jpg",
                    "mjpegUrl": f"/api/streams/{stream_id}/mjpeg",
                    "snapshotUrl": f"/api/streams/{stream_id}/frame.jpg",
                }
            )
        return {
            "running": self.is_running(),
            "detector": f"{analysis.model_status()['person']} + {analysis.model_status()['face']}",
            "mode": "local_pilot_sandbox",
            "notice": "4-camera live person + face + watchlist pilot (2 demo feeds loaded, 2 slots ready for IP Webcam / custom video).",
            "streams": items,
        }


manager = LocalSurveillanceManager()
