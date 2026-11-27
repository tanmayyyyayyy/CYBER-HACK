# CCTV video formats in this dataset

| ATM | Export profile | Container / codec | Resolution / fps | What it tests |
|---|---|---|---|---|
| JPR0142 | MP4_H264_720P | .mp4 / H.264 | 1280×720, source fps | clean baseline |
| JPR0317 | AVI_MJPEG_VGA | .avi / Motion-JPEG | 640×480 | old DVR export, large files |
| AJM0055 | MKV_H265_1080P | .mkv / H.265 (HEVC) | 1920×1080 | codec support (HEVC) |
| JDH0208 | MOV_H264_720P | .mov / H.264 | 1280×720 | QuickTime container |
| KOT0091 | WMV_LOW_360P | .wmv / WMV8 | 640×360, low bitrate | compression artefacts |
| UDR0019 | DVR_CIF_NIGHT | .mpg / MPEG-2 and raw `.264` (no container) | 352×288, 6–8 fps, grayscale IR | worst case: CIF, low fps, night, raw stream with no timestamps |

Format-coverage copies (`02_videos/format_coverage/`) re-encode one clip to **every** format named in PS04: MP4, AVI, MOV, MKV, WMV, FLV, MPEG/MPG.

Each clip burns a camera clock (`ATM_ID YYYY-MM-DD HH:MM:SS`) into the top-left corner, as most DVRs do. **The camera clock is not the bank clock.** Each ATM has a clock offset (see `atm_master.csv`): from a few seconds up to 1 hour (a wrong timezone on UDR0019). Tools must use a configurable time window around the transaction time.

## Proprietary DVR files

`02_videos/proprietary/UDR0019.export.dav` imitates a Dahua `.dav` export (it starts with the `DHAV` magic but is **not playable**). The expected behaviour is that the tool detects it and reports that it is unsupported, with conversion instructions such as:

- Convert with the DVR vendor's own player / converter (vendor "Smart Player" / client software → export to MP4/AVI).
- If the export is a raw H.264/H.265 stream: `ffmpeg -f h264 -i input.264 -c copy output.mp4` (frame rate may need `-r`).
- Ask the bank to re-export in MP4/AVI with the DVR's "backup → MP4" option.

## Useful checks

`ffmpeg -i <file>` shows the container, codec, resolution, fps and duration. The raw `.264` has no duration or timestamps. Frame times must come from the fps and the burned-in clock.

## Clock offset alignment (worked example)

```
Bank EJ time:   2026-10-14 13:22:36  (card inserted, STAN 004512)
ATM JPR0142 offset: +18 s
Camera time to seek: 13:22:36 + 18 = 13:22:54
Search window: ±10 s  →  13:22:44 .. 13:23:04
```

Tools should expose the offset and window as configurable parameters (UI or config file).

