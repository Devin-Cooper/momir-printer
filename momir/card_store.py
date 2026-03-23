"""Card Store — loads AtomicCards.json and indexes creatures by mana value."""

import json
import random
from collections import defaultdict
from pathlib import Path

EXTRACTED_FIELDS = [
    "name", "manaValue", "type", "types", "power", "toughness",
    "text", "manaCost", "supertypes", "subtypes",
]


class CardStore:
    def __init__(self, index: dict[int, list[dict]]):
        self._index = index

    @classmethod
    def from_dict(cls, raw: dict) -> "CardStore":
        """Build index from parsed AtomicCards.json dict."""
        index = defaultdict(list)
        for name, printings in raw["data"].items():
            card = printings[0]
            if "Creature" not in card.get("types", []):
                continue
            extracted = {}
            for field in EXTRACTED_FIELDS:
                extracted[field] = card.get(field, "" if field == "text" else None)
            extracted["isFunny"] = card.get("isFunny", False)
            mv = int(extracted["manaValue"] or 0)
            extracted["manaValue"] = float(mv)
            index[mv].append(extracted)
        return cls(dict(index))

    @classmethod
    def from_file(cls, path: str | Path) -> "CardStore":
        """Load from an AtomicCards.json file on disk."""
        with open(path) as f:
            raw = json.load(f)
        return cls.from_dict(raw)

    def get_random_creature(self, mv: int, include_funny: bool = True) -> dict | None:
        """Pick a random creature at the given mana value. Returns None if empty."""
        bucket = self._index.get(mv, [])
        if not include_funny:
            bucket = [c for c in bucket if not c["isFunny"]]
        if not bucket:
            return None
        return random.choice(bucket)

    def stats(self) -> dict:
        """Return summary statistics about the loaded creature pool."""
        total = sum(len(v) for v in self._index.values())
        mv_dist = {mv: len(cards) for mv, cards in sorted(self._index.items())}
        return {"total_creatures": total, "mv_distribution": mv_dist}


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Card Store CLI — load and query creatures")
    parser.add_argument("--file", default=str(Path.home() / "Downloads" / "AtomicCards.json"),
                        help="Path to AtomicCards.json")
    parser.add_argument("--mv", type=int, help="Pick a random creature at this mana value")
    parser.add_argument("--include-funny", action="store_true", default=False)
    args = parser.parse_args()

    print(f"Loading {args.file}...")
    store = CardStore.from_file(args.file)
    s = store.stats()
    print(f"Loaded {s['total_creatures']} creatures")
    print("MV distribution:")
    for mv, count in s["mv_distribution"].items():
        print(f"  MV {mv}: {count}")

    if args.mv is not None:
        creature = store.get_random_creature(args.mv, include_funny=args.include_funny)
        if creature:
            print(f"\nRandom creature at MV {args.mv}:")
            print(f"  {creature['name']} — {creature['type']}")
            print(f"  {creature.get('power', '?')}/{creature.get('toughness', '?')}")
            print(f"  {creature.get('manaCost', '')}")
            if creature.get("text"):
                print(f"  {creature['text']}")
        else:
            print(f"\nNo creatures at MV {args.mv}")
