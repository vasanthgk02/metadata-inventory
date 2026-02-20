from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

from app.core.config import settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Singleton MongoDB connection manager.

    Use the module-level ``db`` instance; do not instantiate directly.

    Lifecycle::

        await db.connect()   # call once at startup
        ...
        await db.disconnect()  # call once at shutdown
    """

    _instance: DatabaseManager | None = None
    _client: AsyncIOMotorClient | None = None

    def __new__(cls) -> DatabaseManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def connect(self) -> None:
        """Open the Motor client and verify connectivity with a ping."""
        self._client = AsyncIOMotorClient(
            settings.mongo_uri,
            maxPoolSize=settings.mongo_max_pool_size,
        )
        await self._client.admin.command("ping")
        logger.info("Connected to MongoDB at %s.", settings.mongo_uri)

    async def disconnect(self) -> None:
        """Close the Motor client and release all pooled connections."""
        if self._client is not None:
            self._client.close()
            self._client = None
            logger.info("Disconnected from MongoDB.")

    def get_collection(self, name: str) -> AsyncIOMotorCollection:
        """Return a Motor collection by name from the configured database."""
        if self._client is None:
            raise RuntimeError(
                "DatabaseManager is not connected. Call connect() first."
            )
        return self._client[settings.mongo_db][name]


#: Module-level singleton — import and use this everywhere.
db: DatabaseManager = DatabaseManager()



