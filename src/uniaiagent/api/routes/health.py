"""Health check endpoint."""

from fastapi import APIRouter

from uniaiagent.core import perform_health_check

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    health_status = await perform_health_check()
    status_code = 200
    if health_status.status == "unhealthy":
        status_code = 503

    return health_status.to_dict()
