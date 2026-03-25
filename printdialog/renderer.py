"""Renderer — converts images/PDFs to 1-bit bitmaps for thermal printing."""

import struct
from PIL import Image, ImageOps

from momir.ble_printer import (
    PrinterProfile, PROFILE_M02S, PROFILE_M04S,
    MAX_LINES_PER_BLOCK, pack_image_to_bytes,
)


def render(
    source: Image.Image,
    print_width: int = 576,
    fit_to_width: bool = True,
    scale: int = 100,
    orientation: str = "auto",
    dither: str = "floyd-steinberg",
    invert: bool = False,
) -> Image.Image:
    img = source.copy()

    # 1. Orientation
    is_landscape = img.width > img.height
    if orientation == "auto":
        if print_width <= 576 and is_landscape:
            img = img.rotate(90, expand=True)
        elif print_width > 576 and not is_landscape:
            img = img.rotate(90, expand=True)
    elif orientation == "portrait" and is_landscape:
        img = img.rotate(90, expand=True)
    elif orientation == "landscape" and not is_landscape:
        img = img.rotate(90, expand=True)

    # 2. Scale
    if fit_to_width:
        ratio = print_width / img.width
        new_h = max(1, int(img.height * ratio))
        img = img.resize((print_width, new_h), Image.LANCZOS)
    else:
        target_w = max(1, int(print_width * scale / 100))
        ratio = target_w / img.width
        new_h = max(1, int(img.height * ratio))
        img = img.resize((target_w, new_h), Image.LANCZOS)

    # 3. Ensure exactly print_width wide (pad or clip)
    if img.width != print_width:
        padded = Image.new("RGB" if img.mode == "RGB" else "L", (print_width, img.height), 255)
        offset_x = (print_width - img.width) // 2
        padded.paste(img, (max(0, offset_x), 0))
        img = padded

    # 4. Grayscale
    if img.mode != "L":
        img = img.convert("L")

    # 5. Invert
    if invert:
        img = ImageOps.invert(img)

    # 6. Dither
    if dither == "threshold":
        img = img.point(lambda x: 0 if x < 128 else 255, "1")
    else:
        img = img.convert("1")

    return img


def load_pdf_page(pdf_path: str, page: int = 0, dpi: int = 300) -> Image.Image:
    import fitz
    doc = fitz.open(pdf_path)
    if page >= len(doc):
        page = 0
    pix = doc[page].get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()
    return img


def get_pdf_page_count(pdf_path: str) -> int:
    import fitz
    doc = fitz.open(pdf_path)
    count = len(doc)
    doc.close()
    return count


def build_init_commands(profile: PrinterProfile, density: int) -> bytes:
    if profile.name == "M04S":
        density = max(1, min(15, density))
        heat = min(255, round(100 + (density - 1) * 50 / 3))
        return (
            b'\x1f\x11\x02' + bytes([density])
            + b'\x1f\x11\x37' + bytes([heat])
            + b'\x1f\x11\x0b'
            + b'\x1f\x11\x35\x00'
        )
    return profile.init_commands


def build_feed_commands(feed: str) -> bytes:
    if feed == "single":
        return b'\x1b\x64\x02'
    elif feed == "double":
        return b'\x1b\x64\x04'
    return b''


def build_raster_commands(img: Image.Image, bytes_per_line: int) -> bytes:
    bitmap = pack_image_to_bytes(img, bytes_per_line)
    commands = bytearray()
    total_lines = img.height
    offset = 0
    while offset < total_lines:
        lines = min(MAX_LINES_PER_BLOCK, total_lines - offset)
        commands.extend(b'\x1d\x76\x30\x00')
        commands.extend(struct.pack('<H', bytes_per_line))
        commands.extend(struct.pack('<H', lines))
        start = offset * bytes_per_line
        end = start + (lines * bytes_per_line)
        commands.extend(bitmap[start:end])
        offset += lines
    return bytes(commands)


def build_full_commands(
    img: Image.Image,
    profile: PrinterProfile,
    density: int = 4,
    feed: str = "single",
) -> bytes:
    init = build_init_commands(profile, density)
    raster = build_raster_commands(img, profile.bytes_per_line)
    feed_cmds = build_feed_commands(feed)
    return init + raster + feed_cmds + profile.finalize_commands
