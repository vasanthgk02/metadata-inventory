"""Async HTTP fetcher.

Responsible solely for retrieving HTTP metadata from a URL.

Uses httpx.AsyncClient which is meant to be long-lived and reused.
A single shared client is managed by the module; see ``get_http_client``
and ``close_http_client`` for lifecycle hooks.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from tenacity import (
    RetryError,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    wait_exponential,
)

from app.core.config import settings
from app.models.metadata.document import MetadataDocument

logger = logging.getLogger(__name__)

# Module-level shared client
_http_client: Optional[httpx.AsyncClient] = None


def get_http_client() -> httpx.AsyncClient:
    """Return the shared AsyncClient.  Creates one if missing."""
    global _http_client  # noqa: PLW0603
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.http_timeout),
            follow_redirects=True,
            verify=settings.http_verify_ssl,
            headers={"User-Agent": "MetadataInventoryBot/1.0"},
        )
    return _http_client


async def close_http_client() -> None:
    """Close the shared AsyncClient gracefully."""
    global _http_client  # noqa: PLW0603
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None
        logger.info("HTTP client closed.")


class FetchError(Exception):
    """Raised when the fetcher cannot collect metadata."""


@retry(
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    stop=lambda rs: rs.attempt_number >= settings.http_max_retries + 1,
    wait=wait_exponential(multiplier=0.5, min=0.5, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=False,
)
async def _fetch_with_retry(url: str) -> MetadataDocument:
    """Single fetch attempt; tenacity retries on transient errors."""
    return await _do_fetch(url)


async def fetch_metadata(url: str) -> MetadataDocument:
    """Fetch HTTP metadata for *url* and return an unsaved MetadataDocument.

    Retries on transient errors (timeouts, connection failures) using
    exponential backoff via tenacity.  Raises :class:`FetchError` on
    permanent failures or when all retries are exhausted.

    The ``stop`` condition uses a lambda so ``settings.http_max_retries``
    is read per-attempt, not at import time — patches in tests work as
    expected.
    """
    try:
        return await _fetch_with_retry(url)
    except RetryError as exc:
        raise FetchError(
            f"Failed to fetch {url} after {settings.http_max_retries + 1} attempts: "
            f"{exc.last_attempt.exception()}"
        ) from exc


async def _do_fetch(url: str) -> MetadataDocument:
    """Perform a single HTTP GET and map the response to a MetadataDocument."""
    client = get_http_client()
    now = datetime.now(timezone.utc)

    try:
        response = await client.get(url)
    except httpx.InvalidURL as exc:
        raise FetchError(f"Invalid URL '{url}': {exc}") from exc
    except httpx.TimeoutException:
        raise  # propagate for retry logic
    except httpx.ConnectError:
        raise  # propagate for retry logic
    except httpx.RequestError as exc:
        raise FetchError(f"Request error for '{url}': {exc}") from exc

    # Normalise headers and cookies to plain dicts[str, str]
    headers: dict[str, str] = dict(response.headers)
    cookies: dict[str, str] = {k: v for k, v in response.cookies.items()}

    return MetadataDocument(
        url=url,
        headers=headers,
        cookies=cookies,
        page_source=response.text,
        status_code=response.status_code,
        created_at=now,
        updated_at=now,
    )
