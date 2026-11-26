# Repository analysis and integration notes

## `sih-2026-raw` (IBVAP)

The relevant pipeline is `VideoSource → YOLO person detector → ByteTracker → event/incident logic → MJPEG`. The edge processor also runs face detection, but its face registry assigns `SOLDIER` / `INTRUDER` roles and syncs embeddings from the backend. The backend can write to Supabase/PostgreSQL and the UI expects a separate command center.

For PS04, this product carries forward person detection, lightweight track continuity, local video metadata and timestamped event recording. It replaces the face registry with per-clip candidate crops, quality scores, human review, local SQLite audit entries and an evidence sheet. Border fences, line crossings, loitering, ANPR, watchlist roles, cloud database configuration and remote edge transmission are not part of the ATM task. Runtime person detection uses the OpenCV Zoo MediaPipe ONNX model; YOLO was removed after identifying its AGPL/commercial licensing implications.

The cloned repository did not contain trained model weights. This workspace downloads model assets into the main repo's ignored `models/` folder for local operation.

## `gods-eye-view`

Its CCTV view is a source-provider abstraction around catalogs, health, frame URLs, media URLs and upstream proxy routes. The feeds are public city-camera sources (including upstream image and HLS families), not an ATM/DVR export. The ATM problem statement scopes this milestone to investigator-supplied files and excludes live bank CCTV, so Drishti uses four local evidence channels for uploaded recordings instead of connecting unrelated public feeds.

## Main repository

`CYBER-HACK` was empty at the supplied GitHub URL. This workspace initializes it as the hackathon product. The two source repositories remain sibling clones for reference and are not copied into the main project's runtime.
