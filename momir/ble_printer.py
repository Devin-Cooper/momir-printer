"""BLE Printer — Phomemo M02S Bluetooth printing via ESC/POS over BLE."""

import asyncio
import struct
from enum import Enum
from PIL import Image

PRINT_WIDTH = 576
BYTES_PER_LINE = PRINT_WIDTH // 8  # 72
MAX_LINES_PER_BLOCK = 255

SERVICE_UUID = "0000ff00-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ff03-0000-1000-8000-00805f9b34fb"

DEVICE_NAMES = ("M02S", "Mr.in_M02")

CMD_INIT = b'\x1b\x40'
CMD_PROP_INIT = b'\x1f\x11\x02\x04'
CMD_CENTER = b'\x1b\x61\x01'
CMD_M02S_PREAMBLE = b'\x1f\x11\x24\x00'
CMD_FEED = b'\x1b\x64\x02'
CMD_FIN_1 = b'\x1f\x11\x08'
CMD_FIN_2 = b'\x1f\x11\x0e'
CMD_FIN_3 = b'\x1f\x11\x07'
CMD_FIN_4 = b'\x1f\x11\x09'


class PrinterState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    READY = "ready"
    PRINTING = "printing"


def pack_image_to_bytes(img: Image.Image) -> bytes:
    assert img.mode == "1"
    assert img.width == PRINT_WIDTH
    result = bytearray()
    for y in range(img.height):
        for x_byte in range(BYTES_PER_LINE):
            byte = 0
            for bit in range(8):
                px = img.getpixel((x_byte * 8 + bit, y))
                if px == 0:
                    byte |= 1 << (7 - bit)
            if byte == 0x0a:
                byte = 0x14
            result.append(byte)
    return bytes(result)


def build_print_commands(img: Image.Image) -> bytes:
    bitmap = pack_image_to_bytes(img)
    commands = bytearray()
    commands.extend(CMD_INIT)
    commands.extend(CMD_PROP_INIT)
    commands.extend(CMD_CENTER)
    commands.extend(CMD_M02S_PREAMBLE)
    total_lines = img.height
    offset = 0
    while offset < total_lines:
        lines = min(MAX_LINES_PER_BLOCK, total_lines - offset)
        commands.extend(b'\x1d\x76\x30\x00')
        commands.extend(struct.pack('<H', BYTES_PER_LINE))
        commands.extend(struct.pack('<H', lines))
        start = offset * BYTES_PER_LINE
        end = start + (lines * BYTES_PER_LINE)
        commands.extend(bitmap[start:end])
        offset += lines
    commands.extend(CMD_FEED)
    commands.extend(CMD_FEED)
    commands.extend(CMD_FIN_1)
    commands.extend(CMD_FIN_2)
    commands.extend(CMD_FIN_3)
    commands.extend(CMD_FIN_4)
    return bytes(commands)


# --- BLE Connection Layer ---

try:
    from bleak import BleakClient, BleakScanner
except ImportError:
    BleakClient = None
    BleakScanner = None

CHUNK_DELAY = 0.05
POST_PRINT_DELAY = 2.0


class BLEPrinter:
    def __init__(self):
        self._client: BleakClient | None = None
        self._state = PrinterState.DISCONNECTED
        self._lock = asyncio.Lock()

    @property
    def state(self) -> PrinterState:
        return self._state

    async def scan(self, timeout: float = 10.0) -> str | None:
        if BleakScanner is None:
            raise RuntimeError("bleak not installed")
        devices = await BleakScanner.discover(timeout=timeout)
        for d in devices:
            if d.name and any(name in d.name for name in DEVICE_NAMES):
                return d.address
        return None

    async def connect(self, address: str | None = None) -> bool:
        if self._state not in (PrinterState.DISCONNECTED,):
            return self._state == PrinterState.READY
        self._state = PrinterState.CONNECTING
        try:
            if address is None:
                address = await self.scan()
                if address is None:
                    self._state = PrinterState.DISCONNECTED
                    return False
            self._client = BleakClient(address)
            await self._client.connect()
            self._state = PrinterState.READY
            return True
        except Exception:
            self._state = PrinterState.DISCONNECTED
            self._client = None
            return False

    async def disconnect(self):
        if self._client and self._client.is_connected:
            await self._client.disconnect()
        self._client = None
        self._state = PrinterState.DISCONNECTED

    async def print_image(self, img: Image.Image) -> bool:
        async with self._lock:
            if self._state != PrinterState.READY:
                if not await self.connect():
                    return False
            self._state = PrinterState.PRINTING
            try:
                commands = build_print_commands(img)
                mtu = (self._client.mtu_size - 3) if self._client else 500
                chunk_size = max(20, mtu)
                for i in range(0, len(commands), chunk_size):
                    chunk = commands[i:i + chunk_size]
                    await self._client.write_gatt_char(WRITE_UUID, chunk, response=False)
                    await asyncio.sleep(CHUNK_DELAY)
                await asyncio.sleep(POST_PRINT_DELAY)
                self._state = PrinterState.READY
                return True
            except Exception:
                self._state = PrinterState.DISCONNECTED
                self._client = None
                return False


def write_dry_run(img: Image.Image, output_path: str):
    commands = build_print_commands(img)
    with open(output_path, "wb") as f:
        f.write(commands)
    return len(commands)


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="BLE Printer CLI")
    parser.add_argument("image", nargs="?", help="Path to a 576px-wide image to print")
    parser.add_argument("--scan-only", action="store_true", help="Just scan for the printer")
    parser.add_argument("--dry-run", metavar="OUTPUT", help="Write commands to file instead of printing")
    args = parser.parse_args()

    async def main():
        if args.scan_only:
            printer = BLEPrinter()
            print("Scanning for M02S printer...")
            addr = await printer.scan()
            if addr:
                print(f"Found printer at: {addr}")
            else:
                print("No printer found.")
            return

        if not args.image:
            print("Provide an image path, or use --scan-only")
            sys.exit(1)

        img = Image.open(args.image)
        if img.width != PRINT_WIDTH:
            img = img.resize((PRINT_WIDTH, int(img.height * PRINT_WIDTH / img.width)))
        if img.mode != "1":
            img = img.convert("1")

        if args.dry_run:
            size = write_dry_run(img, args.dry_run)
            print(f"Wrote {size} bytes to {args.dry_run}")
            return

        printer = BLEPrinter()
        print("Connecting...")
        if not await printer.connect():
            print("Failed to connect.")
            sys.exit(1)
        print(f"Connected. Printing {img.width}x{img.height} image...")
        success = await printer.print_image(img)
        print("Success!" if success else "Print failed.")
        await printer.disconnect()

    asyncio.run(main())
