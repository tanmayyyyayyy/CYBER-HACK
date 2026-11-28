from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import cv2
import numpy as np

DVR_EXPORT_GUIDANCE: list[dict[str, str]] = [
    {
        "vendor": "Hikvision / iVMS-4200",
        "steps": "Playback -> Clip/Download -> Select MP4/AVI container (avoid proprietary .exe self-player).",
    },
    {
        "vendor": "Dahua / SmartPSS",
        "steps": "Export -> Format: MP4 or AVI (instead of raw .dav). If only .dav is available, Drishti normalizes unencrypted .dav via FFmpeg.",
    },
    {
        "vendor": "CP Plus / KVMS Pro",
        "steps": "Backup -> Video Format: MP4 (H.264). Disable proprietary watermark encryption before export.",
    },
    {
        "vendor": "Manual FFmpeg CLI",
        "steps": "ffmpeg -protocol_whitelist file,pipe -i export.dav -c:v libx264 -pix_fmt yuv420p -movflags +faststart atm_clip.mp4",
    },
]


def detect_proprietary_dvr(path: Path) -> str | None:
    """Detect proprietary/unplayable DVR containers (e.g., Dahua DHAV) and return conversion guidance."""
    try:
        header = path.open("rb").read(16)
    except OSError:
        return None
    suffix = path.suffix.lower()
    if header.startswith(b"DHAV") or suffix == ".dav":
        return (
            "Unsupported proprietary Dahua .dav (DHAV) DVR export detected. "
            "Convert with the DVR vendor's Smart Player / SmartPSS -> Export to MP4/AVI, "
            "ask the bank to re-export via DVR 'Backup -> MP4', or if the underlying stream is raw H.264 run: "
            "ffmpeg -f h264 -i input.264 -c copy output.mp4"
        )
    return None


def probe_video_container(path: Path) -> dict[str, Any]:
    """Inspect container format, streams, encoder tag, and GOP anomalies via ffprobe."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"probed": False, "reason": "ffprobe not installed", "guidance": DVR_EXPORT_GUIDANCE}
    try:
        proc = subprocess.run(
            [
                ffprobe,
                "-v", "error",
                "-show_format",
                "-show_streams",
                "-of", "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        data = json.loads(proc.stdout or "{}")
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError) as exc:
        return {
            "probed": False,
            "reason": f"Container probe failed ({type(exc).__name__})",
            "guidance": DVR_EXPORT_GUIDANCE,
        }

    fmt = data.get("format", {})
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    tags = {**(fmt.get("tags") or {}), **(video.get("tags") or {})}
    encoder = str(tags.get("encoder") or tags.get("ENCODER") or "")
    format_name = str(fmt.get("format_name") or "unknown")
    codec_name = str(video.get("codec_name") or "unknown")
    pix_fmt = str(video.get("pix_fmt") or "unknown")
    bit_rate = int(fmt.get("bit_rate") or video.get("bit_rate") or 0)
    nb_frames = int(video.get("nb_frames") or 0)

    cues: list[str] = []
    if "lavf" in encoder.lower():
        cues.append(f"Muxed with FFmpeg/Lavf ({encoder}) — verify original DVR export provenance.")
    if codec_name.lower() in {"hevc", "h265"}:
        cues.append("HEVC/H.265 DVR stream detected; normalized locally to H.264 for browser review.")
    if format_name.lower() in {"h264", "hevc", "mpegts"}:
        cues.append(f"Raw/transport DVR stream ({format_name}); timestamp indexing stabilized via local normalization.")

    return {
        "probed": True,
        "formatName": format_name,
        "codecName": codec_name,
        "pixFmt": pix_fmt,
        "bitRateKbps": round(bit_rate / 1000, 1) if bit_rate else 0,
        "nbFrames": nb_frames,
        "encoderTag": encoder or "Not specified",
        "cues": cues,
    }


def check_frame_continuity(path: Path, max_samples: int = 48) -> dict[str, Any]:
    """Run a fast local continuity check for abrupt luminance splices or blackouts."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return {"checked": False, "spliceCues": 0, "blackoutFrames": 0, "cues": []}
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0) or 25.0
    step = max(1, total // max_samples) if total > max_samples else 1
    prev_mean: float | None = None
    splice_cues: list[str] = []
    blackouts = 0
    idx = 0
    sampled = 0
    try:
        while sampled < max_samples:
            if total > max_samples:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            mean_val = float(gray.mean())
            if mean_val < 10.0:
                blackouts += 1
            if prev_mean is not None and abs(mean_val - prev_mean) > 48.0:
                ts = idx / fps
                splice_cues.append(f"Sudden luminance jump ({prev_mean:.0f} -> {mean_val:.0f}) near {int(ts // 60):02}:{int(ts % 60):02}")
            prev_mean = mean_val
            idx += step
            sampled += 1
    finally:
        cap.release()
    return {
        "checked": True,
        "sampled": sampled,
        "spliceCues": len(splice_cues),
        "blackoutFrames": blackouts,
        "cues": splice_cues[:5],
    }


def enhance_face_crop(face_bgr: np.ndarray, label: bool = True, fused: bool = False) -> np.ndarray:
    """
    Deterministic, non-hallucinating forensic contrast/sharpness enhancement.
    Always clearly labelled so reviewers never mistake it for raw evidence.
    """
    if face_bgr is None or face_bgr.size == 0:
        raise ValueError("Empty face image.")
    h, w = face_bgr.shape[:2]
    target_w = max(w * 2, 224)
    target_h = max(h * 2, 224)
    upscaled = cv2.resize(face_bgr, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)
    denoised = cv2.bilateralFilter(upscaled, d=5, sigmaColor=28, sigmaSpace=28)
    lab = cv2.cvtColor(denoised, cv2.COLOR_BGR2LAB)
    l_chan, a_chan, b_chan = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(4, 4))
    l_enh = clahe.apply(l_chan)
    merged = cv2.cvtColor(cv2.merge([l_enh, a_chan, b_chan]), cv2.COLOR_LAB2BGR)
    blurred = cv2.GaussianBlur(merged, (0, 0), sigmaX=1.2)
    sharpened = cv2.addWeighted(merged, 1.38, blurred, -0.38, 0)
    return label_enhanced_crop(sharpened, fused) if label else sharpened


def label_enhanced_crop(image: np.ndarray, fused: bool) -> np.ndarray:
    height, width = image.shape[:2]
    canvas = np.full((height + 26, max(width, 200), 3), (17, 43, 67), dtype=np.uint8)
    left = (canvas.shape[1] - width) // 2
    canvas[:height, left:left + width] = image
    cv2.putText(
        canvas,
        "MULTI-FRAME - REVIEW ONLY" if fused else "ENHANCED - REVIEW ONLY",
        (6, height + 17),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.36,
        (235, 190, 110),
        1,
        cv2.LINE_AA,
    )
    return canvas


def video_frame_time(cap) -> float:
    seconds = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
    frame_index = cap.get(cv2.CAP_PROP_POS_FRAMES) - 1
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    return seconds if seconds > 0 or frame_index <= 0 else frame_index / fps


def seek_video_frame(cap, seconds: float) -> bool:
    """Grab the first frame at the requested clip time, checking its decoded timestamp."""
    seconds = max(0.0, seconds)
    rewind = 0.0
    while True:
        seek_at = max(0.0, seconds - rewind)
        cap.set(cv2.CAP_PROP_POS_MSEC, seek_at * 1000)
        ok = cap.grab()
        if ok and (seek_at == 0 or video_frame_time(cap) <= seconds + 0.0005):
            break
        if seek_at == 0:
            return False
        rewind = max(1.0, rewind * 2)

    while video_frame_time(cap) < seconds - 0.0005:
        if not cap.grab():
            return False
    return True


def redact_bystanders_frame(
    video_path: Path,
    frame_seconds: float,
    target_bbox: list[int] | None,
    face_detector: Any,
    clip_sha_prefix: str,
) -> bytes:
    """
    Extract the frame at frame_seconds, blur all bystander faces except target_bbox,
    and stamp provenance metadata for DPDP-compliant privacy export.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError("Could not open source clip for frame extraction.")
    try:
        ok, frame = cap.retrieve() if seek_video_frame(cap, frame_seconds) else (False, None)
        if not ok or frame is None:
            raise ValueError("Could not seek to the requested timestamp in the clip.")
    finally:
        cap.release()

    h, w = frame.shape[:2]
    blurred_count = 0
    if face_detector is not None:
        faces = face_detector(frame)
        if faces is not None:
            tx1, ty1, tx2, ty2 = target_bbox if target_bbox and len(target_bbox) == 4 else (-1, -1, -1, -1)
            tcx, tcy = (tx1 + tx2) / 2.0, (ty1 + ty2) / 2.0
            for row in faces:
                fx, fy, fw, fh = map(int, row[:4])
                x1, y1 = max(0, fx), max(0, fy)
                x2, y2 = min(w, fx + fw), min(h, fy + fh)
                if x2 <= x1 or y2 <= y1:
                    continue
                is_target = False
                if tx2 > tx1 and ty2 > ty1:
                    if x1 <= tcx <= x2 and y1 <= tcy <= y2:
                        is_target = True
                if is_target:
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (55, 175, 145), 2)
                else:
                    roi = frame[y1:y2, x1:x2]
                    k = max(15, ((min(roi.shape[:2]) // 3) | 1))
                    frame[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (k, k), 0)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (160, 175, 185), 1)
                    blurred_count += 1

    # Highlight the recorded target box even if this pass misses it.
    if target_bbox and len(target_bbox) == 4:
        tx1, ty1, tx2, ty2 = [max(0, int(v)) for v in target_bbox]
        if tx2 > tx1 and ty2 > ty1:
            cv2.rectangle(frame, (tx1, ty1), (tx2, ty2), (225, 168, 90), 2)

    footer = f"DRISHTI PRIVACY EXPORT | t={frame_seconds:.2f}s | BYSTANDERS BLURRED: {blurred_count} | SHA256:{clip_sha_prefix[:12]}"
    cv2.rectangle(frame, (0, max(0, h - 28)), (w, h), (12, 34, 54), -1)
    cv2.putText(frame, footer, (10, max(18, h - 9)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (238, 242, 245), 1, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        raise RuntimeError("Could not encode redacted frame.")
    return encoded.tobytes()

