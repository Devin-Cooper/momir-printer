"""BLE Printer — Phomemo thermal printer family via ESC/POS over BLE."""

import asyncio
import struct
from enum import Enum
from PIL import Image

# BLE UUIDs (shared across all Phomemo models)
SERVICE_UUID = "0000ff00-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ff03-0000-1000-8000-00805f9b34fb"

MAX_LINES_PER_BLOCK = 255

# Device name patterns for BLE scanning
DEVICE_NAMES = ("M04S", "M04AS", "M02S", "M02 Pro", "M02", "T02", "Mr.in_")

# ESC/POS commands shared across models
CMD_FEED = b'\x1b\x64\x02'


# --- Printer Profiles ---

class PrinterProfile:
    def __init__(self, name, print_width, init_commands, finalize_commands,
                 chunk_size=512, chunks_per_burst=1, burst_delay=0.05):
        self.name = name
        self.print_width = print_width
        self.bytes_per_line = print_width // 8
        self.init_commands = init_commands
        self.finalize_commands = finalize_commands
        self.chunk_size = chunk_size
        self.chunks_per_burst = chunks_per_burst
        self.burst_delay = burst_delay


PROFILE_M02 = PrinterProfile(
    name="M02",
    print_width=384,
    init_commands=b'\x1b\x40\x1f\x11\x02\x04\x1b\x61\x01\x1f\x11\x24\x00',
    finalize_commands=b'\x1b\x64\x02\x1b\x64\x02\x1f\x11\x08\x1f\x11\x0e\x1f\x11\x07\x1f\x11\x09',
)

PROFILE_M02S = PrinterProfile(
    name="M02S",
    print_width=576,
    init_commands=b'\x1b\x40\x1f\x11\x02\x04\x1b\x61\x01\x1f\x11\x24\x00',
    finalize_commands=b'\x1b\x64\x02\x1b\x64\x02\x1f\x11\x08\x1f\x11\x0e\x1f\x11\x07\x1f\x11\x09',
    chunks_per_burst=2,
)

PROFILE_M04S = PrinterProfile(
    name="M04S",
    print_width=1232,
    init_commands=(
        b'\x1f\x11\x02\x04'  # density = 4 (normal)
        b'\x1f\x11\x37\x96'  # heat/speed = 150 (matches density=4)
        b'\x1f\x11\x0b'      # continuous media mode
        b'\x1f\x11\x35\x00'  # compression = raw
    ),
    finalize_commands=b'\x1b\x64\x02',  # single feed
    chunk_size=205,           # confirmed by BTSnoop — must be ≤244 (MTU-3)
    chunks_per_burst=3,       # confirmed by BTSnoop
    burst_delay=0.05,         # 50ms between bursts
)

DEFAULT_PROFILE = PROFILE_M02S


def detect_profile(device_name: str) -> PrinterProfile:
    """Detect printer profile from BLE device name."""
    name = device_name.upper() if device_name else ""
    if "M04" in name:
        return PROFILE_M04S
    if "M02S" in name or "M02 PRO" in name:
        return PROFILE_M02S
    if "T02" in name or "M02" in name:
        return PROFILE_M02
    return DEFAULT_PROFILE


class PrinterState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    READY = "ready"
    PRINTING = "printing"


def pack_image_to_bytes(img: Image.Image, bytes_per_line: int) -> bytes:
    """Pack a 1-bit image into printer bytes. Width must match bytes_per_line * 8."""
    assert img.mode == "1"
    assert img.width == bytes_per_line * 8

    result = bytearray()
    for y in range(img.height):
        for x_byte in range(bytes_per_line):
            byte = 0
            for bit in range(8):
                px = img.getpixel((x_byte * 8 + bit, y))
                if px == 0:
                    byte |= 1 << (7 - bit)
            if byte == 0x0a:
                byte = 0x14
            result.append(byte)
    return bytes(result)


def build_print_commands(img: Image.Image, profile: PrinterProfile | None = None) -> bytes:
    """Build ESC/POS commands for the given printer profile."""
    if profile is None:
        profile = DEFAULT_PROFILE

    bitmap = pack_image_to_bytes(img, profile.bytes_per_line)
    commands = bytearray()

    commands.extend(profile.init_commands)

    total_lines = img.height
    offset = 0
    while offset < total_lines:
        lines = min(MAX_LINES_PER_BLOCK, total_lines - offset)
        commands.extend(b'\x1d\x76\x30\x00')
        commands.extend(struct.pack('<H', profile.bytes_per_line))
        commands.extend(struct.pack('<H', lines))
        start = offset * profile.bytes_per_line
        end = start + (lines * profile.bytes_per_line)
        commands.extend(bitmap[start:end])
        offset += lines

    commands.extend(profile.finalize_commands)

    return bytes(commands)


# --- BLE Connection Layer ---

try:
    from bleak import BleakClient, BleakScanner
except ImportError:
    BleakClient = None
    BleakScanner = None

POST_PRINT_DELAY = 2.0


class BLEPrinter:
    def __init__(self):
        self._client: BleakClient | None = None
        self._state = PrinterState.DISCONNECTED
        self._lock = asyncio.Lock()
        self._profile = DEFAULT_PROFILE
        self._device_name: str | None = None

    @property
    def state(self) -> PrinterState:
        return self._state

    @property
    def profile(self) -> PrinterProfile:
        return self._profile

    @property
    def device_name(self) -> str | None:
        return self._device_name

    def _on_disconnect(self, client) -> None:
        """Callback fired by bleak when BLE link drops."""
        self._state = PrinterState.DISCONNECTED
        self._client = None

    async def _cleanup_client(self):
        """Best-effort disconnect and cleanup of the BLE client."""
        client = self._client
        self._client = None
        if client is not None:
            try:
                if client.is_connected:
                    await client.disconnect()
            except Exception:
                pass

    async def scan(self, timeout: float = 10.0) -> tuple[str, str] | None:
        """Scan for printer. Returns (address, name) or None."""
        if BleakScanner is None:
            raise RuntimeError("bleak not installed")
        devices = await BleakScanner.discover(timeout=timeout)
        for d in devices:
            if d.name and any(name in d.name for name in DEVICE_NAMES):
                return (d.address, d.name)
        return None

    async def _connect_locked(self, address: str | None = None) -> bool:
        """Internal connect — caller must hold self._lock."""
        # Check for stale READY state
        if self._state == PrinterState.READY:
            if self._client and self._client.is_connected:
                return True
            # Stale — fall through to reconnect
            self._state = PrinterState.DISCONNECTED
            self._client = None
        if self._state == PrinterState.CONNECTING:
            return False
        if self._state == PrinterState.PRINTING:
            return False
        if self._state != PrinterState.DISCONNECTED:
            return False

        self._state = PrinterState.CONNECTING
        try:
            if address is None:
                result = await self.scan()
                if result is None:
                    self._state = PrinterState.DISCONNECTED
                    return False
                address, self._device_name = result
            self._profile = detect_profile(self._device_name or "")
            self._client = BleakClient(address, disconnected_callback=self._on_disconnect)
            await self._client.connect()
            self._state = PrinterState.READY
            return True
        except Exception:
            self._state = PrinterState.DISCONNECTED
            await self._cleanup_client()
            return False

    async def connect(self, address: str | None = None) -> bool:
        """Connect to the printer. Thread-safe — acquires lock."""
        async with self._lock:
            return await self._connect_locked(address)

    async def disconnect(self):
        """Disconnect from the printer. Thread-safe — acquires lock."""
        async with self._lock:
            await self._cleanup_client()
            self._state = PrinterState.DISCONNECTED

    async def _send_chunks(self, commands: bytes) -> None:
        """Send command bytes in chunks with burst pacing. Caller must hold lock."""
        chunk_size = self._profile.chunk_size
        burst = self._profile.chunks_per_burst
        delay = self._profile.burst_delay
        chunks = [commands[i:i + chunk_size] for i in range(0, len(commands), chunk_size)]
        for i, chunk in enumerate(chunks):
            await self._client.write_gatt_char(WRITE_UUID, chunk, response=False)
            if (i + 1) % burst == 0:
                await asyncio.sleep(delay)
        await asyncio.sleep(POST_PRINT_DELAY)

    async def print_image(self, img: Image.Image) -> bool:
        async with self._lock:
            if self._state != PrinterState.READY:
                if not await self._connect_locked():
                    return False
            self._state = PrinterState.PRINTING
            try:
                # Ensure 1-bit mode before any transforms
                if img.mode != "1":
                    img = img.convert("1")
                # For wide printers, rotate landscape and center
                if self._profile.print_width > 576:
                    img = img.rotate(90, expand=True)
                    padded = Image.new("1", (self._profile.print_width, img.height), 1)
                    offset_x = (self._profile.print_width - img.width) // 2
                    padded.paste(img, (offset_x, 0))
                    img = padded
                elif img.width != self._profile.print_width:
                    ratio = img.height / img.width
                    img = img.resize((self._profile.print_width, int(self._profile.print_width * ratio)))
                    if img.mode != "1":
                        img = img.convert("1")

                commands = build_print_commands(img, self._profile)
                await self._send_chunks(commands)
                self._state = PrinterState.READY
                return True
            except Exception:
                await self._cleanup_client()
                self._state = PrinterState.DISCONNECTED
                return False
            finally:
                if self._state == PrinterState.PRINTING:
                    self._state = PrinterState.DISCONNECTED

    async def send_raw_commands(self, commands: bytes) -> bool:
        """Send pre-built command bytes via BLE with chunk/burst pacing."""
        async with self._lock:
            if self._state != PrinterState.READY:
                if not await self._connect_locked():
                    return False
            self._state = PrinterState.PRINTING
            try:
                await self._send_chunks(commands)
                self._state = PrinterState.READY
                return True
            except Exception:
                await self._cleanup_client()
                self._state = PrinterState.DISCONNECTED
                return False
            finally:
                if self._state == PrinterState.PRINTING:
                    self._state = PrinterState.DISCONNECTED


def write_dry_run(img: Image.Image, output_path: str, profile: PrinterProfile | None = None):
    commands = build_print_commands(img, profile)
    with open(output_path, "wb") as f:
        f.write(commands)
    return len(commands)


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="BLE Printer CLI")
    parser.add_argument("image", nargs="?", help="Path to image to print")
    parser.add_argument("--scan-only", action="store_true", help="Just scan for printers")
    parser.add_argument("--dry-run", metavar="OUTPUT", help="Write commands to file instead of printing")
    args = parser.parse_args()

    async def main():
        if args.scan_only:
            printer = BLEPrinter()
            print("Scanning for Phomemo printers...")
            result = await printer.scan()
            if result:
                addr, name = result
                profile = detect_profile(name)
                print(f"Found: {name} at {addr} ({profile.print_width} dots/line)")
            else:
                print("No printer found.")
            return

        if not args.image:
            print("Provide an image path, or use --scan-only")
            sys.exit(1)

        img = Image.open(args.image)
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
        print(f"Connected to {printer._device_name} ({printer.profile.name}, {printer.profile.print_width} dots/line)")
        print(f"Printing {img.width}x{img.height} image...")
        success = await printer.print_image(img)
        print("Success!" if success else "Print failed.")
        await printer.disconnect()

    asyncio.run(main())
