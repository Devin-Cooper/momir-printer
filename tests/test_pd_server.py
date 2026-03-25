import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from PIL import Image
from fastapi.testclient import TestClient
from momir.ble_printer import PrinterState, PROFILE_M02S


@pytest.fixture
def client():
    with patch("printdialog.server.printer") as mock_printer:
        type(mock_printer).state = PropertyMock(return_value=PrinterState.READY)
        type(mock_printer).profile = PropertyMock(return_value=PROFILE_M02S)
        mock_printer._device_name = "M02S"
        mock_printer.send_raw_commands = AsyncMock(return_value=True)
        import printdialog.server as srv
        srv._current_file = None
        srv._current_ext = None
        srv._page_count = 1
        yield TestClient(srv.app)


class TestUpload:

    def test_upload_image(self, client):
        img = Image.new("RGB", (100, 100), "red")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        resp = client.post("/upload", files={"file": ("test.png", buf, "image/png")})
        assert resp.status_code == 200
        data = resp.json()
        assert data["page_count"] == 1

    def test_upload_replaces_previous(self, client):
        for color in ["red", "blue"]:
            img = Image.new("RGB", (100, 100), color)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            resp = client.post("/upload", files={"file": ("test.png", buf, "image/png")})
            assert resp.status_code == 200


class TestPreview:

    def test_preview_returns_png(self, client):
        img = Image.new("RGB", (100, 100), "red")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        client.post("/upload", files={"file": ("test.png", buf, "image/png")})

        resp = client.post("/preview", json={
            "page": 0, "scale": 100, "fit_to_width": True,
            "density": 4, "dither": "floyd-steinberg",
            "orientation": "auto", "invert": False, "print_width": 576,
        })
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"

    def test_preview_without_upload(self, client):
        resp = client.post("/preview", json={
            "page": 0, "scale": 100, "fit_to_width": True,
            "density": 4, "dither": "floyd-steinberg",
            "orientation": "auto", "invert": False, "print_width": 576,
        })
        assert resp.status_code == 400


class TestStatus:

    def test_status_returns_model(self, client):
        resp = client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "state" in data
        assert "model" in data
        assert "print_width" in data


class TestPrint:

    def test_print_without_upload(self, client):
        resp = client.post("/print", json={
            "page": 0, "scale": 100, "fit_to_width": True,
            "density": 4, "dither": "floyd-steinberg",
            "orientation": "auto", "invert": False,
            "print_width": 576, "feed": "single",
        })
        assert resp.status_code == 400
