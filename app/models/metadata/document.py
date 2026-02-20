from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class MetadataDocument(BaseModel):
    """Internal representation of a stored metadata record.

    Never returned from the API directly — see ``MetadataResponse``.
    """

    url: str
    status_code: int
    headers: dict[str, str]
    cookies: dict[str, str]
    page_source: str
    created_at: datetime
    updated_at: datetime
