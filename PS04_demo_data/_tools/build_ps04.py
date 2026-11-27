"""PS04 dataset builder: turns your own ATM-style video clips into the demo dataset.

  python3 build_ps04.py init  <root>   -> scans <root>/raw_videos, writes <root>/clip_manifest.csv
  python3 build_ps04.py build <root>   -> 02_videos/, 03_transactions/, 04_cases/, 99_answer_key/

<root>/01_reference/atm_master.csv decides each ATM's export format, resolution, DVR clock offset
and night look.

Needs ffmpeg: on PATH, in env FFMPEG, or `pip install imageio-ffmpeg`.

macOS / Linux note:
  The FONT path defaults to Consolas on Windows. On macOS the script auto-detects a monospace
  font from /Library/Fonts, /System/Library/Fonts, or /usr/share/fonts. You can override with:
    export DRISHTI_FONT=/path/to/font.ttf
"""

import csv
import datetime as dt
import hashlib
import os
import platform
import random
import re
import shutil
import subprocess
import sys
from collections import defaultdict

R = random.Random(404)
BASE = dt.datetime(2026, 10, 14, 11, 5, 0)   # first clip's true (bank) clock start

VIDEO_EXT = (".mp4", ".mov", ".avi", ".mkv", ".3gp", ".m4v", ".wmv", ".mpg", ".mpeg", ".flv", ".webm")


# ------------------------------------------------------------------ font auto-detection
def _find_monospace_font() -> str:
    """Return an ffmpeg-safe path to a monospace TTF/OTF font for the drawtext filter."""
    # Env override always wins
    if os.environ.get("DRISHTI_FONT"):
        return os.environ["DRISHTI_FONT"]

    system = platform.system()

    # Windows: Consolas is always present
    if system == "Windows":
        win_path = r"C:\Windows\Fonts\consola.ttf"
        if os.path.exists(win_path):
            return win_path.replace("\\", "/").replace(":", "\\:")  # ffmpeg escaping

    # macOS candidates (Courier New, Menlo, Monaco, SF Mono)
    mac_candidates = [
        "/Library/Fonts/Courier New.ttf",
        "/System/Library/Fonts/Courier New.ttf",
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Monaco.ttf",
    ]
    # Linux candidates
    linux_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/usr/share/fonts/truetype/ubuntu/UbuntuMono-R.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    ]

    for p in (mac_candidates if system == "Darwin" else linux_candidates):
        if os.path.exists(p):
            return p

    # Last resort: ask fc-match
    try:
        result = subprocess.run(["fc-match", "monospace", "--format=%{file}"], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except FileNotFoundError:
        pass

    # Give up — drawtext will still work but may use a default font
    return "monospace"


FONT = _find_monospace_font()


# ------------------------------------------------------------------ ffmpeg
def ffmpeg_exe():
    if os.environ.get("FFMPEG"):
        return os.environ["FFMPEG"]
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise RuntimeError(
            "ffmpeg not found. Install it (brew install ffmpeg / apt install ffmpeg) "
            "or pip install imageio-ffmpeg."
        )


FF = None


def run(args):
    p = subprocess.run(
        [FF, "-hide_banner", "-loglevel", "error", "-y"] + args,
        capture_output=True, text=True,
    )
    if p.returncode:
        raise RuntimeError("ffmpeg failed: " + " ".join(str(a) for a in args[:6]) + "\n" + p.stderr[-800:])


def probe(path):
    p = subprocess.run(
        [FF, "-hide_banner", "-i", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    err = p.stderr
    dur = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    vid = re.search(r"Video: (\w+).*?, (\d{2,5})x(\d{2,5})", err)
    fps = re.search(r"([\d.]+) fps", err)
    secs = (
        int(dur.group(1)) * 3600 + int(dur.group(2)) * 60 + float(dur.group(3))
        if dur else None
    )
    return dict(
        duration=round(secs, 2) if secs else "",
        codec=vid.group(1) if vid else "",
        res=f"{vid.group(2)}x{vid.group(3)}" if vid else "",
        fps=fps.group(1) if fps else "",
    )


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


# ------------------------------------------------------------------ init
MANIFEST_COLS = [
    "clip_id", "source_file", "atm_id", "role", "person_id", "other_person_ids",
    "txn_person_enter_sec", "txn_card_insert_sec", "txn_cash_taken_sec",
    "txn_person_exit_sec", "other_txn_card_insert_sec",
    "occlusion", "lighting", "consent_form_id", "notes",
    "duration_sec", "resolution", "fps",
]


def init(root: str):
    """Scan raw_videos/, probe each file, write clip_manifest.csv template."""
    raw = os.path.join(root, "raw_videos")
    if not os.path.isdir(raw):
        sys.exit(f"ERROR: {raw!r} not found. Create it and place your videos inside.")

    files = sorted(f for f in os.listdir(raw) if f.lower().endswith(VIDEO_EXT))
    if not files:
        sys.exit(f"ERROR: no video files found in {raw}. Supported: {VIDEO_EXT}")

    atm_path = os.path.join(root, "01_reference", "atm_master.csv")
    if not os.path.exists(atm_path):
        sys.exit(f"ERROR: {atm_path!r} not found.")
    atms = [a["atm_id"] for a in read_csv(atm_path)]

    rows = []
    for i, f in enumerate(files, 1):
        p = probe(os.path.join(raw, f))
        rows.append([
            f"C{i:02d}", "raw_videos/" + f, atms[(i - 1) % len(atms)],
            "primary", "", "", "", "", "", "", "",
            "none", "day", "", "",
            p["duration"], p["res"], p["fps"],
        ])
        print(f"C{i:02d}  {f}  {p['duration']}s  {p['res']}  {p['fps']} fps")

    out = os.path.join(root, "clip_manifest.csv")
    if os.path.exists(out):
        out = os.path.join(root, "clip_manifest.NEW.csv")
    write_csv(out, MANIFEST_COLS, rows)
    print("wrote", out, "- fill the blank columns, then run: build")


# ------------------------------------------------------------------ encoding profiles
_HAS_DRAWTEXT: bool | None = None


def _ffmpeg_has_drawtext() -> bool:
    """Return True if the active ffmpeg binary supports the libfreetype drawtext filter."""
    global _HAS_DRAWTEXT
    if _HAS_DRAWTEXT is None:
        p = subprocess.run([FF, "-hide_banner", "-filters"], capture_output=True, text=True)
        _HAS_DRAWTEXT = bool(re.search(r"\bdrawtext\b", p.stdout))
    return _HAS_DRAWTEXT


def _overlay_filter(atm_id: str, epoch: int) -> str:
    """drawtext filter: burns ATM ID + camera-clock timestamp into top-left corner."""
    # Escape the font path for ffmpeg filtergraph (colons must be escaped on all OS)
    safe_font = FONT.replace("\\", "/").replace(":", "\\:")
    return (
        f"drawtext=fontfile='{safe_font}':"
        f"text='{atm_id}  %{{pts\\:gmtime\\:{epoch}\\:%Y-%m-%d %H\\\\\\:%M\\\\\\:%S}}'"
        ":x=10:y=10:fontsize=h/22:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=4"
    )


def _render_cv2_clock_source(src: str, tmp_out: str, atm_id: str, cam0: dt.datetime) -> str:
    """Fallback clock burn-in via OpenCV when ffmpeg was built without libfreetype drawtext."""
    try:
        import cv2
    except ImportError:
        return src
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        return src
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)
    writer = cv2.VideoWriter(tmp_out, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    if not writer.isOpened():
        cap.release()
        return src
    scale = max(0.45, h / 540.0)
    idx = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            ts = cam0 + dt.timedelta(seconds=idx / fps)
            label = f"{atm_id}  {ts.strftime('%Y-%m-%d %H:%M:%S')}"
            (tw, th), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
            cv2.rectangle(frame, (8, 8), (18 + tw, 18 + th + baseline), (0, 0, 0), -1)
            cv2.putText(frame, label, (13, 14 + th), cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), 1, cv2.LINE_AA)
            writer.write(frame)
            idx += 1
    finally:
        cap.release()
        writer.release()
    return tmp_out


PROFILES = {
    "MP4_H264_720P":  (".mp4", "scale=-2:720",    ["-c:v", "libx264", "-crf", "23", "-preset", "veryfast", "-pix_fmt", "yuv420p"]),
    "AVI_MJPEG_VGA":  (".avi", "scale=640:480",   ["-c:v", "mjpeg",   "-q:v", "6",  "-pix_fmt", "yuvj420p"]),
    "MKV_H265_1080P": (".mkv", "scale=-2:1080",   ["-c:v", "libx265", "-crf", "28", "-preset", "fast",     "-pix_fmt", "yuv420p"]),
    "MOV_H264_720P":  (".mov", "scale=-2:720",    ["-c:v", "libx264", "-crf", "24", "-preset", "veryfast", "-pix_fmt", "yuv420p"]),
    "WMV_LOW_360P":   (".wmv", "scale=640:360",   ["-c:v", "wmv2",    "-b:v", "450k"]),
    "DVR_CIF_NIGHT":  (
        ".mpg",
        "fps=8,scale=352:288,hue=s=0,eq=brightness=-0.12:contrast=1.35,noise=alls=18:allf=t",
        ["-c:v", "mpeg2video", "-q:v", "8", "-pix_fmt", "yuv420p"],
    ),
}

COVERAGE_CODECS = {
    "mp4": ["-c:v", "libx264",     "-crf",  "23",  "-pix_fmt", "yuv420p"],
    "avi": ["-c:v", "mpeg4",       "-q:v",  "5"],
    "mov": ["-c:v", "libx264",                      "-pix_fmt", "yuv420p"],
    "mkv": ["-c:v", "libx264",                      "-pix_fmt", "yuv420p"],
    "wmv": ["-c:v", "wmv2",        "-b:v",  "900k"],
    "flv": ["-c:v", "flv1",        "-b:v",  "900k"],
    "mpg": ["-c:v", "mpeg2video",  "-q:v",  "5",   "-pix_fmt", "yuv420p"],
}


def num(x):
    return float(x) if str(x).strip() not in ("", "None") else None


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ build
def build(root: str):
    """Build the full PS04 dataset from raw_videos/ + clip_manifest.csv."""
    atm_path = os.path.join(root, "01_reference", "atm_master.csv")
    man_path = os.path.join(root, "clip_manifest.csv")
    if not os.path.exists(atm_path):
        sys.exit(f"ERROR: {atm_path!r} not found.")
    if not os.path.exists(man_path):
        sys.exit(f"ERROR: {man_path!r} not found. Run 'init' first.")

    atms = {a["atm_id"]: a for a in read_csv(atm_path)}
    man  = read_csv(man_path)

    vdir = os.path.join(root, "02_videos")
    for d in ("02_videos", "03_transactions", "04_cases", "99_answer_key"):
        shutil.rmtree(os.path.join(root, d), ignore_errors=True)

    t_cursor = BASE
    clips: list = []
    ej: dict = defaultdict(list)
    victims: dict = {}
    stan: dict = defaultdict(lambda: R.randrange(1000, 9000))

    def card() -> str:
        return R.choice(["4591", "6521", "5244", "6070", "4213"]) + "XXXXXXXX" + str(R.randrange(1000, 9999))

    def add_txn(atm, insert_t, amount, card_no, kind, clip_id, who,
                cash_taken=None, exit_t=None, resp="00") -> str:
        stan[atm] += 1
        s = stan[atm]
        rrn = f"{insert_t.year % 10}{insert_t.strftime('%j%H')}{s % 1_000_000:06d}"
        ej[atm].append(dict(
            insert=insert_t, amount=amount, card=card_no, kind=kind, stan=s, rrn=rrn,
            resp=resp, clip=clip_id, who=who,
            cash_taken=cash_taken or insert_t + dt.timedelta(seconds=34),
            exit=exit_t or insert_t + dt.timedelta(seconds=40),
        ))
        return rrn

    for row in man:
        src = os.path.join(root, row["source_file"].replace("/", os.sep))
        if not os.path.exists(src):
            print(f"SKIP (file missing): {row['clip_id']}  {row['source_file']}")
            continue

        atm = atms.get(row["atm_id"])
        if not atm:
            print(f"SKIP (unknown atm_id {row['atm_id']}): {row['clip_id']}")
            continue

        p   = probe(src)
        dur = float(p["duration"] or 60)
        t0  = t_cursor + dt.timedelta(minutes=R.randrange(9, 26), seconds=R.randrange(60))
        t_cursor = t0 + dt.timedelta(seconds=dur)

        offset = int(atm["camera_clock_offset_sec"])
        cam0   = t0 + dt.timedelta(seconds=offset)
        epoch  = int((cam0 - dt.datetime(1970, 1, 1)).total_seconds())

        ext, vf, codec = PROFILES[atm["dvr_export_profile"]]
        atm_vdir = os.path.join(vdir, row["atm_id"])
        os.makedirs(atm_vdir, exist_ok=True)

        name = f"{row['atm_id']}_CH01_{cam0.strftime('%Y%m%d%H%M%S')}"
        out  = os.path.join(atm_vdir, name + ext)
        use_drawtext = _ffmpeg_has_drawtext()
        stamped_tmp = os.path.join(atm_vdir, f".{name}_stamped.mp4")
        encode_src = src if use_drawtext else _render_cv2_clock_source(src, stamped_tmp, row["atm_id"], cam0)
        ovl = _overlay_filter(row["atm_id"], epoch)
        try:
            vf_main = f"{vf},{ovl}" if use_drawtext else vf
            run(["-i", encode_src, "-an", "-vf", vf_main, *codec,
                 "-metadata", f"creation_time={cam0.strftime('%Y-%m-%dT%H:%M:%S')}", out])

            files = [os.path.relpath(out, root)]
            sha   = sha256_file(out)

            # Extra raw H.264 elementary stream for DVR_CIF_NIGHT
            if atm["dvr_export_profile"] == "DVR_CIF_NIGHT":
                raw = os.path.join(atm_vdir, name + "_raw.264")
                vf_raw = vf.replace("fps=8", "fps=6") + ("," + ovl if use_drawtext else "")
                run(["-i", encode_src, "-an", "-vf", vf_raw,
                     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-f", "h264", raw])
                files.append(os.path.relpath(raw, root))
        finally:
            if os.path.exists(stamped_tmp):
                os.remove(stamped_tmp)

        # Format-coverage copies (one per COVERAGE_CODECS format)
        cov_dir = os.path.join(vdir, "format_coverage")
        os.makedirs(cov_dir, exist_ok=True)
        for fmt, fcodec in COVERAGE_CODECS.items():
            cov_out = os.path.join(cov_dir, f"{row['clip_id']}_coverage.{fmt}")
            try:
                run(["-i", src, "-an", "-vf", "scale=-2:480", *fcodec, cov_out])
            except RuntimeError as e:
                print(f"  coverage {fmt} skipped: {e}")

        c = dict(row=row, atm=atm, t0=t0, cam0=cam0, offset=offset,
                 files=files, dur=dur, probe=p, sha=sha)

        # Generate transactions
        ins = num(row["txn_card_insert_sec"])
        if ins is not None and row["role"] in ("primary", "distractor"):
            if row["role"] == "primary":
                v = victims.setdefault(row["person_id"], dict(
                    victim=f"V{len(victims) + 1:02d}", card=card(), rrns=[],
                ))
                if R.random() < 0.5:   # skimmers often check balance first
                    add_txn(row["atm_id"], t0 + dt.timedelta(seconds=ins),
                            0, v["card"], "BALANCE ENQUIRY", row["clip_id"], row["person_id"])
                rrn = add_txn(
                    row["atm_id"],
                    t0 + dt.timedelta(seconds=ins + 12),
                    R.choice([10000, 10000, 9500, 5000, 20000]),
                    v["card"], "CASH WITHDRAWAL", row["clip_id"], row["person_id"],
                    t0 + dt.timedelta(seconds=num(row["txn_cash_taken_sec"]) or ins + 34),
                    t0 + dt.timedelta(seconds=num(row["txn_person_exit_sec"]) or ins + 42),
                )
                v["rrns"].append((rrn, row["clip_id"]))
                c["victim"] = v["victim"]
                c["rrn"]    = rrn
            else:
                c["rrn"] = add_txn(
                    row["atm_id"],
                    t0 + dt.timedelta(seconds=ins + 10),
                    R.choice([500, 1000, 2000, 3000]),
                    card(), "CASH WITHDRAWAL", row["clip_id"], row["person_id"],
                )

        oth = num(row["other_txn_card_insert_sec"])
        if oth is not None:
            add_txn(
                row["atm_id"],
                t0 + dt.timedelta(seconds=oth + 10),
                R.choice([1000, 2000, 4000]),
                card(), "CASH WITHDRAWAL", row["clip_id"],
                row.get("other_person_ids", ""),
            )

        clips.append(c)
        print(f"  {row['clip_id']}  {row['atm_id']}  {cam0.strftime('%H:%M:%S')}  "
              f"{ext}  SHA256={sha[:12]}…")

    # ---- write EJ logs ----
    txn_dir = os.path.join(root, "03_transactions")
    os.makedirs(txn_dir, exist_ok=True)
    for atm_id, entries in ej.items():
        atm = atms[atm_id]
        ej_path = os.path.join(txn_dir, f"{atm_id}_ej.txt")
        bk_path = os.path.join(txn_dir, f"{atm_id}_bank_statement.csv")
        with open(ej_path, "w", encoding="utf-8") as f:
            f.write(f"{'─' * 72}\n")
            f.write(f"  ELECTRONIC JOURNAL  ATM: {atm_id}  {atm['bank']}  {atm['location']}\n")
            f.write(f"{'─' * 72}\n")
            for e in sorted(entries, key=lambda x: x["insert"]):
                ts = e["insert"].strftime("%d/%m/%Y %H:%M:%S")
                f.write(f"{ts}   TRANSACTION START\n")
                f.write(f"{ts}   CARD INSERTED\n")
                f.write(f"{ts}   CARD NUMBER: {e['card']}\n")
                f.write(f"{ts}   OPCODE: {e['kind']}  AMOUNT: {e['amount']:,.2f}\n")
                f.write(f"{ts}   STAN {e['stan']:06d}  RRN {e['rrn']}  RESP {e['resp']}\n")
                if e["kind"] != "BALANCE ENQUIRY":
                    f.write(f"{e['cash_taken'].strftime('%d/%m/%Y %H:%M:%S')}   NOTES TAKEN\n")
                    f.write(f"{e['exit'].strftime('%d/%m/%Y %H:%M:%S')}   CARD TAKEN\n")
                f.write(f"{e['exit'].strftime('%d/%m/%Y %H:%M:%S')}   TRANSACTION END\n")
                f.write(f"{'─' * 72}\n")

        bal = R.uniform(10000, 90000)
        bk_rows = []
        for e in sorted(entries, key=lambda x: x["insert"]):
            if e["kind"] == "BALANCE ENQUIRY" or e["resp"] != "00":
                continue
            bal -= e["amount"]
            bk_rows.append([
                e["insert"].strftime("%d-%m-%Y %H:%M:%S"),
                e["insert"].strftime("%d-%m-%Y"),
                f"ATM WDL/{atm_id}/{atm['location'].upper()}/STAN {e['stan']:06d}",
                e["rrn"],
                f"{e['amount']:.2f}", "",
                f"{bal:.2f}",
            ])
        write_csv(bk_path,
                  ["Txn Date", "Value Date", "Description", "Ref No./Cheque No.",
                   "Debit", "Credit", "Balance"],
                  bk_rows)
        print(f"  EJ → {os.path.basename(ej_path)}  ({len(entries)} txns)")

    # ---- write cases ----
    cases_dir = os.path.join(root, "04_cases")
    os.makedirs(cases_dir, exist_ok=True)
    for person_id, v in victims.items():
        case_dir = os.path.join(cases_dir, v["victim"])
        os.makedirs(case_dir, exist_ok=True)
        with open(os.path.join(case_dir, "case_brief.txt"), "w", encoding="utf-8") as f:
            f.write(f"CASE: {v['victim']}  PERSON: {person_id}  CARD: {v['card']}\n")
            f.write(f"{'─' * 60}\n")
            for rrn, clip_id in v["rrns"]:
                c = next((x for x in clips if x["row"]["clip_id"] == clip_id), None)
                if c:
                    f.write(f"  RRN {rrn}  CLIP {clip_id}  ATM {c['atm']['atm_id']}  "
                            f"CAMERA_TIME {c['cam0'].strftime('%Y-%m-%d %H:%M:%S')}\n")
                    for fi in c["files"]:
                        f.write(f"    video: {fi}\n")
        print(f"  Case {v['victim']} → {case_dir}")

    # ---- answer key ----
    ak_dir = os.path.join(root, "99_answer_key")
    os.makedirs(ak_dir, exist_ok=True)
    ak_rows = []
    for c in clips:
        row = c["row"]
        ak_rows.append([
            row["clip_id"], row["atm_id"], row["role"], row["person_id"],
            c.get("victim", ""),
            c.get("rrn", ""),
            c["t0"].strftime("%Y-%m-%d %H:%M:%S"),
            c["cam0"].strftime("%Y-%m-%d %H:%M:%S"),
            c["offset"],
            "; ".join(c["files"]),
            c["sha"],
        ])
    write_csv(
        os.path.join(ak_dir, "answer_key.csv"),
        ["clip_id", "atm_id", "role", "person_id", "victim_id", "rrn",
         "bank_time_t0", "camera_time_t0", "clock_offset_sec", "output_files", "sha256"],
        ak_rows,
    )

    print("\n✓ Build complete.")
    print(f"  {len(clips)} clip(s) processed  →  {vdir}")
    print(f"  {sum(len(v) for v in ej.values())} transaction(s) written  →  {txn_dir}")
    print(f"  {len(victims)} case(s)  →  {cases_dir}")
    print(f"  Answer key  →  {os.path.join(ak_dir, 'answer_key.csv')}")


# ------------------------------------------------------------------ proprietary stub
def _write_dav_stub(root: str):
    """Write a fake Dahua .dav stub so tools can test 'unsupported format' detection."""
    prop_dir = os.path.join(root, "02_videos", "proprietary")
    os.makedirs(prop_dir, exist_ok=True)
    stub = os.path.join(prop_dir, "UDR0019.export.dav")
    if not os.path.exists(stub):
        with open(stub, "wb") as f:
            # DHAV magic header + junk
            f.write(b"DHAV" + b"\x00" * 508)
        print(f"  DAV stub → {stub}")


# ------------------------------------------------------------------ CLI
def main():
    global FF
    FF = ffmpeg_exe()

    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    cmd, root = sys.argv[1], sys.argv[2]
    root = os.path.abspath(root)

    if cmd == "init":
        init(root)
    elif cmd == "build":
        build(root)
        _write_dav_stub(root)
    else:
        sys.exit(f"Unknown command {cmd!r}. Use 'init' or 'build'.")


if __name__ == "__main__":
    main()

