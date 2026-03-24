"""Build creatures.json from AtomicCards.json for the web app."""

import argparse
import json
from collections import defaultdict
from pathlib import Path


def build_creatures(input_path: str, output_path: str) -> dict:
    """Read AtomicCards.json, extract creatures, write minified JSON."""
    with open(input_path) as f:
        raw = json.load(f)

    creatures = defaultdict(list)
    for name, printings in raw["data"].items():
        card = printings[0]
        if "Creature" not in card.get("types", []):
            continue
        mv = int(card.get("manaValue", 0))
        creatures[mv].append({
            "n": card["name"],
            "t": card.get("type", ""),
            "p": card.get("power", ""),
            "h": card.get("toughness", ""),
            "x": card.get("text", ""),
            "m": card.get("manaCost", ""),
            "f": card.get("isFunny", False),
        })

    output = {str(mv): cards for mv, cards in sorted(creatures.items())}

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, separators=(",", ":"), ensure_ascii=False)

    total = sum(len(v) for v in output.values())
    file_size = Path(output_path).stat().st_size
    mv_dist = {mv: len(cards) for mv, cards in sorted(creatures.items())}

    return {"total": total, "file_size": file_size, "mv_distribution": mv_dist}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build creatures.json for the web app")
    parser.add_argument("--input", default=str(Path.home() / "Downloads" / "AtomicCards.json"),
                        help="Path to AtomicCards.json")
    parser.add_argument("--output", default=str(Path(__file__).resolve().parent.parent / "web" / "creatures.json"),
                        help="Output path for creatures.json")
    args = parser.parse_args()

    print(f"Reading {args.input}...")
    stats = build_creatures(args.input, args.output)
    print(f"Wrote {stats['total']} creatures to {args.output}")
    print(f"File size: {stats['file_size']:,} bytes ({stats['file_size']/1024/1024:.1f} MB)")
    print("MV distribution:")
    for mv, count in stats["mv_distribution"].items():
        print(f"  MV {mv}: {count}")
