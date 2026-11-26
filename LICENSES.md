# Model and runtime notices

This file lists the AI model assets shipped by the setup workflow. Review all licenses with counsel before any paid deployment.

| Asset | Purpose | Upstream license | Integrity pin |
|---|---|---|---|
| `person_detection_mediapipe_2023mar.onnx` | Person/upper-body detector | Apache-2.0 per OpenCV Zoo model directory | SHA-256 pinned in `scripts/download_models.py` |
| `face_detection_yunet_2023mar.onnx` | Face detector | MIT per the model's upstream license | SHA-256 pinned in `scripts/download_models.py` |
| `face_recognition_sface_2021dec.onnx` | Local 128-D face embedding extractor | Apache-2.0 per OpenCV Zoo model directory | SHA-256 pinned in `scripts/download_models.py` |

The earlier Ultralytics YOLO model and dependency have been removed from the runtime. OpenCV HOG remains an offline fallback when the person model has not been downloaded. The OpenCV Zoo person model is designed as a lightweight detector and is not a validated ATM-camera model; collect representative, authorised clips and benchmark before an operational pilot.

The application itself includes separately licensed dependencies. Keep the generated `THIRD_PARTY_NOTICES` and package lock files with distributions, and perform a full dependency-license scan as part of release review.
