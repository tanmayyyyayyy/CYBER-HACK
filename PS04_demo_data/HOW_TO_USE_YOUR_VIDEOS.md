# How to use your own videos with the PS04 demo dataset

This folder is the **PS04 demo dataset** for the Rajasthan Police Hackathon 2026 (RPH26).
The builder script (`_tools/build_ps04.py`) converts your own ATM-style footage into a
structured multi-ATM dataset complete with EJ transaction logs, cases, and an answer key.

---

## Prerequisites

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows — download from https://ffmpeg.org/download.html and add to PATH
```

Python 3.8+ is required (no extra packages needed).

**macOS font note:** the drawtext overlay auto-detects Courier New / Menlo from
`/Library/Fonts` or `/System/Library/Fonts`. Override with:
```bash
export DRISHTI_FONT=/path/to/YourFont.ttf
```

---

## Step 1 — Film your clips

**Shot checklist:**
- [ ] Camera above or in front of the actor (simulate ATM position)
- [ ] Actor's face clearly visible when "inserting card" and "collecting cash"
- [ ] At least one clip with a cap or helmet (occlusion test)
- [ ] At least one clip with low light or backlight (lighting test)
- [ ] At least one clip with two people in frame (shoulder-surfing / bystander)
- [ ] Signed consent form for every volunteer (see `00_format_samples/volunteer_consent_form.md`)
- [ ] Record the form ID on the consent form before filming

**Minimum recommended:** 5 clips, 3 different people, mix of day/night/occluded.

---

## Step 2 — Place your videos

Copy your video files into `raw_videos/`.

Supported formats: `.mp4 .mov .avi .mkv .3gp .m4v .wmv .mpg .mpeg .flv .webm`

---

## Step 3 — Generate the manifest

From the **project root** (`CYBER-HACK/`):

```bash
python3 PS04_demo_data/_tools/build_ps04.py init PS04_demo_data/
```

This scans `raw_videos/`, probes each file with ffmpeg, and writes `PS04_demo_data/clip_manifest.csv`.

---

## Step 4 — Fill in the manifest

Open `clip_manifest.csv` in a spreadsheet or text editor. Fill in the blank columns:

| Column | What to fill |
|---|---|
| `atm_id` | pick from `01_reference/atm_master.csv` (JPR0142, JPR0317, …) |
| `role` | `primary` (suspect), `distractor` (innocent bystander), `search` (target only appears in search) |
| `person_id` | unique label per person: P01, P02 … (same person = same ID across clips) |
| `other_person_ids` | comma-separated IDs of other people visible in this clip |
| `txn_person_enter_sec` | seconds from clip start when person enters frame |
| `txn_card_insert_sec` | seconds when person inserts card (leave blank for search/distractor) |
| `txn_cash_taken_sec` | seconds when cash is taken |
| `txn_person_exit_sec` | seconds when person leaves frame |
| `other_txn_card_insert_sec` | if a second person also transacts, their card insert second |
| `occlusion` | `none`, `cap`, `mask`, `sunglasses`, `helmet`, `backlit` |
| `lighting` | `day`, `night`, `backlit`, `low` |
| `consent_form_id` | the form ID written on the signed consent form |
| `notes` | any free text |

See `00_format_samples/clip_manifest_TEMPLATE.csv` for 5 example rows.

---

## Step 5 — Build the dataset

```bash
python3 PS04_demo_data/_tools/build_ps04.py build PS04_demo_data/
```

This generates:
- `02_videos/` — re-encoded clips in ATM-specific formats with burned-in clock overlay
- `02_videos/format_coverage/` — same clip in every PS04 format (MP4, AVI, MKV, MOV, WMV, FLV, MPEG)
- `02_videos/proprietary/UDR0019.export.dav` — fake Dahua stub to test unsupported-format detection
- `03_transactions/` — EJ journal `.txt` and bank statement `.csv` per ATM
- `04_cases/` — one folder per primary person with a case brief linking RRNs to clips
- `99_answer_key/` — `answer_key.csv` with correct person IDs, RRNs, SHA-256 hashes (**judges only**)

---

## Consent reminder

🔒 **Do not upload recordings to public websites or social media.**
All video data must be deleted within the number of days you wrote on the consent form.
Videos must not be matched against Aadhaar or any criminal database.
See `00_format_samples/volunteer_consent_form.md` for the full terms.

