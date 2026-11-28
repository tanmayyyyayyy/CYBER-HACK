# Drishti Digital Forensics brand kit

## Logo

`assets/drishti-logo-original.png` is the supplied logo and the source of truth. Use the complete shield, eye, fingerprint, DRISHTI wordmark, and DIGITAL FORENSICS descriptor on welcome and login screens. In tight app navigation, use a proportional crop of the supplied shield only; never redraw or stretch it. Keep clear space around the logo and use it on a white or deep navy background. Do not add police insignia or suggest official endorsement.

`brand-board.png` is an illustrative application board. Its recreated logo and sample UI are concept references; the actual product must use the original asset.

## Color system

| Token | Hex | Use |
| --- | --- | --- |
| Navy | `#061B3B` | Brand heading, navigation, high contrast text |
| Navy raised | `#09244C` | Hover and selected navigation |
| Gold | `#F8B443` | Primary action and selected step, always with navy text |
| Warm white | `#FAFAF8` | App background |
| Cool gray | `#E9EEF2` | Quiet grouped areas and borders |
| Text | `#172A40` | Reading text |
| White | `#FFFFFF` | Forms, evidence, logo backing |
| Red | `#B53F3F` | Errors only, with text explanation |
| Green | `#196D51` | Verified/saved state only, with text explanation |

Gold is the one brand accent. Never use it for warnings: “Warning” should have a clear label and separate semantic treatment. Keep primary buttons gold with navy text. Avoid glows, gradients, generic security graphics, and dense dashboards.

## Typography and accessibility

Use locally hosted Noto Sans with Devanagari support for UI text. Keep body text at least 16 px, labels at least 14 px, and touch targets at least 44 px. Use sentence case. Do not use the bold display wordmark as a body font. Provide icons together with words. Do not rely on color alone.

## Product voice

Simple Hinglish, one instruction per screen. Examples: “Naya case shuru karein”, “Video chunein”, “File theek hai?”, “Transaction ka time batayein”, “Chehra dekhein”, “Pakka nahi”, “Possible match”, “Report download karein”. Explain terms such as codec and FFmpeg in plain words beside the relevant choice. Do not claim a face match proves identity.

## Navigation and flow

Login → New case → Upload → File check → Transaction → Scan → Transaction person → Best frames → Search → Evidence sheet.

Show only the current step, its immediate context, and one main action. Provide Back and save progress. Officer must confirm a person or choose “Pakka nahi”. Search results say “Possible match”. Evidence sheet download is available after human review.
