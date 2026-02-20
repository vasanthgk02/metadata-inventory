from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, HttpUrl


class MetadataCreateRequest(BaseModel):
    """Request body for POST /metadata."""

    url: HttpUrl


class MetadataResponse(BaseModel):
    """API response shape for a stored metadata record.

    ``page_source`` is intentionally excluded — it is stored internally
    in ``MetadataDocument`` but never exposed through the API.
    """

    url: str
    status_code: int
    headers: dict[str, str]
    cookies: dict[str, str]
    created_at: datetime
    updated_at: datetime
