"""Image Cache — fetches and caches Scryfall card images."""

import os
import re
from pathlib import Path
from urllib.parse import quote

import httpx

SCRYFALL_NAMED_URL = "https://api.scryfall.com/cards/named"
USER_AGENT = "MomirPrinter/0.1 (thermal printer app)"
DEFAULT_CACHE_DIR = str(Path.home() / ".cache" / "momir-printer" / "images")


def _sanitize_filename(name: str) -> str:
    if not name:
        return "_"
    sanitized = re.sub(r'[^\w\s-]', '', name)
    sanitized = re.sub(r'\s+', '_', sanitized.strip())
    return sanitized or "_"


class ImageCache:
    def __init__(self, cache_dir: str = DEFAULT_CACHE_DIR):
        self._cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _cache_path(self, card_name: str) -> str:
        return os.path.join(self._cache_dir, _sanitize_filename(card_name) + ".jpg")

    async def get_image(self, card_name: str) -> bytes | None:
        path = self._cache_path(card_name)

        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    SCRYFALL_NAMED_URL,
                    params={"exact": card_name, "format": "image", "version": "normal"},
                    headers={"User-Agent": USER_AGENT},
                    follow_redirects=True,
                    timeout=15.0,
                )
                resp.raise_for_status()
                with open(path, "wb") as f:
                    f.write(resp.content)
                return resp.content
        except Exception:
            return None


if __name__ == "__main__":
    import asyncio
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m momir.image_cache <card name>")
        sys.exit(1)

    card_name = " ".join(sys.argv[1:])

    async def main():
        cache = ImageCache()
        print(f"Fetching image for: {card_name}")
        data = await cache.get_image(card_name)
        if data:
            path = cache._cache_path(card_name)
            print(f"Image cached at: {path} ({len(data)} bytes)")
        else:
            print("Failed to fetch image.")

    asyncio.run(main())
