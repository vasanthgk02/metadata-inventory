from __future__ import annotations

import logging

from app.models.metadata.document import MetadataDocument
from app.repositories.metadata.repository import MetadataRepository
from app.workers.fetcher import FetchError, fetch_metadata

logger = logging.getLogger(__name__)


class MetadataService:
    """Business logic for metadata collection and retrieval."""

    def __init__(self, repo: MetadataRepository) -> None:
        self._repo = repo

    async def get_metadata(self, url: str) -> MetadataDocument | None:
        """Return the cached metadata for *url*, or ``None`` if not stored."""
        return await self._repo.find_by_url(url)

    async def store_metadata(self, url: str) -> MetadataDocument:
        """Fetch live metadata for *url* and persist it.

        Returns the document as it was written to the database (with the
        server-side ``updated_at`` timestamp applied by the repository).

        Raises:
            FetchError: propagated from the fetcher on network failure.
            RuntimeError: raised by repository on database failure.
        """
        doc = await fetch_metadata(url)
        return await self._repo.upsert(doc)

    async def background_collect(self, url: str) -> None:
        """Fire-and-forget wrapper for ``store_metadata``.

        Catches and logs all exceptions so a transient network or database
        failure never crashes the background task silently.  FastAPI cannot
        propagate background task exceptions to the original response, so
        swallowing here with structured logging is the correct approach.
        """
        try:
            await self.store_metadata(url)
        except FetchError as exc:
            logger.error("Background fetch failed for %s: %s", url, exc)
        except Exception as exc:
            logger.exception("Unexpected error in background_collect for %s: %s", url, exc)
