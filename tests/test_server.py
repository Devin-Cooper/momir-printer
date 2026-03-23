import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from momir.ble_printer import PrinterState


@pytest.fixture
def client():
    mock_store = MagicMock()
    mock_store.get_random_creature.return_value = {
        "name": "Tarmogoyf",
        "manaValue": 2.0,
        "type": "Creature — Lhurgoyf",
        "power": "*",
        "toughness": "1+*",
        "text": "Tarmogoyf's power is equal to the number of card types among cards in all graveyards and its toughness is equal to that number plus 1.",
        "manaCost": "{1}{G}",
    }

    with patch("momir.server.card_store", mock_store), \
         patch("momir.server.image_cache") as mock_cache, \
         patch("momir.server.printer") as mock_printer:
        mock_printer.state = PrinterState.READY
        mock_cache.get_image = AsyncMock(return_value=b"fake_image")
        from momir.server import app
        yield TestClient(app)


class TestRollEndpoint:

    def test_roll_returns_creature(self, client):
        resp = client.post("/roll", json={"mv": 2, "include_funny": False})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Tarmogoyf"
        assert "image_url" in data

    def test_roll_empty_mv(self, client):
        with patch("momir.server.card_store") as mock_store:
            mock_store.get_random_creature.return_value = None
            resp = client.post("/roll", json={"mv": 14, "include_funny": True})
            assert resp.status_code == 404


class TestPrintEndpoint:

    def test_print_no_card_rolled(self, client):
        with patch("momir.server.last_rolled_card", None):
            resp = client.post("/print")
            assert resp.status_code == 400

    def test_print_when_already_printing(self, client):
        with patch("momir.server.last_rolled_card", {"name": "Test", "type": "Creature", "power": "1", "toughness": "1", "text": "", "manaCost": "{W}"}), \
             patch("momir.server.printer") as mock_printer:
            mock_printer.state = PrinterState.PRINTING
            resp = client.post("/print")
            assert resp.status_code == 409


class TestImageEndpoint:

    def test_get_image_success(self, client):
        with patch("momir.server.image_cache") as mock_cache:
            mock_cache.get_image = AsyncMock(return_value=b'\xff\xd8fake_jpg')
            resp = client.get("/image/Lightning%20Bolt")
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "image/jpeg"

    def test_get_image_not_found(self, client):
        with patch("momir.server.image_cache") as mock_cache:
            mock_cache.get_image = AsyncMock(return_value=None)
            resp = client.get("/image/Nonexistent%20Card")
            assert resp.status_code == 404


class TestStatusEndpoint:

    def test_status_returns_state(self, client):
        resp = client.get("/status")
        assert resp.status_code == 200
        assert "state" in resp.json()


class TestSettingsEndpoint:

    def test_get_settings(self, client):
        resp = client.get("/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "include_funny" in data
        assert "auto_print" in data

    def test_update_settings(self, client):
        resp = client.post("/settings", json={"include_funny": True, "auto_print": True})
        assert resp.status_code == 200
        resp2 = client.get("/settings")
        data = resp2.json()
        assert data["include_funny"] is True
        assert data["auto_print"] is True
