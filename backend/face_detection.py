"""InsightFace SCRFD-10GF inference with the five-landmark layout used by OpenCV."""

from functools import lru_cache
import logging

import cv2
import numpy as np


@lru_cache(maxsize=1)
def load_scrfd(weights):
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    cpu = "CPUExecutionProvider"
    if "CoreMLExecutionProvider" in ort.get_available_providers():
        try:
            session = ort.InferenceSession(str(weights), options, providers=["CoreMLExecutionProvider", cpu])
            detector = SCRFD(session)
            detector(np.zeros((640, 640, 3), dtype=np.uint8))
            return detector
        except Exception as exc:
            logging.getLogger(__name__).warning("SCRFD Core ML unavailable, using CPU: %s", exc)
    return SCRFD(ort.InferenceSession(str(weights), options, providers=[cpu]))


@lru_cache(maxsize=12)
def anchors(stride):
    grid = np.mgrid[: 640 // stride, : 640 // stride][::-1]
    return np.repeat(grid.transpose(1, 2, 0).reshape(-1, 2), 2, axis=0) * stride


class SCRFD:
    def __init__(self, session):
        self.session = session
        self.input_name = session.get_inputs()[0].name

    def __call__(self, frame):
        height, width = frame.shape[:2]
        scale = 640 / max(height, width)
        resized_width = max(1, round(width * scale))
        resized_height = max(1, round(height * scale))
        resized = cv2.resize(frame, (resized_width, resized_height))
        image = np.zeros((640, 640, 3), dtype=np.uint8)
        image[:resized_height, :resized_width] = resized
        blob = cv2.dnn.blobFromImage(image, 1 / 128, mean=(127.5,) * 3, swapRB=True)
        outputs = self.session.run(None, {self.input_name: blob})

        rows = []
        for index, stride in enumerate((8, 16, 32)):
            scores = outputs[index].reshape(-1)
            keep = scores >= 0.50
            centers = anchors(stride)[keep]
            distances = outputs[index + 3].reshape(-1, 4)[keep] * stride
            landmarks = outputs[index + 6].reshape(-1, 5, 2)[keep] * stride
            top_left = centers - distances[:, :2]
            size = centers + distances[:, 2:] - top_left
            landmarks += centers[:, None, :]
            rows.append(np.column_stack((top_left, size, landmarks.reshape(-1, 10), scores[keep])))
        faces = np.concatenate(rows).astype(np.float32)
        faces[:, :14:2] *= width / resized_width
        faces[:, 1:14:2] *= height / resized_height
        faces = faces[(faces[:, 0] < width) & (faces[:, 1] < height)]
        keep = cv2.dnn.NMSBoxes(faces[:, :4].tolist(), faces[:, 14].tolist(), 0.499, 0.4)
        return faces[np.asarray(keep, dtype=int).ravel()]
