# Momir Printer

A [Momir format](https://mtg.fandom.com/wiki/Momir) MTG creature printer — pick a mana value, get a random creature, and print it on a thermal printer via Bluetooth.

**Try it now: [momir.io](https://momir.io)** (Chrome/Edge on Android or desktop)

## How It Works

1. Pick a mana value (0–16)
2. Roll to get a random creature at that mana value
3. See the full card image preview in your browser (or hide it for a surprise)
4. Print the card on thermal paper — dithered art + card info in a readable layout

## Supported Printers

Any Phomemo M02-family thermal printer with BLE:

- **M02** (384 dots/line, 48mm paper)
- **M02S** (576 dots/line, 53mm paper)
- **M02 Pro** (576 dots/line, 53mm paper)
- **T02** (384 dots/line, 48mm paper)

Connect via Bluetooth Low Energy. Pair in your OS Bluetooth settings first (code: `0000` or `1234`).

## Web App (momir.io)

The primary version — runs entirely in your browser, no server needed.

**Live at [https://momir.io](https://momir.io)**

### Browser Support

- Chrome/Edge on **Android** and **desktop** (macOS, Windows, Linux)
- **Not supported on iOS** — Web Bluetooth is unavailable on any iOS browser (Apple restriction)

### Settings

- **Auto-print** — automatically print after each roll
- **Include Un-sets** — include silver-bordered/funny cards in the pool
- **Print Art** — include dithered card artwork on the thermal print
- **Hide Preview** — don't show the card on screen before printing (for the surprise factor)

### Run Locally

```bash
# Build the card database (requires AtomicCards.json from MTGJSON)
python scripts/build_creatures.py

# Serve
cd web && python3 -m http.server 8080
```

Open http://localhost:8080 in Chrome.

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

## Thermal Print Layout

```
┌──────────────────────────────┐
│  Card Name            {W}{U} │
├──────────────────────────────┤
│          [Card Art]          │  (when Print Art is enabled)
├──────────────────────────────┤
│  Creature — Type Line        │
├──────────────────────────────┤
│  Rules text, word-wrapped    │
│  to fit the print width.     │
├──────────────────────────────┤
│                        3 / 4 │
└──────────────────────────────┘
```

## API Endpoints (Python version)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/` | Web frontend |
| `POST` | `/roll` | Pick random creature `{mv, include_funny}` |
| `GET` | `/image/{name}` | Card image (cached from Scryfall) |
| `POST` | `/print` | Print the last rolled card |
| `GET` | `/status` | Printer state |
| `POST` | `/connect` | Connect to printer via BLE |
| `GET/POST` | `/settings` | Get/update settings |

## Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

## Tech Stack

- **Web app**: HTML/CSS/JS, Web Bluetooth API, Canvas API
- **Python app**: FastAPI, Pillow, bleak, httpx
- **Card data**: [MTGJSON](https://mtgjson.com) AtomicCards.json (18,000+ creatures)
- **Card images**: [Scryfall API](https://scryfall.com/docs/api)
- **Printer protocol**: Phomemo ESC/POS over BLE (service `FF00`, write `FF02`)

## License

MIT
