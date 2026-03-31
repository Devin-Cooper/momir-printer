from PIL import Image
from momir.ble_printer import (
    PROFILE_M02S,
    PROFILE_M04S,
    build_print_commands,
    pack_image_to_bytes,
    resolve_transfer_settings,
)

BYTES_PER_LINE = PROFILE_M02S.bytes_per_line  # 72


class TestPackImage:

    def test_all_white_image(self):
        img = Image.new("1", (576, 1), 1)
        data = pack_image_to_bytes(img, BYTES_PER_LINE)
        assert len(data) == BYTES_PER_LINE
        assert all(b == 0x00 for b in data)

    def test_all_black_image(self):
        img = Image.new("1", (576, 1), 0)
        data = pack_image_to_bytes(img, BYTES_PER_LINE)
        assert len(data) == BYTES_PER_LINE
        assert all(b == 0xFF for b in data)

    def test_multi_line_length(self):
        img = Image.new("1", (576, 10), 1)
        data = pack_image_to_bytes(img, BYTES_PER_LINE)
        assert len(data) == BYTES_PER_LINE * 10

    def test_0x0a_substitution(self):
        img = Image.new("1", (576, 1), 1)
        img.putpixel((4, 0), 0)
        img.putpixel((6, 0), 0)
        data = pack_image_to_bytes(img, BYTES_PER_LINE)
        assert data[0] == 0x14


class TestBuildPrintCommands:

    def test_small_image_single_block(self):
        img = Image.new("1", (576, 100), 1)
        commands = build_print_commands(img, PROFILE_M02S)
        assert b'\x1b\x40' in commands
        assert b'\x1f\x11\x02\x04' in commands
        assert b'\x1d\x76\x30\x00\x48\x00' in commands
        assert b'\x1b\x64\x02' in commands

    def test_large_image_multiple_blocks(self):
        img = Image.new("1", (576, 300), 1)
        commands = build_print_commands(img, PROFILE_M02S)
        gs_v_0 = b'\x1d\x76\x30\x00\x48\x00'
        count = commands.count(gs_v_0)
        assert count == 2

    def test_exact_255_lines_single_block(self):
        img = Image.new("1", (576, 255), 1)
        commands = build_print_commands(img, PROFILE_M02S)
        gs_v_0 = b'\x1d\x76\x30\x00\x48\x00'
        count = commands.count(gs_v_0)
        assert count == 1

    def test_command_length_matches_image(self):
        img = Image.new("1", (576, 100), 0)
        commands = build_print_commands(img, PROFILE_M02S)
        assert len(commands) > 7200


class TestResolveTransferSettings:

    def test_m02s_uses_conservative_chunking(self):
        settings = resolve_transfer_settings(
            PROFILE_M02S,
            mtu_size=247,
            max_write_without_response_size=244,
        )
        assert settings.chunk_size == 205
        assert settings.chunks_per_burst == 1
        assert settings.burst_delay == 0.07
        assert settings.inter_chunk_delay == 0.012

    def test_m04s_keeps_profile_bursting(self):
        settings = resolve_transfer_settings(
            PROFILE_M04S,
            mtu_size=247,
            max_write_without_response_size=244,
        )
        assert settings.chunk_size == 205
        assert settings.chunks_per_burst == PROFILE_M04S.chunks_per_burst
        assert settings.burst_delay == PROFILE_M04S.burst_delay
        assert settings.inter_chunk_delay == 0.008

    def test_characteristic_limit_wins_when_smaller(self):
        settings = resolve_transfer_settings(
            PROFILE_M02S,
            mtu_size=517,
            max_write_without_response_size=128,
        )
        assert settings.chunk_size == 128
