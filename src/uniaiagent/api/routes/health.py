"""Health check endpoint."""

from fastapi import APIRouter

from uniaiagent.core import perform_health_check
from uniaiagent.core.health_checker import get_version

router = APIRouter()


@router.get("/")
async def root():
    """Root endpoint returning basic application information."""
    version = await get_version()
    return {
        "name": "UniAiAgent",
        "version": version,
        "status": "running",
    }


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    health_status = await perform_health_check()
    status_code = 200
    if health_status.status == "unhealthy":
        status_code = 503

    return health_status.to_dict()
