# FlashFrame

**Image ↔ camera-flash / screen-blink optical transfer.**

Encode a picture into a sequence of brightness flashes (fullscreen screen blinks or LED-style pulses). A second device watches with its camera (or you feed a recorded brightness signal) and reconstructs the image.

```
  ┌─────────────┐         light / blinks          ┌─────────────┐
  │  Phone A    │  ─────────────────────────────► │  Phone B    │
  │  transmitter│   fullscreen white/black        │  receiver   │
  │  (screen)   │         flashes                 │  (webcam)   │
  └──────▲──────┘                                 └──────┬──────┘
         │ image                                          │ brightness(t)
         │                                                ▼
   flashframe encode                              flashframe decode
   → timeline.json                                → rebuilt.png
```

v1 demos **without two phones** via a perfect-channel software simulator:

```
photo → encode → timeline.json → simulate → signal.csv → decode → rebuilt.png
```

Point two phones at each other for the live path: Phone A runs `static/transmitter.html` (screen blinks); Phone B records video / samples mean luminance and runs `flashframe decode-video`.

## Protocol (v1)

1. **Resize** image to a small grayscale grid (default **32×32**).
2. **Preamble** — unique raw on/off pattern `10101010 11110000` (16 symbols) for lock.
3. **Header** (11 bytes, then coded) — magic `FF`, version, width, height, bit depth, coding, CRC32.
4. **Payload** — pixel bits (MSB first), default 8-bit grayscale.
5. **Coding**
   - **Manchester** (default): `0 → 10`, `1 → 01` (edge in the middle of each bit).
   - **PWM / OOK**: bright = 1, dark = 0, fixed `frame_ms` per bit.
6. Each symbol lasts `frame_ms` (default **40 ms**).

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# optional webcam / video decode:
pip install -e ".[webcam]"
```

## CLI

```bash
flashframe encode photo.jpg -o timeline.json --size 32
flashframe simulate timeline.json -o signal.csv   # perfect channel
flashframe decode signal.csv -o rebuilt.png
flashframe decode-signal signal.csv -o rebuilt.png
flashframe decode-video recording.mp4 -o rebuilt.png   # needs opencv
flashframe demo
```

### Live transmitter (HTML)

Open `static/transmitter.html` in a mobile browser, load the JSON from `encode`, crank brightness, and start flashing. A second phone pointed at the screen can record; decode with `decode-video` or export mean-luminance CSV and `decode`.

Prefer Pillow + numpy. Webcam / MP4 sampling uses `opencv-python-headless` when installed (`[webcam]` extra); otherwise use the simulator path.

## Make targets

```bash
make install   # venv + editable install
make test      # pytest round-trip
make demo      # evidence/ artifacts
make verify    # test + demo (CI green)
```

## Layout

```
src/flashframe/     protocol, encode, simulate, decode, cli
static/             transmitter.html (fullscreen blinks)
tests/              round-trip + CLI demo
evidence/           demo outputs (timeline, signal, rebuilt PNG)
```

## License

MIT — see [LICENSE](LICENSE).
