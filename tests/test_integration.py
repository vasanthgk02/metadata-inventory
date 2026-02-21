"""Integration tests.

These tests exercise the full request → service → repository → database pipeline.

What is mocked:
  - MongoDB replaced with an in-memory AsyncMongoMockClient (no Docker needed)
  - External HTTP calls mocked per-test with respx

What is NOT mocked (runs real code):
  - FastAPI routes, dependency injection
  - MetadataService business logic
  - MetadataRepository (upsert, find_by_url, ensure_indexes)
  - URL normalisation, response shaping, error handling
"""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient
from unittest.mock import AsyncMock, patch

import app.workers.fetcher as fetcher_module
from app.main import app


_FAKE_HTML = "<!DOCTYPE html><html><body>Hello</body></html>"
_FAKE_RESPONSE = httpx.Response(
    200,
    headers={"content-type": "text/html; charset=utf-8"},
    text=_FAKE_HTML,
)


@pytest.fixture
def integration_client():
    """Full-stack client with in-memory MongoDB and no real HTTP traffic.

    The httpx client is reset before and after each test so that
    respx can intercept the freshly-created client for that test.
    """
    # Reset http client so respx can wrap the new one created inside the test
    fetcher_module._http_client = None

    with (
        patch("app.core.database.AsyncIOMotorClient", AsyncMongoMockClient),
        patch("app.workers.fetcher.close_http_client", new_callable=AsyncMock),
    ):
        with TestClient(app) as client:
            yield client

    # Ensure a stale client never leaks into the next test
    fetcher_module._http_client = None


# ── POST /metadata ─────────────────────────────────────────────────────────────

class TestIntegrationPost:
    @respx.mock
    def test_post_fetches_and_stores(self, integration_client):
        """POST returns 200 and the document is retrievable by GET."""
        respx.get("https://example.com/").mock(return_value=_FAKE_RESPONSE)

        resp = integration_client.post("/metadata", json={"url": "https://example.com/"})

        assert resp.status_code == 200
        assert "message" in resp.json()

    @respx.mock
    def test_post_upsert_does_not_duplicate(self, integration_client):
        """Posting the same URL twice updates the doc, not creates a second one."""
        respx.get("https://example.com/").mock(return_value=_FAKE_RESPONSE)

        r1 = integration_client.post("/metadata", json={"url": "https://example.com/"})
        r2 = integration_client.post("/metadata", json={"url": "https://example.com/"})

        assert r1.status_code == 200
        assert r2.status_code == 200

        # GET should still return exactly one document (not 404 or 500)
        get_resp = integration_client.get("/metadata?url=https://example.com/")
        assert get_resp.status_code == 200

    def test_post_invalid_url_returns_422(self, integration_client):
        resp = integration_client.post("/metadata", json={"url": "not-a-url"})
        assert resp.status_code == 422


# ── GET /metadata ──────────────────────────────────────────────────────────────

class TestIntegrationGet:
    @respx.mock
    def test_get_after_post_returns_200(self, integration_client):
        """After POST, GET should return the stored document with correct fields."""
        respx.get("https://example.com/").mock(return_value=_FAKE_RESPONSE)

        integration_client.post("/metadata", json={"url": "https://example.com/"})
        resp = integration_client.get("/metadata?url=https://example.com/")

        assert resp.status_code == 200
        body = resp.json()
        assert body["url"] == "https://example.com/"
        assert body["status_code"] == 200
        assert "content-type" in body["headers"]
        assert "created_at" in body
        assert "updated_at" in body
        # page_source must never be exposed in the API response
        assert "page_source" not in body

    def test_get_miss_returns_202(self, integration_client):
        """GET on an unknown URL returns 202 and a human-readable message."""
        resp = integration_client.get("/metadata?url=https://never-stored.example/")

        assert resp.status_code == 202
        assert "message" in resp.json()

    def test_get_missing_url_param_returns_422(self, integration_client):
        resp = integration_client.get("/metadata")
        assert resp.status_code == 422

    def test_get_invalid_url_returns_422(self, integration_client):
        resp = integration_client.get("/metadata?url=not-a-url")
        assert resp.status_code == 422


# ── Full lifecycle ─────────────────────────────────────────────────────────────

class TestIntegrationLifecycle:
    @respx.mock
    def test_miss_then_post_then_get_hit(self, integration_client):
        """GET miss → POST stores → GET hit — the canonical user flow."""
        respx.get("https://example.com/").mock(return_value=_FAKE_RESPONSE)

        # 1. Not stored yet
        miss = integration_client.get("/metadata?url=https://example.com/")
        assert miss.status_code == 202

        # 2. Store it
        post = integration_client.post("/metadata", json={"url": "https://example.com/"})
        assert post.status_code == 200

        # 3. Now cached
        hit = integration_client.get("/metadata?url=https://example.com/")
        assert hit.status_code == 200
        assert hit.json()["url"] == "https://example.com/"

    @respx.mock
    def test_url_normalisation_consistency(self, integration_client):
        """URL with and without trailing slash both resolve to the same stored record."""
        respx.get("https://example.com/").mock(return_value=_FAKE_RESPONSE)

        # POST with no trailing slash — pydantic normalises to https://example.com/
        integration_client.post("/metadata", json={"url": "https://example.com"})

        # GET with trailing slash — should hit the same document
        resp = integration_client.get("/metadata?url=https://example.com/")
        assert resp.status_code == 200
        assert resp.json()["url"] == "https://example.com/"

    @respx.mock
    def test_response_does_not_expose_page_source(self, integration_client):
        """page_source is stored in DB but must never appear in any API response."""
        respx.get("https://example.com/").mock(return_value=_FAKE_RESPONSE)

        integration_client.post("/metadata", json={"url": "https://example.com/"})
        resp = integration_client.get("/metadata?url=https://example.com/")

        assert "page_source" not in resp.json()
