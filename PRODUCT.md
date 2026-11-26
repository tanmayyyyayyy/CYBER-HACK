# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React + Python API, chosen by the user; run locally with no cloud services.

## Users

Authorised investigators reviewing ATM footage for a specific bank transaction, and hackathon evaluators assessing the workflow. Initial demonstration is restricted to hackathon-provided or synthetic clips.

## Product Purpose

Help an investigator inspect ATM footage around a supplied transaction timestamp, review the clearest candidate face frames with quality signals, search for visually similar candidates in other supplied clips, and export a traceable evidence sheet. Success means less manual scrubbing while keeping the final decision with a human reviewer.

## Positioning

Transaction-time-first forensic review: a configurable time window narrows the footage before face candidates are ranked for clarity. Similarity search returns review candidates only; it does not identify a person.

## Operating Context

Single-machine local product pilot for transaction-linked ATM video review. Input is a video file plus transaction time and optional transaction reference. Reviewers compare candidate stills, inspect clip/time provenance, add notes, and export evidence. No bank connection or live CCTV is part of this product.

## Capabilities and Constraints

- Accept common video formats supported by the local FFmpeg/OpenCV installation; validate and report codec, dimensions, duration, and timestamp errors.
- Focus the analysis window around the transaction time, detect/track people, locate face candidates, score frame quality, and let a reviewer select and search candidate faces across other uploaded clips.
- Keep processing, clip metadata, review records, and exports on the local machine. External APIs, cloud databases, telemetry, and remote services are disabled.
- Record SHA-256 fingerprints for the uploaded source and analyzed bytes, with an on-demand local integrity verification and an audit event for each check.
- Similarity results are pseudonymous, limited to the supplied clips, and require human review. No criminal/Aadhaar matching or automatic identity claims.
- No R4C sample dataset or model weights were present in the supplied repositories at setup. Until provided, demonstrations use synthetic clips or clearly labelled demo records.
- The SIH source project is an IBVAP border-surveillance platform; its person detector/tracker/streaming ideas are references, not a mandate to retain ANPR, border rules, face registries, or cloud integrations.
- The supplied God's Eye View repository is a separate public-camera/map application; its CCTV source/provider architecture may inform local adapters, but no live camera endpoint is assumed or enabled.

## Brand Commitments

The interface should feel like a professional Rajasthan Police-inspired control room, without implying official endorsement or using government insignia as decoration.

## Evidence on Hand

- `../sih-2026-raw`: IBVAP React/Vite dashboard, FastAPI backend, YOLO person detection, ByteTrack, event pipeline, and MJPEG stream implementation.
- `../gods-eye-view`: public CCTV catalog/source architecture; not a ready ATM stream source.
- No ATM sample clips, matching transaction records, trained weights, official Rajasthan Police brand assets, or endorsement evidence were supplied.

## Product Principles

- Keep evidence local by default.
- Make timestamps, quality signals, and provenance inspectable.
- Rank frames to assist review; never present a machine result as identity proof.
- Preserve a human decision and an audit trail at each evidence action.
- Label synthetic data and limitations plainly.
- Keep all detector/model artifacts pinned, checksummed, and license-reviewed before redistribution or operational deployment.
