"""Abstract base class for all MongoDB repositories.

Every repository in this project must extend ``BaseRepository``.

Extending for a new collection:
    1. Add the collection name to ``CollectionNames``.
    2. Subclass ``BaseRepository``, set ``COLLECTION_NAME``, and override
       ``ensure_indexes()`` with the indexes your collection needs.
    3. Register the repository in the app lifespan (``main.py``).

Example::

    class UserRepository(BaseRepository):
        COLLECTION_NAME = CollectionNames.USERS

        async def ensure_indexes(self) -> None:
            await self._col.create_index("email", unique=True)
"""

from __future__ import annotations

import logging
from abc import ABC
from typing import ClassVar, TypeVar

from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.database import DatabaseManager

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="BaseRepository")


class BaseRepository(ABC):
    """Base class that wires a repository to its Motor collection.

    Subclasses declare:
    - ``COLLECTION_NAME`` - the name string from ``CollectionNames``.
    - ``ensure_indexes()`` - indexes to create at startup (idempotent).

    The ``from_db`` classmethod is the standard factory used
    throughout the app and in the lifespan startup hook.
    """

    COLLECTION_NAME: ClassVar[str]

    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        self._col = collection

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_db(cls: type[T], db: DatabaseManager) -> T:
        """Instantiate the repository using the live ``DatabaseManager``.

        Usage::

            repo = MetadataRepository.from_db(db)
        """
        return cls(db.get_collection(cls.COLLECTION_NAME))

    # ------------------------------------------------------------------
    # Index management (override in subclasses)
    # ------------------------------------------------------------------

    async def ensure_indexes(self) -> None:
        """Create collection indexes.  Called once at startup.

        The default is a no-op.  Override to declare the indexes
        your collection requires; Motor / MongoDB make this idempotent
        (existing indexes are silently skipped).
        """
