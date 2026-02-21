from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.models.metadata.document import MetadataDocument
from app.workers.fetcher import FetchError

_NOW = datetime.now(timezone.utc)
_DOC = MetadataDocument(
    url="https://example.com/",
    status_code=200,
    headers={"content-type": "text/html"},
    cookies={},
    page_source="<html></html>",
    created_at=_NOW,
    updated_at=_NOW,
)


class TestPostMetadata:
    def test_post_success(self, client):
        with patch(
            "app.api.metadata.routes.MetadataService.store_metadata",
            new_callable=AsyncMock,
            return_value=_DOC,
        ):
            resp = client.post("/metadata", json={"url": "https://example.com/"})
        assert resp.status_code == 200
        assert "message" in resp.json()

    def test_post_invalid_url_returns_422(self, client):
        resp = client.post("/metadata", json={"url": "not-a-url"})
        assert resp.status_code == 422

    def test_post_fetch_error_returns_400(self, client):
        with patch(
            "app.api.metadata.routes.MetadataService.store_metadata",
            new_callable=AsyncMock,
            side_effect=FetchError("DNS lookup failed"),
        ):
            resp = client.post(
                "/metadata", json={"url": "https://unreachable.example/"}
            )
        assert resp.status_code == 400
        assert "DNS lookup failed" in resp.json()["detail"]

    def test_post_db_error_returns_500(self, client):
        with patch(
            "app.api.metadata.routes.MetadataService.store_metadata",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB down"),
        ):
            resp = client.post("/metadata", json={"url": "https://example.com/"})
        assert resp.status_code == 500


class TestGetMetadata:
    def test_get_hit_returns_200(self, client):
        with patch(
            "app.api.metadata.routes.MetadataService.get_metadata",
            new_callable=AsyncMock,
            return_value=_DOC,
        ):
            resp = client.get("/metadata?url=https://example.com/")
        assert resp.status_code == 200
        assert resp.json()["url"] == "https://example.com/"

    def test_get_miss_returns_202(self, client):
        with (
            patch(
                "app.api.metadata.routes.MetadataService.get_metadata",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.api.metadata.routes.MetadataService.background_collect",
                new_callable=AsyncMock,
            ) as mock_bg,
        ):
            resp = client.get("/metadata?url=https://example.com/")
        assert resp.status_code == 202
        assert "message" in resp.json()
        mock_bg.assert_called_once_with("https://example.com/")

    def test_get_missing_url_param_returns_422(self, client):
        resp = client.get("/metadata")
        assert resp.status_code == 422

    def test_get_invalid_url_returns_422(self, client):
        resp = client.get("/metadata?url=not-a-url")
        assert resp.status_code == 422

    def test_get_db_error_returns_500(self, client):
        with patch(
            "app.api.metadata.routes.MetadataService.get_metadata",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB gone"),
        ):
            resp = client.get("/metadata?url=https://example.com")
        assert resp.status_code == 500


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
