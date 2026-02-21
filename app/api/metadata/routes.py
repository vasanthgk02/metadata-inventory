from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import HttpUrl, ValidationError

from app.core.database import db
from app.models.common import AcceptedResponse
from app.models.metadata.schemas import MetadataCreateRequest, MetadataResponse
from app.repositories.metadata.repository import MetadataRepository
from app.services.metadata.service import MetadataService
from app.workers.fetcher import FetchError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metadata", tags=["metadata"])


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def _get_service() -> MetadataService:
    """FastAPI dependency that builds a ``MetadataService`` for each request."""
    return MetadataService(MetadataRepository.from_db(db))


# ---------------------------------------------------------------------------
# POST /metadata
# ---------------------------------------------------------------------------


@router.post(
    "",
    status_code=200,
    response_model=AcceptedResponse,
    summary="Fetch and store metadata for a URL",
)
async def post_metadata(
    request: MetadataCreateRequest,
    service: MetadataService = Depends(_get_service),
) -> AcceptedResponse:
    """Fetch live HTTP metadata for the given URL and persist it.

    Blocks until the fetch and upsert complete.

    - **200** — metadata fetched and stored successfully
    - **400** — URL could not be fetched (network / DNS error)
    - **422** — invalid URL format
    - **500** — database failure
    """
    url = str(request.url)
    try:
        await service.store_metadata(url)
        return AcceptedResponse(message=f"Metadata stored for {url}")
    except FetchError as exc:
        logger.warning("POST /metadata fetch error for %s: %s", url, exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("POST /metadata DB error for %s: %s", url, exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# GET /metadata
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=MetadataResponse,
    responses={202: {"model": AcceptedResponse}},
    summary="Retrieve cached metadata for a URL",
)
async def get_metadata(
    url: str,
    background_tasks: BackgroundTasks,
    service: MetadataService = Depends(_get_service),
) -> MetadataResponse | JSONResponse:
    """Return the cached metadata document for *url*.

    On a cache miss, returns **202 Accepted** immediately and schedules a
    background task to fetch and store the metadata without blocking the
    response.  No HTTP self-calls are made; orchestration is internal only.

    - **200** — document found and returned
    - **202** — not yet stored; background collection has been triggered
    - **422** — ``url`` query parameter missing or not a valid HTTP URL
    - **500** — database failure
    """
    try:
        normalised_url = str(HttpUrl(url))
    except ValidationError:
        raise HTTPException(status_code=422, detail=f"Invalid URL: {url}")

    try:
        doc = await service.get_metadata(normalised_url)
        if doc is None:
            background_tasks.add_task(service.background_collect, normalised_url)
            return JSONResponse(
                status_code=202,
                content=AcceptedResponse(
                    message=f"No metadata yet for {normalised_url}. Collection triggered."
                ).model_dump(),
            )
        return MetadataResponse(**doc.model_dump(exclude={"page_source"}))
    except Exception as exc:
        logger.error("GET /metadata DB error for %s: %s", normalised_url, exc)
        raise HTTPException(status_code=500, detail=str(exc))
