from fastapi import APIRouter

from app.api.metadata.routes import router as metadata_router

router = APIRouter()
router.include_router(metadata_router)
