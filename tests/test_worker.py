from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.models.metadata.document import MetadataDocument
from app.repositories.metadata.repository import MetadataRepository
from app.services.metadata.service import MetadataService
from app.workers.fetcher import FetchError, fetch_metadata

_NOW = datetime.now(timezone.utc)


def _make_doc(**kwargs) -> MetadataDocument:
    defaults = dict(
        url="https://example.com/",
        status_code=200,
        headers={"content-type": "text/html"},
        cookies={},
        page_source="<html></html>",
        created_at=_NOW,
        updated_at=_NOW,
    )
    return MetadataDocument(**{**defaults, **kwargs})


# ---------------------------------------------------------------------------
# Fetcher tests
# ---------------------------------------------------------------------------


class TestFetcher:
    async def test_successful_fetch(self):
        mock_resp = httpx.Response(
            200,
            text="<html></html>",
            request=httpx.Request("GET", "https://example.com/"),
        )
        with patch("app.workers.fetcher.get_http_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_get.return_value = mock_client
            result = await fetch_metadata("https://example.com/")
        assert result.status_code == 200
        assert result.url == "https://example.com/"

    async def test_invalid_url_raises_fetch_error(self):
        with patch("app.workers.fetcher.get_http_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.InvalidURL("invalid url")
            )
            mock_get.return_value = mock_client
            with pytest.raises(FetchError, match="Invalid URL"):
                await fetch_metadata("not-a-url")

    async def test_non_200_response_is_stored(self):
        mock_resp = httpx.Response(
            404,
            text="not found",
            request=httpx.Request("GET", "https://example.com/404"),
        )
        with patch("app.workers.fetcher.get_http_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_get.return_value = mock_client
            result = await fetch_metadata("https://example.com/404")
        assert result.status_code == 404

    async def test_timeout_retries_and_raises(self):
        with (
            patch("app.workers.fetcher.settings") as mock_settings,
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch(
                "app.workers.fetcher._do_fetch", new_callable=AsyncMock
            ) as mock_fetch,
        ):
            mock_settings.http_max_retries = 1
            mock_fetch.side_effect = httpx.TimeoutException("timed out")
            with pytest.raises(FetchError):
                await fetch_metadata("https://example.com/")
        assert mock_fetch.call_count == 2

    async def test_connect_error_retries_and_raises(self):
        with (
            patch("app.workers.fetcher.settings") as mock_settings,
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch(
                "app.workers.fetcher._do_fetch", new_callable=AsyncMock
            ) as mock_fetch,
        ):
            mock_settings.http_max_retries = 1
            mock_fetch.side_effect = httpx.ConnectError("refused")
            with pytest.raises(FetchError):
                await fetch_metadata("https://example.com/")
        assert mock_fetch.call_count == 2


# ---------------------------------------------------------------------------
# MetadataService tests
# ---------------------------------------------------------------------------


class TestMetadataService:
    @pytest.fixture
    def repo(self):
        return AsyncMock(spec=MetadataRepository)

    @pytest.fixture
    def service(self, repo):
        return MetadataService(repo)

    async def test_get_metadata_returns_document(self, service, repo):
        doc = _make_doc()
        repo.find_by_url.return_value = doc
        result = await service.get_metadata("https://example.com/")
        assert result == doc
        repo.find_by_url.assert_called_once_with("https://example.com/")

    async def test_get_metadata_returns_none_on_miss(self, service, repo):
        repo.find_by_url.return_value = None
        result = await service.get_metadata("https://example.com/")
        assert result is None

    async def test_store_metadata_fetches_and_upserts(self, service, repo):
        doc = _make_doc()
        repo.upsert.return_value = doc
        with patch(
            "app.services.metadata.service.fetch_metadata",
            new_callable=AsyncMock,
            return_value=doc,
        ) as mock_fetch:
            result = await service.store_metadata("https://example.com/")
        mock_fetch.assert_called_once_with("https://example.com/")
        repo.upsert.assert_called_once_with(doc)
        assert result == doc

    async def test_background_collect_persists_data(self, service):
        doc = _make_doc()
        with patch.object(
            service, "store_metadata", new_callable=AsyncMock, return_value=doc
        ) as mock_store:
            await service.background_collect("https://example.com/")
        mock_store.assert_called_once_with("https://example.com/")

    async def test_background_collect_logs_fetch_error(self, service):
        with patch.object(
            service,
            "store_metadata",
            new_callable=AsyncMock,
            side_effect=FetchError("network failure"),
        ):
            await service.background_collect("https://example.com/")  # must not raise

    async def test_background_collect_swallows_db_error(self, service):
        """Non-FetchError exceptions (e.g. DB crash) must also be swallowed."""
        with patch.object(
            service,
            "store_metadata",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB crashed"),
        ):
            await service.background_collect("https://example.com/")  # must not raise

    async def test_store_metadata_propagates_fetch_error(self, service):
        with patch(
            "app.services.metadata.service.fetch_metadata",
            new_callable=AsyncMock,
            side_effect=FetchError("network error"),
        ):
            with pytest.raises(FetchError, match="network error"):
                await service.store_metadata("https://example.com/")

    async def test_store_metadata_propagates_db_error(self, service, repo):
        doc = _make_doc()
        with patch(
            "app.services.metadata.service.fetch_metadata",
            new_callable=AsyncMock,
            return_value=doc,
        ):
            repo.upsert.side_effect = RuntimeError("DB crashed")
            with pytest.raises(RuntimeError, match="DB crashed"):
                await service.store_metadata("https://example.com/")
