from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """TestClient with lifespan startup/shutdown hooks fully mocked."""
    with (
        patch(
            "app.core.database.DatabaseManager.connect",
            new_callable=AsyncMock,
        ),
        patch(
            "app.core.database.DatabaseManager.disconnect",
            new_callable=AsyncMock,
        ),
        patch(
            "app.core.database.DatabaseManager.get_collection",
            return_value=MagicMock(),
        ),
        patch(
            "app.repositories.metadata.repository.MetadataRepository.ensure_indexes",
            new_callable=AsyncMock,
        ),
        patch(
            "app.workers.fetcher.close_http_client",
            new_callable=AsyncMock,
        ),
    ):
        with TestClient(app) as c:
            yield c
