import pytest


SAMPLE_CREATURE = {
    "name": "Tarmogoyf",
    "manaValue": 2.0,
    "type": "Creature — Lhurgoyf",
    "types": ["Creature"],
    "power": "*",
    "toughness": "1+*",
    "text": "Tarmogoyf's power is equal to the number of card types among cards in all graveyards and its toughness is equal to that number plus 1.",
    "manaCost": "{1}{G}",
    "supertypes": [],
    "subtypes": ["Lhurgoyf"],
    "isFunny": False,
}

VANILLA_CREATURE = {
    "name": "Grizzly Bears",
    "manaValue": 2.0,
    "type": "Creature — Bear",
    "types": ["Creature"],
    "power": "2",
    "toughness": "2",
    "text": "",
    "manaCost": "{1}{G}",
    "supertypes": [],
    "subtypes": ["Bear"],
    "isFunny": False,
}

FUNNY_CREATURE = {
    "name": "\"Brims\" Barone, Midway Mobster",
    "manaValue": 5.0,
    "type": "Legendary Creature — Human Rogue",
    "types": ["Creature"],
    "power": "5",
    "toughness": "5",
    "text": "When \"Brims\" Barone, Midway Mobster enters, put a +1/+1 counter on each other creature you control that has a hat.",
    "manaCost": "{3}{W}{B}",
    "supertypes": ["Legendary"],
    "subtypes": ["Human", "Rogue"],
    "isFunny": True,
}


@pytest.fixture
def sample_creature():
    return SAMPLE_CREATURE.copy()


@pytest.fixture
def vanilla_creature():
    return VANILLA_CREATURE.copy()


@pytest.fixture
def funny_creature():
    return FUNNY_CREATURE.copy()


@pytest.fixture
def sample_card_data():
    """Minimal AtomicCards.json-shaped data for testing CardStore."""
    return {
        "data": {
            "Tarmogoyf": [_make_atomic(SAMPLE_CREATURE)],
            "Grizzly Bears": [_make_atomic(VANILLA_CREATURE)],
            "\"Brims\" Barone, Midway Mobster": [_make_atomic(FUNNY_CREATURE)],
            "Lightning Bolt": [{
                "name": "Lightning Bolt",
                "manaValue": 1.0,
                "type": "Instant",
                "types": ["Instant"],
                "text": "Lightning Bolt deals 3 damage to any target.",
                "manaCost": "{R}",
                "supertypes": [],
                "subtypes": [],
                "identifiers": {"scryfallOracleId": "test-bolt-id"},
            }],
        }
    }


def _make_atomic(creature_dict):
    """Wrap a creature dict to look like an AtomicCards.json entry."""
    entry = creature_dict.copy()
    entry.setdefault("identifiers", {"scryfallOracleId": f"test-{creature_dict['name'][:8]}"})
    return entry
