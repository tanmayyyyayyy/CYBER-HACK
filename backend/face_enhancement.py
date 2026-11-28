"""Combine compatible face crops explicitly confirmed by an operator."""

import cv2
import numpy as np

from backend import analysis, forensics


def quality(crop, detector, face_geometry=None):
    """Local recognition-readiness rubric inspired by FaceQnet."""
    height, width = crop.shape[:2]
    pad = max(8, min(height, width) // 4)
    padded = cv2.copyMakeBorder(crop, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
    if face_geometry:
        landmarks, confidence = face_geometry
        points = np.asarray(landmarks, dtype=np.float32)
        face = np.r_[pad, pad, width, height, (points + pad).ravel(), confidence]
    else:
        face = next((row for row in detector(padded) if analysis.usable_face_row(row)
                     and row[0] <= pad + width / 2 <= row[0] + row[2]
                     and row[1] <= pad + height / 2 <= row[1] + row[3]), None)
    if face is None or not analysis.usable_face_row(face):
        return {"score": 0.0, "metrics": None, "flags": ["Face could not be verified in this crop"]}
    yaw = (face[8] - (face[4] + face[6]) / 2) / face[2]
    score, metrics, flags = analysis._occlusion_and_quality(padded, face, crop, float(face[14]), float(yaw))
    return {"score": score, "metrics": metrics, "flags": flags}


def enhance(crops: list[np.ndarray], scores: list[float], *, preserve_detail=False) -> tuple[np.ndarray, list[int]]:
    """Keep the highest-ranked crop as the anchor and reject poor alignment."""
    anchor = crops[0]
    height, width = anchor.shape[:2]
    if scores[0] <= 0 or min(height, width) < 32:
        return anchor, [0]
    reference = cv2.cvtColor(anchor, cv2.COLOR_BGR2GRAY)
    pixels = anchor.astype(np.float32)
    weights = np.ones((height, width, 1), dtype=np.float32)
    used = [0]
    for index, crop in enumerate(crops[1:], 1):
        if scores[index] <= 0 or min(crop.shape[:2]) < 32:
            continue
        resized = cv2.resize(crop, (width, height), interpolation=cv2.INTER_LINEAR)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        transform = np.eye(2, 3, dtype=np.float32)
        try:
            score, transform = cv2.findTransformECC(
                reference, gray, transform, cv2.MOTION_EUCLIDEAN,
                (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 35, 1e-4),
            )
        except cv2.error:
            continue
        if (not np.isfinite(score) or score < .88 or abs(transform[1, 0]) > .14
                or abs(transform[0, 2]) > width * .10 or abs(transform[1, 2]) > height * .10):
            continue
        aligned = cv2.warpAffine(resized, transform, (width, height),
                                 flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
        valid = cv2.warpAffine(np.ones((height, width), np.uint8), transform, (width, height),
                               flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP).astype(bool)
        difference = np.abs(aligned.astype(np.float32) - anchor).mean(axis=2)
        compatible = valid & (difference <= 24)
        if compatible.mean() < .65:
            continue
        weight = compatible[:, :, None].astype(np.float32) * (.25 * scores[index] / scores[0])
        pixels += aligned * weight
        weights += weight
        used.append(index)
        if len(used) == 5:
            break
    blended = pixels / weights
    if preserve_detail and len(used) >= 4:
        # Apply the agreed low-frequency correction while retaining the anchor's edges.
        original = anchor.astype(np.float32)
        correction = cv2.GaussianBlur(blended - original, (0, 0), 1.1)
        blended = original + correction * (weights > 1)
        if blended.mean() < 115:
            blended += max(0.0, min(8.0, 250.0 - float(np.percentile(blended, 99.5))))
    return np.clip(np.rint(blended), 0, 255).astype(np.uint8), used



def enhance_nearby(path, anchor, bbox, timestamp, score):
    """Register a short burst around a reviewed crop from the same source video."""
    x1, y1, x2, y2 = bbox
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened() or not forensics.seek_video_frame(cap, timestamp):
            return anchor, []
        ok, frame = cap.retrieve()
        if not ok or abs(forensics.video_frame_time(cap) - timestamp) > 0.001:
            return anchor, []
        source = frame[y1:y2, x1:x2]
        if source.shape != anchor.shape or np.abs(source.astype(np.float32) - anchor).mean() > 6:
            return anchor, []

        samples = [(timestamp, anchor)]
        has_frame = forensics.seek_video_frame(cap, timestamp - 0.68)
        while has_frame and len(samples) < 100:
            seconds = forensics.video_frame_time(cap)
            if seconds > timestamp + 0.68:
                break
            if abs(seconds - timestamp) > 0.001:
                ok, frame = cap.retrieve()
                if not ok:
                    break
                samples.append((seconds, frame[y1:y2, x1:x2].copy()))
            has_frame = cap.grab()
    finally:
        cap.release()

    samples.sort(key=lambda item: abs(item[0] - timestamp))
    image, used = enhance([crop for _, crop in samples], [score] * len(samples), preserve_detail=True)
    return image, [round(samples[index][0], 3) for index in used]
