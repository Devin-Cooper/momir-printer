"""BLE print tuning script — test different chunk/burst/delay parameters.

Connects to the printer, sends test images with various settings,
and reports timing. Also monitors printer notifications (FF03) to
understand buffer state and flow control.

Usage:
    python scripts/tune_ble.py --scan              # Find printers
    python scripts/tune_ble.py --test-notifications # Monitor FF03 during a print
    python scripts/tune_ble.py --sweep              # Test parameter grid
    python scripts/tune_ble.py --custom 512 5 30    # chunk_size bursts_per_batch delay_ms
"""

import asyncio
import struct
import sys
import time
from pathlib import Path

from bleak import BleakClient, BleakScanner
from PIL import Image

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from momir.ble_printer import (
    SERVICE_UUID, WRITE_UUID, NOTIFY_UUID, DEVICE_NAMES,
    MAX_LINES_PER_BLOCK, PROFILE_M04S, PROFILE_M02S,
    detect_profile, build_print_commands,
)
from momir.thermal_renderer import render_card

SAMPLE_CARD = {
    "name": "Tarmogoyf",
    "manaValue": 2.0,
    "type": "Creature — Lhurgoyf",
    "power": "*",
    "toughness": "1+*",
    "text": "Tarmogoyf's power is equal to the number of card types among cards in all graveyards and its toughness is equal to that number plus 1.",
    "manaCost": "{1}{G}",
}


def generate_test_image(profile, pattern="card"):
    """Generate a test image for the given printer profile."""
    if pattern == "card":
        img = render_card(SAMPLE_CARD, print_width=576)
        # Rotate and pad for wide printers
        if profile.print_width > 576:
            img = img.rotate(90, expand=True)
            padded = Image.new("1", (profile.print_width, img.height), 1)
            padded.paste(img, (0, 0))
            return padded
        return img
    elif pattern == "black":
        return Image.new("1", (profile.print_width, 200), 0)
    elif pattern == "stripes":
        img = Image.new("1", (profile.print_width, 200), 1)
        for y in range(200):
            if y % 4 < 2:
                for x in range(profile.print_width):
                    img.putpixel((x, y), 0)
        return img


async def scan_printers():
    """Scan and list all Phomemo printers."""
    print("Scanning for 10 seconds...")
    devices = await BleakScanner.discover(timeout=10)
    found = []
    for d in devices:
        if d.name and any(name in d.name for name in DEVICE_NAMES):
            profile = detect_profile(d.name)
            print(f"  {d.name} -> {d.address} ({profile.name}, {profile.print_width} dots)")
            found.append((d.address, d.name))
    if not found:
        print("  No printers found.")
    return found


async def connect_printer():
    """Connect to the first available printer."""
    devices = await BleakScanner.discover(timeout=10)
    for d in devices:
        if d.name and any(name in d.name for name in DEVICE_NAMES):
            print(f"Connecting to {d.name} ({d.address})...")
            client = BleakClient(d.address)
            await client.connect()
            profile = detect_profile(d.name)
            print(f"Connected! Profile: {profile.name} ({profile.print_width} dots)")
            print(f"MTU: {client.mtu_size}")
            return client, profile, d.name
    print("No printer found.")
    return None, None, None


async def test_notifications(client, profile):
    """Print a card while monitoring FF03 notifications."""
    notifications = []

    def on_notify(sender, data):
        t = time.monotonic()
        notifications.append((t, list(data)))
        print(f"  [{t:.3f}] Notification: {list(data)}")

    print("\nSubscribing to notifications on FF03...")
    try:
        await client.start_notify(NOTIFY_UUID, on_notify)
    except Exception as e:
        print(f"  Could not subscribe to notifications: {e}")
        print("  (This is normal if the device isn't paired at OS level)")

    print("Generating test card...")
    img = generate_test_image(profile, "card")
    commands = build_print_commands(img, profile)
    print(f"Image: {img.width}x{img.height}, commands: {len(commands):,} bytes")

    print("\nSending with current settings (512 bytes, 3/burst, 50ms)...")
    chunk_size = 512
    burst = 3
    delay = 0.05

    t_start = time.monotonic()
    chunks = [commands[i:i + chunk_size] for i in range(0, len(commands), chunk_size)]
    for i, chunk in enumerate(chunks):
        await client.write_gatt_char(WRITE_UUID, chunk, response=False)
        if (i + 1) % burst == 0:
            await asyncio.sleep(delay)

    t_send_done = time.monotonic()
    print(f"\nAll data sent in {t_send_done - t_start:.2f}s")

    # Wait for print to finish, monitoring notifications
    print("Waiting 5s for print to complete and notifications...")
    await asyncio.sleep(5)
    t_end = time.monotonic()

    try:
        await client.stop_notify(NOTIFY_UUID)
    except Exception:
        pass

    print(f"\nTotal time: {t_end - t_start:.2f}s")
    print(f"Notifications received: {len(notifications)}")
    for t, data in notifications:
        print(f"  [{t - t_start:.3f}s] {data}")

    return notifications


async def send_with_params(client, commands, chunk_size, burst, delay_ms):
    """Send print commands with specific parameters, return timing info."""
    delay = delay_ms / 1000.0
    chunks = [commands[i:i + chunk_size] for i in range(0, len(commands), chunk_size)]
    total_chunks = len(chunks)

    t_start = time.monotonic()
    for i, chunk in enumerate(chunks):
        await client.write_gatt_char(WRITE_UUID, chunk, response=False)
        if (i + 1) % burst == 0:
            await asyncio.sleep(delay)
    t_send = time.monotonic() - t_start

    # Wait for print to finish
    await asyncio.sleep(3)
    t_total = time.monotonic() - t_start

    throughput = len(commands) / t_send if t_send > 0 else 0
    return {
        "chunk_size": chunk_size,
        "burst": burst,
        "delay_ms": delay_ms,
        "total_chunks": total_chunks,
        "send_time": t_send,
        "total_time": t_total,
        "throughput_kbps": throughput / 1024,
        "data_size": len(commands),
    }


async def sweep_parameters(client, profile):
    """Test a grid of parameters and report results."""
    img = generate_test_image(profile, "card")
    commands = build_print_commands(img, profile)
    print(f"Test image: {img.width}x{img.height}")
    print(f"Data size: {len(commands):,} bytes")

    # Parameter grid
    configs = [
        # (chunk_size, chunks_per_burst, delay_ms)
        (256, 1, 50),   # conservative baseline
        (512, 1, 50),   # current M02S default
        (512, 2, 50),   # current M02S setting
        (512, 3, 50),   # current M04S setting
        (512, 5, 50),   # more aggressive burst
        (512, 3, 30),   # shorter delay
        (512, 5, 30),   # aggressive burst + short delay
        (512, 8, 50),   # large burst
        (512, 10, 40),  # very large burst
        (1024, 3, 50),  # bigger chunks
        (1024, 5, 30),  # bigger chunks + aggressive
    ]

    print(f"\nTesting {len(configs)} configurations...")
    print(f"{'Config':>30s}  {'Send':>6s}  {'Total':>6s}  {'KB/s':>7s}")
    print("-" * 60)

    results = []
    for chunk_size, burst, delay_ms in configs:
        label = f"{chunk_size}B x{burst} @{delay_ms}ms"
        print(f"\n  Printing with {label}...")

        # Small pause between tests for printer to reset
        await asyncio.sleep(2)

        result = await send_with_params(client, commands, chunk_size, burst, delay_ms)
        results.append(result)

        print(f"  {label:>30s}  {result['send_time']:5.2f}s  {result['total_time']:5.2f}s  {result['throughput_kbps']:6.1f}")

    print("\n" + "=" * 60)
    print("RESULTS (sorted by send time):")
    print(f"{'Config':>30s}  {'Send':>6s}  {'KB/s':>7s}")
    print("-" * 50)
    for r in sorted(results, key=lambda x: x["send_time"]):
        label = f"{r['chunk_size']}B x{r['burst']} @{r['delay_ms']}ms"
        print(f"  {label:>30s}  {r['send_time']:5.2f}s  {r['throughput_kbps']:6.1f}")

    return results


async def custom_print(client, profile, chunk_size, burst, delay_ms):
    """Print a test card with custom parameters."""
    img = generate_test_image(profile, "card")
    commands = build_print_commands(img, profile)
    print(f"Image: {img.width}x{img.height}, data: {len(commands):,} bytes")
    print(f"Settings: {chunk_size}B chunks, {burst}/burst, {delay_ms}ms delay")

    result = await send_with_params(client, commands, chunk_size, burst, delay_ms)
    print(f"Send time: {result['send_time']:.2f}s")
    print(f"Throughput: {result['throughput_kbps']:.1f} KB/s")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="BLE print tuning")
    parser.add_argument("--scan", action="store_true", help="Scan for printers")
    parser.add_argument("--test-notifications", action="store_true",
                        help="Print while monitoring FF03 notifications")
    parser.add_argument("--sweep", action="store_true",
                        help="Test parameter grid")
    parser.add_argument("--custom", nargs=3, type=int, metavar=("CHUNK", "BURST", "DELAY_MS"),
                        help="Print with custom params: chunk_size burst delay_ms")
    args = parser.parse_args()

    if args.scan:
        await scan_printers()
        return

    client, profile, name = await connect_printer()
    if not client:
        return

    try:
        if args.test_notifications:
            await test_notifications(client, profile)
        elif args.sweep:
            await sweep_parameters(client, profile)
        elif args.custom:
            await custom_print(client, profile, *args.custom)
        else:
            parser.print_help()
    finally:
        await client.disconnect()
        print("\nDisconnected.")


if __name__ == "__main__":
    asyncio.run(main())
