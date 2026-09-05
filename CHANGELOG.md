# Changelog

## 0.1.0 — 2026-09-05

- Initial FlashFrame release
- Encode images to brightness-flash timelines (Manchester + simple PWM)
- Perfect-channel simulator (`simulate` → CSV brightness signal)
- Decode from signal CSV or video (mean luminance windows)
- HTML fullscreen transmitter (`static/transmitter.html`)
- CLI: `encode`, `simulate`, `decode`, `decode-video`, `demo`
- Round-trip tests and `make verify`
