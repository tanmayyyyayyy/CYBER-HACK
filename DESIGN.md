---
name: Drishti ATM Forensic Review
description: Local-first ATM video evidence review for transaction-linked investigation.
colors:
  navy-deep: "#0c2236"
  navy: "#112b43"
  navy-raised: "#1b3c58"
  sand: "#f1f0eb"
  paper: "#ffffff"
  ink: "#1d2d3b"
  ink-soft: "#536575"
  line: "#dfe3e5"
  amber: "#bd7d2d"
  amber-soft: "#f6ecd9"
  teal: "#197b72"
  teal-soft: "#e0f2ee"
  red: "#b64e45"
  red-soft: "#f9e9e6"
typography:
  body:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.45
  title:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "25px"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "-0.025em"
  label:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "9px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.13em"
  record:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace"
    fontSize: "9px"
    fontWeight: 400
    lineHeight: 1.2
rounded:
  sm: "4px"
  md: "6px"
  lg: "7px"
spacing:
  xs: "5px"
  sm: "9px"
  md: "14px"
  lg: "21px"
  xl: "34px"
components:
  button-primary:
    backgroundColor: "{colors.navy}"
    textColor: "{colors.paper}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "36px"
  button-outline:
    backgroundColor: "{colors.paper}"
    textColor: "#324858"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "36px"
  card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "14px"
---

# Design System: Drishti ATM Forensic Review

## Overview

**Creative North Star: The Evidence Room.**

The interface takes its cues from a focused investigation desk: restrained institutional navy, warm paper surfaces, measured amber emphasis, and compact metadata that keeps timestamps and provenance close to the evidence. The Rajasthan Police inspiration is expressed through a professional control-room tone; this is a prototype and does not represent an official system.

The dashboard is information-dense but keeps each action legible. Candidate frames and clip details remain the center of attention, while status colors carry clear meaning. Synthetic evidence and local-only processing are labeled directly in the product.

**Key Characteristics:**
- Calm, operational hierarchy with compact, scannable labels.
- Warm paper and sand surfaces against a deep navy rail.
- Human-reviewed evidence, provenance, and confidence qualifiers stay visible.

## Colors

The palette pairs deep institutional blue with warm neutral surfaces; amber signals review emphasis, teal signals healthy local status, and muted red marks warnings.

### Primary
- **Control Navy**: The navigation rail, primary actions, and strong structural anchors.
- **Review Amber**: Selected candidates, active navigation accents, and transaction markers.

### Secondary
- **Verification Teal**: Local-ready and integrity-positive states.
- **Alert Red**: Integrity mismatches and attention states; use with an explanatory label.

### Neutral
- **Deep Rail Navy**: The fixed navigation surface.
- **Warm Sand**: The application canvas around cards and work areas.
- **Evidence Paper**: Candidate cards, tables, and review panels.
- **Record Ink**: Primary text; softer ink is reserved for supporting metadata.
- **Divider Gray**: Quiet card and table boundaries.

**The Meaningful Status Rule.** Amber, teal, and red communicate a review state; do not use them as decoration.

## Typography

**Display Font:** IBM Plex Sans (with sans-serif fallback)  
**Body Font:** IBM Plex Sans (with sans-serif fallback)  
**Label/Mono Font:** IBM Plex Sans for labels; system monospace for hashes and machine records.

**Character:** A practical, neutral sans keeps the interface readable under dense information. Tabular numerals and compact uppercase labels make times and statuses easy to scan.

### Hierarchy
- **Headline** (600, 25px, 1.15): Main workspace title.
- **Title** (600, 12–15px): Panel and card headings.
- **Body** (400, 12px, 1.45): Explanations and ordinary controls.
- **Label** (700, 8–10px, 0.08–0.13em): Eyebrows, state labels, and compact metadata.

**The Provenance Readability Rule.** Hashes and event identifiers use monospace with tabular numerals; explanatory copy stays in the body face.

## Layout

The desktop shell uses a fixed 248px navigation rail and a flexible work area capped at 1600px. Page gutters are 34px on desktop and contract at smaller breakpoints. The transaction review uses a compact four-column summary, then evidence and candidate panels; the four channel cards are recorded clip slots. At narrow widths, the rail becomes an off-canvas drawer and multi-column summaries collapse to fewer columns.

## Elevation & Depth

Depth comes primarily from tonal separation and fine borders. A soft shadow lifts summary and evidence panels from the sand canvas; stronger shadows are reserved for overlays and interactive hover states.

### Shadow Vocabulary
- **Panel Lift** (`0 8px 22px rgba(16, 37, 54, .06)`): Summary and evidence panels.
- **Overlay Lift** (`0 12px 30px rgba(16,38,56,.16)`): Transient toast feedback.

**The Quiet Surface Rule.** Keep resting panels flat and calm; reserve stronger depth for a surfaced interaction.

## Shapes

Corners are gently squared (4–7px) to keep the interface operational rather than playful. Use thin gray borders to define cards and controls. Status dots and count pills may be circular; evidence panels remain rectangular.

## Components

### Buttons
- **Shape:** Compact corners (5px), clear text, and a 36px minimum height.
- **Primary:** White on control navy, with 12px horizontal padding.
- **Hover / Focus:** Navy shifts lighter on hover; keyboard focus uses a visible amber outline.
- **Secondary:** White surface with a fine gray border.

### Chips
- **Style:** Short uppercase label on a pale semantic tint, with a fine border.
- **State:** Green tint means local-ready; amber is a review marker; red is a warning and must include text.

### Cards / Containers
- **Corner Style:** 6–7px.
- **Background:** Evidence paper on warm sand, with a fine divider border.
- **Shadow Strategy:** Low panel lift at rest.
- **Internal Padding:** Use the 14px panel rhythm; larger page gutters remain 34px on desktop.

### Inputs / Fields
- **Style:** White surface, muted gray stroke, compact corners.
- **Focus:** Three-pixel amber outline with a two-pixel offset.
- **Disabled:** Reduce opacity and preserve a readable label.

### Navigation
- Deep navy rail with quiet text at rest. Active navigation receives a slightly raised navy surface, a fine amber-tinted outline, and amber icon. On small screens it becomes a drawer with a scrim.

### Evidence Candidate
Candidate frames sit on white cards with a subtle border. Selection uses an amber border and a restrained ring; score and quality flags stay alongside the image so the reviewer can assess why a frame ranked well.

## Do's and Don'ts

### Do:
- **Do** keep event time, camera/channel, and source provenance beside evidence.
- **Do** use status colors consistently and pair warnings with text.
- **Do** preserve the current compact, readable control-room hierarchy.
- **Do** keep synthetic/sample labels visible in the interface.

### Don't:
- **Don't** imply official Rajasthan Police endorsement or use unprovided government insignia.
- **Don't** present visual similarity or a detector result as a confirmed identity.
- **Don't** style recorded uploaded clips as live bank CCTV.
- **Don't** use amber, teal, or red for decoration.
