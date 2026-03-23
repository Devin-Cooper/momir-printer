import json
import pytest
from momir.card_store import CardStore


class TestCardStoreFromDict:
    """Test CardStore loading from pre-parsed dict (no file I/O)."""

    def test_loads_only_creatures(self, sample_card_data):
        store = CardStore.from_dict(sample_card_data)
        names = {c["name"] for mv_list in store._index.values() for c in mv_list}
        assert "Tarmogoyf" in names
        assert "Grizzly Bears" in names
        assert "Lightning Bolt" not in names  # Not a creature

    def test_indexes_by_mana_value(self, sample_card_data):
        store = CardStore.from_dict(sample_card_data)
        mv2 = store._index[2]
        names = {c["name"] for c in mv2}
        assert "Tarmogoyf" in names
        assert "Grizzly Bears" in names

    def test_includes_funny_creatures(self, sample_card_data):
        store = CardStore.from_dict(sample_card_data)
        mv5 = store._index[5]
        names = {c["name"] for c in mv5}
        assert "\"Brims\" Barone, Midway Mobster" in names

    def test_extracts_required_fields(self, sample_card_data):
        store = CardStore.from_dict(sample_card_data)
        tarmogoyf = next(c for c in store._index[2] if c["name"] == "Tarmogoyf")
        assert tarmogoyf["power"] == "*"
        assert tarmogoyf["toughness"] == "1+*"
        assert tarmogoyf["type"] == "Creature — Lhurgoyf"
        assert "Tarmogoyf's power" in tarmogoyf["text"]
        assert tarmogoyf["manaCost"] == "{1}{G}"
        assert tarmogoyf["isFunny"] is False

    def test_stats(self, sample_card_data):
        store = CardStore.from_dict(sample_card_data)
        stats = store.stats()
        assert stats["total_creatures"] == 3
        assert stats["mv_distribution"][2] == 2  # Tarmogoyf + Grizzly Bears
        assert stats["mv_distribution"][5] == 1  # Brims Barone


class TestGetRandomCreature:

    def test_returns_creature_at_mv(self, sample_card_data):
        store = CardStore.from_dict(sample_card_data)
        creature = store.get_random_creature(2, include_funny=True)
        assert creature["manaValue"] == 2.0
        assert creature["name"] in ("Tarmogoyf", "Grizzly Bears")

    def test_excludes_funny_when_filtered(self, sample_card_data):
        store = CardStore.from_dict(sample_card_data)
        creature = store.get_random_creature(5, include_funny=False)
        assert creature is None

    def test_includes_funny_when_allowed(self, sample_card_data):
        store = CardStore.from_dict(sample_card_data)
        creature = store.get_random_creature(5, include_funny=True)
        assert creature is not None
        assert creature["name"] == "\"Brims\" Barone, Midway Mobster"

    def test_returns_none_for_empty_mv(self, sample_card_data):
        store = CardStore.from_dict(sample_card_data)
        creature = store.get_random_creature(14, include_funny=True)
        assert creature is None

    def test_returns_none_for_negative_mv(self, sample_card_data):
        store = CardStore.from_dict(sample_card_data)
        creature = store.get_random_creature(-1, include_funny=True)
        assert creature is None
