# Momir Printer

A [Momir format](https://mtg.fandom.com/wiki/Momir) MTG creature printer — pick a mana value, get a random creature, and print it on a thermal printer via Bluetooth.

**Try it now: [momir.io](https://momir.io)** (Chrome/Edge on Android or desktop)

## How It Works

1. Pick a mana value (0–16)
2. Roll to get a random creature at that mana value
3. See the full card image preview in your browser (or hide it for a surprise)
4. Print the card on thermal paper — dithered art + card info in a readable layout

## Supported Printers

Phomemo thermal printers with BLE, auto-detected by device name on connect:

| Model | Print Width | Paper | Orientation |
|-------|------------|-------|-------------|
| **M02** | 384 dots | 48mm | Portrait |
| **M02S** | 576 dots | 53mm | Portrait |
| **M02 Pro** | 576 dots | 53mm | Portrait |
| **T02** | 384 dots | 48mm | Portrait |
| **M04S** | 1232 dots | 110mm | Landscape (auto-rotated) |
| **M04AS** | 1232 dots | 110mm | Landscape (auto-rotated) |

All models connect via Bluetooth Low Energy using the same GATT service (`FF00`) and write characteristic (`FF02`). Pair in your OS Bluetooth settings first (code: `0000` or `1234`).

### Printer Protocol Notes

- **M02 family** (M02, M02S, M02 Pro, T02): Standard ESC/POS init (`ESC @`) + Phomemo proprietary preamble (`1F 11 02 04`, `1F 11 24 00`). 512-byte BLE chunks.
- **M04S family** (M04S, M04AS): Different init sequence with density/heat matching (`1F 11 02 04` + `1F 11 37 96`), continuous media mode (`1F 11 0B`), raw compression (`1F 11 35 00`). **205-byte BLE chunks** (must not exceed MTU-3 = 244; 205 is the confirmed safe size from BTSnoop analysis). 3 chunks per burst with 50ms delay.
- Wide printers (M04S/M04AS) automatically rotate the card landscape and center it on the 110mm paper.
- The official Phomemo app uses L2CAP CoC for faster transfer, which is not available via Web Bluetooth or Python/bleak on macOS. GATT write-without-response is the fallback.

## Web App (momir.io)

The primary version — runs entirely in your browser, no server needed.

**Live at [https://momir.io](https://momir.io)**

### Browser Support

- Chrome/Edge on **Android** and **desktop** (macOS, Windows, Linux)
- **Not supported on iOS** — Web Bluetooth is unavailable on any iOS browser (Apple restriction, applies to Chrome on iOS too since all iOS browsers use WebKit)

### Settings

- **Auto-print** — automatically print after each roll
- **Include Un-sets** — include silver-bordered/funny cards in the pool
- **Print Art** — include Floyd-Steinberg dithered card artwork on the thermal print
- **Hide Preview** — don't show the card on screen before printing (for the surprise factor)

### Run Locally

```bash
# Build the card database (requires AtomicCards.json from MTGJSON)
python scripts/build_creatures.py

# Serve
cd web && python3 -m http.server 8080
```

Open http://localhost:8080 in Chrome. Note: Web Bluetooth requires HTTPS or localhost.

## Python Desktop App

A FastAPI-based version that runs on localhost for desktop use.

### Setup

```bash
cd momir-printer
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Install fonts (optional — falls back to system Arial)
brew install --cask font-dejavu
```

### Card Data

Download `AtomicCards.json` from [MTGJSON](https://mtgjson.com/downloads/all-files/) and place it at `~/Downloads/AtomicCards.json`.

### Run

```bash
source .venv/bin/activate
python -m momir.server
```

Open http://localhost:8000 in your browser.

### CLI Tools

Each module works standalone for testing and debugging:

```bash
# Card Store — load database, pick a random creature
python -m momir.card_store --mv 5

# Thermal Renderer — render a card to PNG
python -m momir.thermal_renderer --card "Tarmogoyf" --output debug_tarmogoyf.png

# Image Cache — fetch a card image from Scryfall
python -m momir.image_cache Lightning Bolt

# BLE Printer — scan, print, or dry-run
python -m momir.ble_printer --scan-only
python -m momir.ble_printer debug_output.png
python -m momir.ble_printer debug_output.png --dry-run output.bin
```

### BLE Tuning

A tuning script for testing different BLE communication parameters:

```bash
# Scan for printers
python scripts/tune_ble.py --scan

# Monitor printer notifications during a print
python scripts/tune_ble.py --test-notifications

# Test a parameter grid to find optimal settings
python scripts/tune_ble.py --sweep

# Test specific parameters: chunk_size burst_count delay_ms
python scripts/tune_ble.py --custom 205 3 50
```

## Architecture

```
momir.io (static web app)              Python desktop app
  │ no server                            │ REST API
  │                                    FastAPI Server
  │                                      │
  ├── Card Store (creatures.json)        ├── Card Store (AtomicCards.json)
  ├── Scryfall (browser fetch)           ├── Image Cache (disk cache)
  ├── Thermal Renderer (Canvas API)      ├── Thermal Renderer (Pillow)
  └── BLE Printer (Web Bluetooth)        └── BLE Printer (bleak)
```

Both versions auto-detect the connected printer model and select the appropriate profile (print width, init commands, BLE chunk parameters).

## Thermal Print Layout

```
┌──────────────────────────────┐
│  Card Name            {W}{U} │
├──────────────────────────────┤
│          [Card Art]          │  (when Print Art is enabled, Floyd-Steinberg dithered)
├──────────────────────────────┤
│  Creature — Type Line        │
├──────────────────────────────┤
│  Rules text, word-wrapped    │
│  to fit the print width.     │
├──────────────────────────────┤
│                        3 / 4 │
└──────────────────────────────┘
```

Wide printers (M04S/M04AS) print this layout rotated 90° and centered on the paper.

## API Endpoints (Python version)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/` | Web frontend |
| `POST` | `/roll` | Pick random creature `{mv, include_funny}` |
| `GET` | `/image/{name}` | Card image (cached from Scryfall) |
| `POST` | `/print` | Print the last rolled card |
| `GET` | `/status` | Printer state + connected model |
| `POST` | `/connect` | Connect to printer via BLE |
| `GET/POST` | `/settings` | Get/update settings |

## Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

## Tech Stack

- **Web app**: HTML/CSS/JS (no frameworks), Web Bluetooth API, Canvas API
- **Python app**: FastAPI, Pillow, bleak, httpx
- **Card data**: [MTGJSON](https://mtgjson.com) AtomicCards.json (18,000+ creatures)
- **Card images**: [Scryfall API](https://scryfall.com/docs/api)
- **Printer protocol**: Phomemo ESC/POS over BLE (service `FF00`, write `FF02`, `GS v 0` raster)
- **Build script**: Python — generates `creatures.json` (~4.7MB, <1MB gzipped) from AtomicCards.json

## License

MIT
