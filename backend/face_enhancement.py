"""Combine compatible face crops explicitly confirmed by an operator."""

import cv2
import numpy as np


def enhance(crops: list[np.ndarray]) -> tuple[np.ndarray, list[int]]:
    """Keep the highest-ranked crop as the anchor and reject poor alignment."""
    anchor = crops[0]
    height, width = anchor.shape[:2]
    if min(height, width) < 32:
        return anchor, [0]
    reference = cv2.cvtColor(anchor, cv2.COLOR_BGR2GRAY)
    pixels = anchor.astype(np.float32)
    weights = np.ones((height, width, 1), dtype=np.float32)
    used = [0]
    for index, crop in enumerate(crops[1:], 1):
        if min(crop.shape[:2]) < 32:
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
        weight = compatible[:, :, None].astype(np.float32) * .25
        pixels += aligned * weight
        weights += weight
        used.append(index)
    return np.rint(pixels / weights).astype(np.uint8), used
