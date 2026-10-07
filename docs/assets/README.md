# docs/assets/

Brand + marketing assets for the README hero and docs.

| File | Status | Notes |
|---|---|---|
| `logo.png` | ✅ present | Black-and-white square conversation mark, without a wordmark. Used in both root README headers and copied into the frontend for navigation and the browser icon. |
| `demo.gif` | ⏳ **TBD — launch-critical** | The single most important asset for a voice product. Record a **15–40s** flow: upload CV + JD → talk to the interviewer → scorecard. Payoff visible in the first ~2s. Referenced by the root README (`docs/assets/demo.gif`). |
| `screenshot-setup.png` | ⏳ TBD | The `/setup` screen (CV drop, JD paste, language + persona pick). |
| `screenshot-interview.png` | ⏳ TBD | The live `/interview/[id]` screen (avatar stage + live transcript). |
| `screenshot-report.png` | ⏳ TBD | The `/report/[id]` scorecard (competency radar + model answers). |

## Conventions

- **Demo GIF:** keep it under ~8 MB so it renders inline on GitHub. Record at the brand's light editorial look (paper background, one indigo accent) — not a dark-neon gradient. Source MP4 can live alongside as `demo.mp4` for the X/Twitter launch video.
- **Screenshots:** light theme, 2x density, crop tight to the content.
- **Logo:** `docs/assets/logo.png` is the source of truth. Keep `frontend/public/logo.png` and `frontend/src/app/icon.png` identical to it when updating the logo. `BrandMark` displays `/logo.png`; Next.js discovers `src/app/icon.png` as the browser icon.

> The hero `demo.gif` is the top item on the WP-13 launch checklist — the README references it today, but the file itself is still to be recorded.

## demo.gif

Hero demo for the main README: live interview room (Dana speaking, captions
streaming, typed answer echoed as YOU, adaptive follow-up) → scored report. Recorded
from the real app via browser automation on the offline demo CV/JD (no real
candidate PII), 1554×784, 14 frames, ~1.9 MB. Re-record after major UI changes.
