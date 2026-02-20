from __future__ import annotations

import logging
from datetime import datetime, timezone

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.collections import CollectionNames
from app.models.metadata.document import MetadataDocument
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class MetadataRepository(BaseRepository):
    """MongoDB repository for the ``metadata`` collection."""

    COLLECTION_NAME = CollectionNames.METADATA

    async def ensure_indexes(self) -> None:
        await self._col.create_index("url", unique=True)

    async def upsert(self, document: MetadataDocument) -> MetadataDocument:
        """Insert or update the document keyed by *url*.

        Uses ``find_one_and_update`` with ``upsert=True`` so concurrent
        requests on the same URL do not produce duplicates.

        - ``$set`` updates all fields except ``created_at`` on every write.
        - ``$setOnInsert`` preserves the original ``created_at`` on insert
          and leaves it untouched on subsequent updates.
        - A ``DuplicateKeyError`` race-condition guard retries as a plain
          update if two requests race on the unique ``url`` index.
        """
        now = datetime.now(timezone.utc)
        payload = document.model_dump(exclude={"created_at"})
        payload["updated_at"] = now
        try:
            updated = await self._col.find_one_and_update(
                {"url": document.url},
                {
                    "$set": payload,
                    "$setOnInsert": {"created_at": document.created_at},
                },
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            # Race condition: another request inserted first — retry as update.
            updated = await self._col.find_one_and_update(
                {"url": document.url},
                {"$set": payload},
                return_document=ReturnDocument.AFTER,
            )
            if updated is None:
                # Document was deleted in the window between our two operations.
                raise RuntimeError(
                    f"Upsert race condition unresolved for url={document.url}"
                )
        except PyMongoError as exc:
            logger.exception("MongoDB upsert failed for url=%s", document.url)
            raise RuntimeError("Database write error") from exc

        updated.pop("_id", None)
        return MetadataDocument(**updated)

    async def find_by_url(self, url: str) -> MetadataDocument | None:
        """Return the stored document for *url*, or ``None`` if not found."""
        result = await self._col.find_one({"url": url})
        if result is None:
            return None
        result.pop("_id", None)
        return MetadataDocument(**result)
