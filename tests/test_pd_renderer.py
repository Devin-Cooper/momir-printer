import math
import pytest
from PIL import Image, ImageDraw
from printdialog.renderer import (
    render, build_init_commands, build_feed_commands,
    build_raster_commands,
)
from momir.ble_printer import PROFILE_M02S, PROFILE_M04S, MAX_LINES_PER_BLOCK


@pytest.fixture
def sample_image():
    img = Image.new("RGB", (800, 600), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([100, 100, 700, 500], fill="black")
    draw.rectangle([200, 200, 600, 400], fill="gray")
    return img


@pytest.fixture
def tall_image():
    return Image.new("RGB", (400, 800), "white")


class TestRender:

    def test_fit_to_width_produces_correct_width(self, sample_image):
        img = render(sample_image, print_width=576, fit_to_width=True)
        assert img.width == 576
        assert img.mode == "1"

    def test_fit_to_width_m04s(self, sample_image):
        img = render(sample_image, print_width=1232, fit_to_width=True)
        assert img.width == 1232

    def test_scale_percentage(self, sample_image):
        img = render(sample_image, print_width=576, fit_to_width=False, scale=50)
        assert img.width == 576
        assert img.mode == "1"

    def test_orientation_auto_narrow_rotates_landscape(self, sample_image):
        img = render(sample_image, print_width=576, orientation="auto")
        assert img.height > img.width or img.width == 576

    def test_orientation_auto_wide_rotates_portrait(self, tall_image):
        img = render(tall_image, print_width=1232, orientation="auto")
        assert img.width == 1232

    def test_orientation_portrait_forces(self, sample_image):
        img = render(sample_image, print_width=576, orientation="portrait")
        assert img.width == 576

    def test_orientation_landscape_forces(self, tall_image):
        img = render(tall_image, print_width=576, orientation="landscape")
        assert img.width == 576

    def test_dither_floyd_steinberg(self, sample_image):
        img = render(sample_image, print_width=576, dither="floyd-steinberg")
        assert img.mode == "1"

    def test_dither_threshold(self, sample_image):
        img = render(sample_image, print_width=576, dither="threshold")
        assert img.mode == "1"

    def test_invert(self, sample_image):
        normal = render(sample_image, print_width=576, invert=False)
        inverted = render(sample_image, print_width=576, invert=True)
        assert normal.tobytes() != inverted.tobytes()

    def test_output_always_1bit(self, sample_image):
        img = render(sample_image, print_width=576)
        assert img.mode == "1"


class TestBuildInitCommands:

    def test_m02s_ignores_density(self):
        default = build_init_commands(PROFILE_M02S, 4)
        custom = build_init_commands(PROFILE_M02S, 10)
        assert default == custom == PROFILE_M02S.init_commands

    def test_m04s_default_density(self):
        cmds = build_init_commands(PROFILE_M04S, 4)
        assert b'\x1f\x11\x02\x04' in cmds
        assert b'\x1f\x11\x37\x96' in cmds

    def test_m04s_custom_density(self):
        cmds = build_init_commands(PROFILE_M04S, 8)
        assert b'\x1f\x11\x02\x08' in cmds
        assert b'\x1f\x11\x37\xd9' in cmds

    def test_m04s_max_density(self):
        cmds = build_init_commands(PROFILE_M04S, 15)
        assert b'\x1f\x11\x02\x0f' in cmds
        assert b'\x1f\x11\x37\xff' in cmds


class TestBuildFeedCommands:

    def test_none(self):
        assert build_feed_commands("none") == b''

    def test_single(self):
        assert build_feed_commands("single") == b'\x1b\x64\x02'

    def test_double(self):
        assert build_feed_commands("double") == b'\x1b\x64\x04'


class TestBuildRasterCommands:

    def test_produces_bytes(self, sample_image):
        img = render(sample_image, print_width=576)
        cmds = build_raster_commands(img, 72)
        assert isinstance(cmds, bytes)
        assert len(cmds) > 0

    def test_block_splitting(self):
        height = MAX_LINES_PER_BLOCK + 45
        img = Image.new("1", (576, height), 1)
        cmds = build_raster_commands(img, 72)
        gs_v_0 = b'\x1d\x76\x30\x00'
        expected_blocks = math.ceil(height / MAX_LINES_PER_BLOCK)
        assert cmds.count(gs_v_0) == expected_blocks
