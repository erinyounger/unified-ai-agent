"""FastAPI exception handlers."""

import traceback
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError

from uniaiagent.config import settings
from uniaiagent.exceptions.custom_errors import BaseError
from uniaiagent.exceptions.types import ErrorContext, ErrorCode, ErrorType
from uniaiagent.services import get_logger

logger = get_logger("error-handler")


def extract_request_context(request: Request) -> ErrorContext:
    """Extract request context for error reporting."""
    return ErrorContext(
        request_id=getattr(request.state, "request_id", None),
        endpoint=str(request.url.path),
        method=request.method,
        user_agent=request.headers.get("user-agent"),
        client_ip=request.client.host if request.client else None,
    )


def create_error_response(
    error: BaseError, context: ErrorContext, include_stack: bool = False
) -> dict[str, Any]:
    """Create standardized error response."""
    response: dict[str, Any] = {
        "error": {
            "message": error.message,
            "type": error.type.value,
            "code": error.code.value,
            "requestId": context.request_id or error.context.request_id,
            "timestamp": error.timestamp,
        }
    }

    # Add details if available
    if error.details:
        response["error"]["details"] = mask_sensitive_details(error.details) if not include_stack else error.details

    # Add stack trace in development
    if include_stack and hasattr(error, "__traceback__"):
        stack = "".join(traceback.format_tb(error.__traceback__))
        if "details" not in response["error"]:
            response["error"]["details"] = {}
        response["error"]["details"]["stack"] = stack

    return response


def mask_sensitive_details(details: dict[str, Any]) -> dict[str, Any]:
    """Mask sensitive data in error details."""
    masked: dict[str, Any] = {}
    sensitive_keys = ["password", "token", "key", "secret", "authorization", "api_key"]

    for key, value in details.items():
        if any(sensitive in key.lower() for sensitive in sensitive_keys):
            masked[key] = "[REDACTED]"
        elif isinstance(value, dict):
            masked[key] = mask_sensitive_details(value)
        else:
            masked[key] = value

    return masked


async def base_error_handler(request: Request, exc: BaseError) -> JSONResponse:
    """Handle custom BaseError instances."""
    context = extract_request_context(request)
    error_response = create_error_response(
        exc, context, include_stack=settings.node_env == "development"
    )

    # Log error
    if exc.status_code >= 500:
        logger.error(
            error=exc.message,
            type=exc.type.value,
            code=exc.code.value,
            status_code=exc.status_code,
            is_operational=exc.is_operational,
            context=context.to_dict(),
            details=mask_sensitive_details(exc.details) if exc.details else {},
            msg=f"{exc.type.value}: {exc.message}",
        )
    else:
        logger.warn(
            error=exc.message,
            type=exc.type.value,
            code=exc.code.value,
            status_code=exc.status_code,
            is_operational=exc.is_operational,
            context=context.to_dict(),
            details=mask_sensitive_details(exc.details) if exc.details else {},
            msg=f"{exc.type.value}: {exc.message}",
        )

    return JSONResponse(status_code=exc.status_code, content=error_response)


async def validation_error_handler(request: Request, exc: PydanticValidationError) -> JSONResponse:
    """Handle Pydantic validation errors."""
    from uniaiagent.exceptions.custom_errors import ValidationError
    from uniaiagent.exceptions.types import ValidationErrorDetail

    context = extract_request_context(request)
    validation_errors = [
        ValidationErrorDetail(
            field=".".join(str(loc) for loc in error["loc"]),
            value=error.get("input"),
            message=error["msg"],
            code=error["type"],
        )
        for error in exc.errors()
    ]

    validation_error = ValidationError(
        message="Validation error",
        validation_errors=validation_errors,
        context=context,
    )

    return await base_error_handler(request, validation_error)


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    from uniaiagent.exceptions.custom_errors import SystemError
    from uniaiagent.exceptions.types import SystemErrorDetail

    context = extract_request_context(request)
    system_details = SystemErrorDetail(
        component="unknown",
        operation="request_processing",
        original_error=str(exc),
        stack_trace=traceback.format_exc(),
    )

    system_error = SystemError(
        message="An unexpected error occurred" if settings.node_env != "development" else str(exc),
        system_details=system_details,
        context=context,
    )

    return await base_error_handler(request, system_error)


def create_stream_error_response(error: Exception | BaseError, request_id: str | None = None) -> str:
    """Create error response for streaming endpoints."""
    import json
    
    if isinstance(error, BaseError):
        error_response = {
            "type": "error",
            "error": {
                "message": error.message,
                "type": error.type.value,
                "code": error.code.value,
                "timestamp": error.timestamp,
            },
        }
    else:
        error_response = {
            "type": "error",
            "error": {
                "message": str(error),
                "type": ErrorType.SYSTEM_ERROR.value,
                "code": ErrorCode.INTERNAL_SERVER_ERROR.value,
            },
        }

    if request_id:
        error_response["error"]["requestId"] = request_id

    return f"data: {json.dumps(error_response)}\n\n"

