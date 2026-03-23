"""Thermal Renderer — renders card data to a 576px-wide 1-bit image for the M02S."""

import os
import textwrap
from PIL import Image, ImageDraw, ImageFont

PRINT_WIDTH = 576
PADDING = 12
CONTENT_WIDTH = PRINT_WIDTH - (PADDING * 2)
RULE_HEIGHT = 1

# Font search paths — DejaVu Sans preferred (spec requirement), Arial as fallback
_BOLD_FONTS = [
    os.path.expanduser("~/Library/Fonts/DejaVuSans-Bold.ttf"),  # brew --cask font-dejavu
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",     # Linux
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",         # macOS fallback
]
_REGULAR_FONTS = [
    os.path.expanduser("~/Library/Fonts/DejaVuSans.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


def _find_font(bold: bool = False) -> str | None:
    candidates = _BOLD_FONTS if bold else _REGULAR_FONTS
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = _find_font(bold)
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines = []
    current_line = ""
    for word in words:
        test = f"{current_line} {word}".strip()
        bbox = font.getbbox(test)
        if bbox[2] <= max_width:
            current_line = test
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines or [""]


def render_card(card: dict) -> Image.Image:
    name_font = _load_font(28, bold=True)
    type_font = _load_font(20, bold=False)
    text_font = _load_font(18, bold=False)
    pt_font = _load_font(26, bold=True)

    y = PADDING
    name_str = card["name"]
    mana_str = card.get("manaCost", "")
    name_height = name_font.getbbox("Ay")[3] - name_font.getbbox("Ay")[1]
    y += name_height + 8
    y += RULE_HEIGHT + 6

    type_str = card.get("type", "")
    type_height = type_font.getbbox("Ay")[3] - type_font.getbbox("Ay")[1]
    y += type_height + 6
    y += RULE_HEIGHT + 6

    rules_text = card.get("text", "")
    rules_lines = []
    if rules_text:
        for paragraph in rules_text.split("\n"):
            rules_lines.extend(_wrap_text(paragraph, text_font, CONTENT_WIDTH))
        text_line_height = text_font.getbbox("Ay")[3] - text_font.getbbox("Ay")[1]
        y += (text_line_height + 4) * len(rules_lines) + 6
        y += RULE_HEIGHT + 6

    power = card.get("power", "")
    toughness = card.get("toughness", "")
    if power and toughness:
        pt_str = f"{power} / {toughness}"
        pt_height = pt_font.getbbox("Ay")[3] - pt_font.getbbox("Ay")[1]
        y += pt_height + 8

    y += PADDING
    total_height = y

    img = Image.new("L", (PRINT_WIDTH, total_height), 255)
    draw = ImageDraw.Draw(img)
    y = PADDING

    if mana_str:
        mana_bbox = name_font.getbbox(mana_str)
        mana_w = mana_bbox[2] - mana_bbox[0]
        draw.text((PRINT_WIDTH - PADDING - mana_w, y), mana_str, font=name_font, fill=0)
        max_name_w = CONTENT_WIDTH - mana_w - 12
        display_name = name_str
        while name_font.getbbox(display_name)[2] > max_name_w and len(display_name) > 1:
            display_name = display_name[:-1]
        draw.text((PADDING, y), display_name, font=name_font, fill=0)
    else:
        draw.text((PADDING, y), name_str, font=name_font, fill=0)
    y += name_height + 8

    draw.line([(PADDING, y), (PRINT_WIDTH - PADDING, y)], fill=0, width=RULE_HEIGHT)
    y += RULE_HEIGHT + 6

    draw.text((PADDING, y), type_str, font=type_font, fill=0)
    y += type_height + 6

    draw.line([(PADDING, y), (PRINT_WIDTH - PADDING, y)], fill=0, width=RULE_HEIGHT)
    y += RULE_HEIGHT + 6

    if rules_lines:
        text_line_height = text_font.getbbox("Ay")[3] - text_font.getbbox("Ay")[1]
        for line in rules_lines:
            draw.text((PADDING, y), line, font=text_font, fill=0)
            y += text_line_height + 4
        y += 6
        draw.line([(PADDING, y), (PRINT_WIDTH - PADDING, y)], fill=0, width=RULE_HEIGHT)
        y += RULE_HEIGHT + 6

    if power and toughness:
        pt_str = f"{power} / {toughness}"
        pt_bbox = pt_font.getbbox(pt_str)
        pt_w = pt_bbox[2] - pt_bbox[0]
        draw.text((PRINT_WIDTH - PADDING - pt_w, y), pt_str, font=pt_font, fill=0)

    return img.convert("1")


if __name__ == "__main__":
    import argparse
    import json
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Thermal Renderer CLI")
    parser.add_argument("--card", help="Card name to render (requires --file)")
    parser.add_argument("--mv", type=int, help="Render a random creature at this MV (requires --file)")
    parser.add_argument("--file", default=str(Path.home() / "Downloads" / "AtomicCards.json"),
                        help="Path to AtomicCards.json")
    parser.add_argument("--output", default="debug_output.png", help="Output PNG path")
    args = parser.parse_args()

    if args.card or args.mv is not None:
        from momir.card_store import CardStore
        store = CardStore.from_file(args.file)
        if args.card:
            creature = None
            for mv_list in store._index.values():
                for c in mv_list:
                    if c["name"].lower() == args.card.lower():
                        creature = c
                        break
                if creature:
                    break
            if not creature:
                print(f"Card not found: {args.card}")
                sys.exit(1)
        else:
            creature = store.get_random_creature(args.mv, include_funny=True)
            if not creature:
                print(f"No creatures at MV {args.mv}")
                sys.exit(1)
    else:
        creature = {
            "name": "Tarmogoyf",
            "manaValue": 2.0,
            "type": "Creature — Lhurgoyf",
            "power": "*",
            "toughness": "1+*",
            "text": "Tarmogoyf's power is equal to the number of card types among cards in all graveyards and its toughness is equal to that number plus 1.",
            "manaCost": "{1}{G}",
        }

    print(f"Rendering: {creature['name']}")
    img = render_card(creature)
    img.save(args.output)
    print(f"Saved {img.width}x{img.height} 1-bit image to {args.output}")
