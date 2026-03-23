from PIL import Image
from momir.thermal_renderer import render_card


class TestRenderCard:

    def test_output_is_576_wide(self, sample_creature):
        img = render_card(sample_creature)
        assert img.width == 576

    def test_output_is_1_bit(self, sample_creature):
        img = render_card(sample_creature)
        assert img.mode == "1"

    def test_variable_height_with_text(self, sample_creature, vanilla_creature):
        img_with_text = render_card(sample_creature)
        img_no_text = render_card(vanilla_creature)
        assert img_with_text.height > img_no_text.height

    def test_minimum_height(self, vanilla_creature):
        img = render_card(vanilla_creature)
        assert img.height >= 50

    def test_handles_star_power_toughness(self, sample_creature):
        img = render_card(sample_creature)
        assert img.width == 576

    def test_handles_no_mana_cost(self, sample_creature):
        creature = sample_creature.copy()
        creature["manaCost"] = ""
        img = render_card(creature)
        assert img.width == 576

    def test_handles_long_rules_text(self):
        creature = {
            "name": "Rules Lawyer",
            "manaValue": 5.0,
            "type": "Creature — Human Advisor",
            "types": ["Creature"],
            "power": "1",
            "toughness": "1",
            "text": "Spells and abilities your opponents control can't cause you to reduce your life total to a number less than 1. " * 5,
            "manaCost": "{3}{W}{W}",
            "supertypes": [],
            "subtypes": ["Human", "Advisor"],
            "isFunny": True,
        }
        img = render_card(creature)
        assert img.width == 576
        assert img.height > 200
