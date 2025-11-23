"""Main FastAPI application entry point."""
import os
os.environ["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from uniaiagent.api.middleware import get_auth_status
from uniaiagent.api.middleware import perform_custom_validation
from uniaiagent.api.routes import claude, health, openai, process
from uniaiagent.config import settings
from uniaiagent.core import executor
from uniaiagent.exceptions.custom_errors import BaseError
from pydantic import ValidationError as PydanticValidationError

from uniaiagent.exceptions.handlers import (
    base_error_handler,
    general_exception_handler,
    validation_error_handler,
)
from uniaiagent.services import server_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    auth_status = get_auth_status()
    server_logger.info(
        type="server_startup",
        environment=settings.node_env,
        log_level=settings.log_level,
        authentication={
            "enabled": auth_status["enabled"],
            "keyCount": auth_status["keyCount"],
        },
        msg="Starting UniAIAgent Server",
    )

    if auth_status["enabled"]:
        server_logger.info(
            type="auth_config",
            key_count=auth_status["keyCount"],
            msg=f"Authentication enabled with {auth_status['keyCount']} API key(s)",
        )
    else:
        server_logger.warn(
            type="auth_config",
            sample_key=auth_status.get("sampleKey"),
            msg="Authentication disabled - API accessible without authentication",
        )

    yield

    # Shutdown
    server_logger.info(
        type="server_shutdown",
        msg="Shutting down UniAIAgent Server",
    )
    executor.cleanup_active_processes()


# Create FastAPI app
app = FastAPI(
    title="UniAIAgent",
    version="0.7.1",
    description="HTTP proxy server for Claude Code CLI with OpenAI API compatibility",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Add request ID middleware
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add request ID to request state."""
    import uuid

    request.state.request_id = str(uuid.uuid4())
    response = await call_next(request)
    return response


# Add custom validation middleware
@app.middleware("http")
async def validate_request(request: Request, call_next):
    """Perform custom validation."""
    if request.method in ["POST", "PUT"]:
        try:
            body = await request.json()
            await perform_custom_validation(request, body)
        except Exception:
            pass  # Let Pydantic handle validation errors
    response = await call_next(request)
    return response


# Register exception handlers
app.add_exception_handler(BaseError, base_error_handler)
app.add_exception_handler(PydanticValidationError, validation_error_handler)
app.add_exception_handler(Exception, general_exception_handler)

# Include routers
app.include_router(health.router)
app.include_router(claude.router)
app.include_router(openai.router)
app.include_router(process.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,  # Pass app object directly instead of string path
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=settings.node_env == "development",
    )
