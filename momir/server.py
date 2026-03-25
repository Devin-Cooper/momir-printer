"""FastAPI server — REST API for Momir Thermal Printer."""

import asyncio
import io
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel

from momir.card_store import CardStore
from momir.image_cache import ImageCache
from momir.thermal_renderer import render_card
from momir.ble_printer import BLEPrinter, PrinterState

card_store: CardStore | None = None
image_cache: ImageCache | None = None
printer: BLEPrinter | None = None
last_rolled_card: dict | None = None

_settings = {
    "include_funny": False,
    "auto_print": False,
    "print_art": True,
    "hide_preview": False,
}

CARDS_JSON_PATH = str(Path.home() / "Downloads" / "AtomicCards.json")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global card_store, image_cache, printer
    print("Loading card database...")
    card_store = CardStore.from_file(CARDS_JSON_PATH)
    stats = card_store.stats()
    print(f"Loaded {stats['total_creatures']} creatures")
    image_cache = ImageCache()
    printer = BLEPrinter()
    yield
    if printer:
        await printer.disconnect()


app = FastAPI(title="Momir Thermal Printer", lifespan=lifespan)


class RollRequest(BaseModel):
    mv: int
    include_funny: bool = False


class SettingsUpdate(BaseModel):
    include_funny: bool | None = None
    auto_print: bool | None = None
    print_art: bool | None = None
    hide_preview: bool | None = None


@app.post("/roll")
async def roll(req: RollRequest):
    global last_rolled_card
    creature = card_store.get_random_creature(req.mv, include_funny=req.include_funny)
    if creature is None:
        raise HTTPException(status_code=404, detail=f"No creatures at mana value {req.mv}")
    last_rolled_card = creature
    return {
        "name": creature["name"],
        "type": creature.get("type", ""),
        "power": creature.get("power", ""),
        "toughness": creature.get("toughness", ""),
        "text": creature.get("text", ""),
        "manaCost": creature.get("manaCost", ""),
        "manaValue": creature.get("manaValue", 0),
        "image_url": f"/image/{quote(creature['name'], safe='')}",
    }


@app.get("/image/{card_name:path}")
async def get_image(card_name: str):
    data = await image_cache.get_image(card_name)
    if data is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(content=data, media_type="image/jpeg")


@app.post("/print")
async def print_card():
    if last_rolled_card is None:
        raise HTTPException(status_code=400, detail="No card rolled yet")
    if printer is None:
        raise HTTPException(status_code=503, detail="Server not ready")
    if printer.state == PrinterState.PRINTING:
        raise HTTPException(status_code=409, detail="Already printing")
    if printer.state != PrinterState.READY:
        raise HTTPException(status_code=400, detail="Printer not connected")
    # Fetch art crop for the thermal print if enabled
    art = None
    if _settings["print_art"]:
        art_bytes = await image_cache.get_image(last_rolled_card["name"], version="art_crop")
        if art_bytes:
            art = Image.open(io.BytesIO(art_bytes))
    img = render_card(last_rolled_card, art_image=art, print_width=printer.profile.print_width)
    success = await printer.print_image(img)
    if not success:
        raise HTTPException(status_code=500, detail="Print failed — check printer connection")
    return {"status": "ok", "card": last_rolled_card["name"]}


@app.get("/status")
async def status():
    if printer is None:
        return {"state": "disconnected", "model": None, "print_width": None}
    return {
        "state": printer.state.value,
        "model": printer.device_name if printer.state == PrinterState.READY else None,
        "print_width": printer.profile.print_width if printer.state == PrinterState.READY else None,
    }


@app.post("/connect")
async def connect():
    if printer is None:
        raise HTTPException(status_code=503, detail="Server not ready")
    if printer.state == PrinterState.CONNECTING:
        return {"connected": False, "state": "connecting"}
    success = await printer.connect()
    return {"connected": success, "state": printer.state.value}


@app.get("/settings")
async def get_settings():
    return _settings.copy()


@app.post("/settings")
async def update_settings(update: SettingsUpdate):
    if update.include_funny is not None:
        _settings["include_funny"] = update.include_funny
    if update.auto_print is not None:
        _settings["auto_print"] = update.auto_print
    if update.print_art is not None:
        _settings["print_art"] = update.print_art
    if update.hide_preview is not None:
        _settings["hide_preview"] = update.hide_preview
    return _settings.copy()


STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("momir.server:app", host="127.0.0.1", port=8000, reload=True)
