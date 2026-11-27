"""Review cues for sustained camera obstruction or abrupt changes in view."""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class CameraTamper:
    previous: np.ndarray | None = None
    reference: np.ndarray | None = None
    obstruction_frames: int = 0
    changed_frames: int = 0
    glare_frames: int = 0
    last_signal: str = ""

    def observe(self, frame: np.ndarray) -> str:
        scene = cv2.resize(frame, (96, 54))
        gray = cv2.cvtColor(scene, cv2.COLOR_BGR2GRAY)[5:-5, 10:-10]
        blue, green, red = cv2.split(scene[:, 24:72].astype(np.int16))
        glare = float(((red > 170) & (red > green + 35) & (red > blue + 35)).mean())
        self.glare_frames = self.glare_frames + 1 if glare > .10 else max(0, self.glare_frames - 1)
        dark_or_flat = bool((gray < 18).mean() > .88 or (gray > 244).mean() > .88 or gray.std() < 7)
        self.obstruction_frames = self.obstruction_frames + 1 if dark_or_flat else 0
        if not dark_or_flat:
            if self.reference is None and self.previous is not None and self._difference(gray, self.previous) > .62:
                self.reference = self.previous
            if self.reference is not None:
                if self._difference(gray, self.reference) > .52:
                    self.changed_frames += 1
                else:
                    self.reference = None
                    self.changed_frames = 0
            self.previous = gray
        else:
            self.reference = None
            self.changed_frames = 0
        reason = ""
        if glare > .22 or self.glare_frames >= 2:
            reason = "Sharp colored glare obscures the camera view"
        elif self.obstruction_frames >= 3:
            reason = "Camera view is obscured or overexposed"
        elif self.changed_frames >= 3:
            reason = "Camera view changed abruptly"
        if reason == self.last_signal:
            return ""
        self.last_signal = reason
        return reason

    @staticmethod
    def _difference(a: np.ndarray, b: np.ndarray) -> float:
        # Compare scene structure after removing a uniform brightness change.
        delta = a.astype(np.float32) - b
        return float((np.abs(delta - np.median(delta)) > 30).mean())
