# Momir Printer

A local app that randomly selects a Magic: The Gathering creature by mana value ([Momir format](https://mtg.fandom.com/wiki/Momir)) and prints it on a Phomemo M02S thermal printer via Bluetooth Low Energy.

## How It Works

1. Pick a mana value (0–16)
2. Roll to get a random creature at that mana value
3. See the full card image preview in your browser
4. Print the card on thermal paper — art + card info in a readable layout

## Hardware

- **Phomemo M02S** thermal printer (576 dots/line, 53mm paper)
- Connects via Bluetooth Low Energy (BLE)
- Pair the printer in macOS Bluetooth settings first (code: `0000` or `1234`)

## Setup

```bash
# Clone and enter the project
cd momir-printer

# Create venv and install
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Install fonts (optional — falls back to system Arial)
brew install --cask font-dejavu
```

### Card Data

Download `AtomicCards.json` from [MTGJSON](https://mtgjson.com/downloads/all-files/) and place it at `~/Downloads/AtomicCards.json`.

## Usage

### Run the Web App

```bash
source .venv/bin/activate
python -m momir.server
```

Open http://localhost:8000 in your browser. Click **Connect** to pair with the printer, pick a mana value, and hit **Roll**.

### Settings

- **Auto-print** — automatically print after each roll
- **Include Un-sets** — include silver-bordered/funny cards in the pool
- **Print Art** — include card artwork on the thermal print (fetched from Scryfall)

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
Browser Frontend (localhost:8000)
  │ REST API
FastAPI Server
  │
  ├── Card Store        AtomicCards.json → indexed by mana value (18,000+ creatures)
  ├── Image Cache       Scryfall card images → disk cache (~/.cache/momir-printer/)
  ├── Thermal Renderer  Card data + art → 576px 1-bit bitmap
  └── BLE Printer       Bitmap → ESC/POS commands → Phomemo M02S via BLE
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

## API Endpoints

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

- **Python** (FastAPI, Pillow, bleak, httpx)
- **MTGJSON** AtomicCards.json for card data
- **Scryfall API** for card images
- **Phomemo M02S** ESC/POS protocol over BLE

## License

MIT
