"""FastAPI server for the Phomemo Print Dialog."""

import hashlib
import io
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from PIL import Image

from momir.ble_printer import BLEPrinter, PrinterState
from printdialog.renderer import (
    render, load_pdf_page, get_pdf_page_count,
    build_full_commands,
)

printer: BLEPrinter | None = None
_upload_dir = tempfile.mkdtemp(prefix="printdialog_")
_current_file: str | None = None
_current_ext: str | None = None
_page_count: int = 1


@asynccontextmanager
async def lifespan(app: FastAPI):
    global printer
    printer = BLEPrinter()
    yield
    if printer:
        await printer.disconnect()


app = FastAPI(title="Phomemo Print Dialog", lifespan=lifespan)


class PreviewRequest(BaseModel):
    page: int = 0
    scale: int = 100
    fit_to_width: bool = True
    density: int = 4
    dither: str = "floyd-steinberg"
    orientation: str = "auto"
    invert: bool = False
    print_width: int = 576


class PrintRequest(PreviewRequest):
    feed: str = "single"


def _get_source_image(page: int = 0) -> Image.Image:
    if _current_file is None:
        raise HTTPException(status_code=400, detail="No file uploaded")
    if _current_ext == ".pdf":
        return load_pdf_page(_current_file, page)
    return Image.open(_current_file)


@app.get("/")
async def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    global _current_file, _current_ext, _page_count

    if _current_file and Path(_current_file).exists():
        Path(_current_file).unlink()

    ext = Path(file.filename or "").suffix.lower()
    _current_ext = ext
    file_hash = hashlib.md5(file.filename.encode()).hexdigest()[:8]
    dest = Path(_upload_dir) / f"upload_{file_hash}{ext}"

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    _current_file = str(dest)

    if ext == ".pdf":
        _page_count = get_pdf_page_count(_current_file)
    else:
        _page_count = 1

    pages = []
    for i in range(_page_count):
        pages.append({"page": i, "thumbnail_url": f"/thumbnail/{i}"})

    return {"page_count": _page_count, "pages": pages}


@app.get("/thumbnail/{page}")
async def thumbnail(page: int):
    if _current_file is None:
        raise HTTPException(status_code=400, detail="No file uploaded")
    source = _get_source_image(page)
    source.thumbnail((150, 150))
    buf = io.BytesIO()
    source.save(buf, format="PNG")
    buf.seek(0)
    return Response(content=buf.getvalue(), media_type="image/png")


@app.post("/preview")
async def preview(req: PreviewRequest):
    # Note: density is accepted in the request but only affects printer hardware
    # (thermal energy), not the rendered image. It's consumed only by /print.
    source = _get_source_image(req.page)
    img = render(
        source,
        print_width=req.print_width,
        fit_to_width=req.fit_to_width,
        scale=req.scale,
        orientation=req.orientation,
        dither=req.dither,
        invert=req.invert,
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Response(content=buf.getvalue(), media_type="image/png")


@app.post("/print")
async def print_file(req: PrintRequest):
    if _current_file is None:
        raise HTTPException(status_code=400, detail="No file uploaded")
    if printer.state == PrinterState.PRINTING:
        raise HTTPException(status_code=409, detail="Already printing")
    if printer.state != PrinterState.READY:
        raise HTTPException(status_code=400, detail="Printer not connected")

    source = _get_source_image(req.page)
    img = render(
        source,
        print_width=printer.profile.print_width,
        fit_to_width=req.fit_to_width,
        scale=req.scale,
        orientation=req.orientation,
        dither=req.dither,
        invert=req.invert,
    )
    commands = build_full_commands(img, printer.profile, req.density, req.feed)
    success = await printer.send_raw_commands(commands)
    if not success:
        raise HTTPException(status_code=500, detail="Print failed")
    return {"status": "ok"}


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
    return {
        "connected": success,
        "state": printer.state.value,
        "model": printer.device_name,
        "print_width": printer.profile.print_width,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("printdialog.server:app", host="127.0.0.1", port=8001, reload=True)
