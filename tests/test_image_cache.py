import os
import pytest
from unittest.mock import AsyncMock, patch
from momir.image_cache import ImageCache, _sanitize_filename


class TestSanitizeFilename:

    def test_simple_name(self):
        assert _sanitize_filename("Lightning Bolt") == "Lightning_Bolt"

    def test_quotes_and_special_chars(self):
        result = _sanitize_filename("\"Brims\" Barone, Midway Mobster")
        assert "/" not in result
        assert '"' not in result

    def test_empty_string(self):
        assert _sanitize_filename("") == "_"


class TestImageCache:

    @pytest.fixture
    def cache(self, tmp_path):
        return ImageCache(cache_dir=str(tmp_path))

    def test_cache_dir_created(self, cache, tmp_path):
        assert os.path.isdir(str(tmp_path))

    @pytest.mark.asyncio
    async def test_cache_miss_fetches_from_scryfall(self, cache):
        fake_image = b'\xff\xd8\xff\xe0fake_jpeg_data'
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = fake_image
        mock_response.raise_for_status = lambda: None

        with patch("momir.image_cache.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get = AsyncMock(return_value=mock_response)
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            result = await cache.get_image("Lightning Bolt")
            assert result == fake_image
            client_instance.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_hit_serves_from_disk(self, cache, tmp_path):
        filename = _sanitize_filename("Lightning Bolt") + ".jpg"
        filepath = os.path.join(str(tmp_path), filename)
        expected = b'cached_image_data'
        with open(filepath, "wb") as f:
            f.write(expected)

        result = await cache.get_image("Lightning Bolt")
        assert result == expected

    @pytest.mark.asyncio
    async def test_network_failure_returns_none(self, cache):
        with patch("momir.image_cache.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get = AsyncMock(side_effect=Exception("network down"))
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            result = await cache.get_image("Lightning Bolt")
            assert result is None
