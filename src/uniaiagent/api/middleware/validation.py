"""Request validation middleware."""

from typing import Any

from fastapi import Request
from pydantic import ValidationError

from uniaiagent.exceptions.custom_errors import ValidationError as CustomValidationError
from uniaiagent.exceptions.types import ErrorCode, ErrorContext, ValidationErrorDetail


async def perform_custom_validation(request: Request, body: dict[str, Any]) -> None:
    """Perform custom validation logic beyond Pydantic validation."""
    validation_errors: list[ValidationErrorDetail] = []

    # Check for conflicting tool permissions
    allowed_tools = body.get("allowed-tools") or body.get("allowed_tools")
    disallowed_tools = body.get("disallowed-tools") or body.get("disallowed_tools")

    if allowed_tools and disallowed_tools:
        allowed_set = set(allowed_tools)
        conflicts = [tool for tool in disallowed_tools if tool in allowed_set]

        if conflicts:
            validation_errors.append(
                ValidationErrorDetail(
                    field="allowed-tools/disallowed-tools",
                    value=conflicts,
                    message=f"Tools cannot be both allowed and disallowed: {', '.join(conflicts)}",
                    code="conflicting_tool_permissions",
                )
            )

    # Throw validation error if any issues found
    if validation_errors:
        context = ErrorContext(
            request_id=getattr(request.state, "request_id", None),
            endpoint=str(request.url.path),
            method=request.method,
        )
        raise CustomValidationError(
            "Request validation failed",
            validation_errors,
            context,
            ErrorCode.INVALID_REQUEST,
        )
