from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # MongoDB
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "metadata_inventory"
    mongo_max_pool_size: int = 10

    # HTTP fetcher
    http_timeout: float = 10.0
    http_max_retries: int = 3
    http_verify_ssl: bool = True  # set False behind corporate SSL-inspection proxies

    # Logging
    log_level: str = "INFO"


settings = Settings()
