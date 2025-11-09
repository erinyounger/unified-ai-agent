"""Custom error classes with automatic HTTP status code assignment."""

from datetime import datetime
from typing import Any

from uniaiagent.exceptions.types import (
    ErrorCode,
    ErrorContext,
    ErrorType,
    SystemErrorDetail,
    ValidationErrorDetail,
)


class BaseError(Exception):
    """Base error class for all custom errors."""

    def __init__(
        self,
        message: str,
        error_type: ErrorType,
        code: ErrorCode,
        status_code: int,
        context: ErrorContext | None = None,
        details: dict[str, Any] | None = None,
        is_operational: bool = True,
    ):
        """Initialize base error."""
        super().__init__(message)
        self.message = message
        self.type = error_type
        self.code = code
        self.status_code = status_code
        self.context = context or ErrorContext()
        self.details = details or {}
        self.is_operational = is_operational
        self.timestamp = datetime.utcnow().isoformat() + "Z"

    def to_error_response(self) -> dict[str, Any]:
        """Convert to error response format."""
        return {
            "error": {
                "message": self.message,
                "type": self.type.value,
                "code": self.code.value,
                "details": self.details,
                "requestId": self.context.request_id,
                "timestamp": self.timestamp,
            }
        }


# 400 Bad Request errors
class ValidationError(BaseError):
    """Validation error."""

    def __init__(
        self,
        message: str,
        validation_errors: list[ValidationErrorDetail] | None = None,
        context: ErrorContext | None = None,
        code: ErrorCode = ErrorCode.INVALID_REQUEST,
    ):
        """Initialize validation error."""
        details: dict[str, Any] = {}
        if validation_errors:
            details["validationErrors"] = [ve.to_dict() for ve in validation_errors]
        super().__init__(message, ErrorType.VALIDATION_ERROR, code, 400, context, details)


class InvalidRequestError(BaseError):
    """Invalid request error."""

    def __init__(
        self,
        message: str,
        context: ErrorContext | None = None,
        code: ErrorCode = ErrorCode.INVALID_REQUEST,
    ):
        """Initialize invalid request error."""
        super().__init__(message, ErrorType.VALIDATION_ERROR, code, 400, context)


# 401 Unauthorized errors
class AuthenticationError(BaseError):
    """Authentication error."""

    def __init__(
        self,
        message: str = "Authentication required",
        context: ErrorContext | None = None,
        code: ErrorCode = ErrorCode.MISSING_API_KEY,
    ):
        """Initialize authentication error."""
        super().__init__(message, ErrorType.AUTHENTICATION_ERROR, code, 401, context)


# 403 Forbidden errors
class AuthorizationError(BaseError):
    """Authorization error."""

    def __init__(
        self,
        message: str = "Insufficient permissions",
        context: ErrorContext | None = None,
        code: ErrorCode = ErrorCode.INSUFFICIENT_PERMISSIONS,
    ):
        """Initialize authorization error."""
        super().__init__(message, ErrorType.AUTHORIZATION_ERROR, code, 403, context)


# 404 Not Found errors
class NotFoundError(BaseError):
    """Not found error."""

    def __init__(
        self,
        message: str,
        context: ErrorContext | None = None,
        code: ErrorCode = ErrorCode.RESOURCE_NOT_FOUND,
    ):
        """Initialize not found error."""
        super().__init__(message, ErrorType.NOT_FOUND_ERROR, code, 404, context)


class WorkspaceNotFoundError(NotFoundError):
    """Workspace not found error."""

    def __init__(self, workspace: str, context: ErrorContext | None = None):
        """Initialize workspace not found error."""
        context = context or ErrorContext()
        context.workspace = workspace
        super().__init__(
            f"Workspace '{workspace}' not found",
            context,
            ErrorCode.WORKSPACE_NOT_FOUND,
        )


class SessionNotFoundError(NotFoundError):
    """Session not found error."""

    def __init__(self, session_id: str, context: ErrorContext | None = None):
        """Initialize session not found error."""
        context = context or ErrorContext()
        context.session_id = session_id
        super().__init__(
            f"Session '{session_id}' not found",
            context,
            ErrorCode.SESSION_NOT_FOUND,
        )


# 429 Too Many Requests errors
class RateLimitError(BaseError):
    """Rate limit error."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        context: ErrorContext | None = None,
        retry_after: int | None = None,
    ):
        """Initialize rate limit error."""
        details: dict[str, Any] = {}
        if retry_after is not None:
            details["retryAfter"] = retry_after
        super().__init__(
            message, ErrorType.RATE_LIMIT_ERROR, ErrorCode.RATE_LIMIT_EXCEEDED, 429, context, details
        )


# 500 Internal Server Error
class SystemError(BaseError):
    """System error."""

    def __init__(
        self,
        message: str,
        system_details: SystemErrorDetail,
        context: ErrorContext | None = None,
        code: ErrorCode = ErrorCode.INTERNAL_SERVER_ERROR,
    ):
        """Initialize system error."""
        super().__init__(
            message,
            ErrorType.SYSTEM_ERROR,
            code,
            500,
            context,
            {"systemDetails": system_details.to_dict()},
            is_operational=False,
        )
        self.system_details = system_details


# 503 Service Unavailable errors
class ServiceUnavailableError(BaseError):
    """Service unavailable error."""

    def __init__(
        self,
        message: str = "Service temporarily unavailable",
        context: ErrorContext | None = None,
        code: ErrorCode = ErrorCode.SERVICE_UNAVAILABLE,
    ):
        """Initialize service unavailable error."""
        super().__init__(message, ErrorType.SYSTEM_ERROR, code, 503, context)


# Claude CLI specific errors
class ClaudeCliError(BaseError):
    """Claude CLI error."""

    def __init__(
        self,
        message: str,
        context: ErrorContext | None = None,
        code: ErrorCode = ErrorCode.CLAUDE_CLI_EXECUTION_FAILED,
    ):
        """Initialize Claude CLI error."""
        status_code = 503 if code == ErrorCode.CLAUDE_CLI_NOT_FOUND else 500
        super().__init__(message, ErrorType.CLAUDE_CLI_ERROR, code, status_code, context)


class ClaudeCliNotFoundError(ClaudeCliError):
    """Claude CLI not found error."""

    def __init__(self, context: ErrorContext | None = None):
        """Initialize Claude CLI not found error."""
        super().__init__(
            "Claude CLI not found or not accessible",
            context,
            ErrorCode.CLAUDE_CLI_NOT_FOUND,
        )


class ClaudeCliTimeoutError(ClaudeCliError):
    """Claude CLI timeout error."""

    def __init__(self, timeout: int, context: ErrorContext | None = None):
        """Initialize Claude CLI timeout error."""
        context = context or ErrorContext()
        context.extra["timeout"] = timeout
        super().__init__(
            f"Claude CLI operation timed out after {timeout}ms",
            context,
            ErrorCode.CLAUDE_CLI_TIMEOUT,
        )


# Workspace specific errors
class WorkspaceError(BaseError):
    """Workspace error."""

    def __init__(
        self,
        message: str,
        context: ErrorContext | None = None,
        code: ErrorCode = ErrorCode.WORKSPACE_ACCESS_DENIED,
    ):
        """Initialize workspace error."""
        status_code = 403 if code == ErrorCode.WORKSPACE_ACCESS_DENIED else 500
        super().__init__(message, ErrorType.WORKSPACE_ERROR, code, status_code, context)


class WorkspaceAccessDeniedError(WorkspaceError):
    """Workspace access denied error."""

    def __init__(self, workspace: str, context: ErrorContext | None = None):
        """Initialize workspace access denied error."""
        context = context or ErrorContext()
        context.workspace = workspace
        super().__init__(
            f"Access denied to workspace '{workspace}'",
            context,
            ErrorCode.WORKSPACE_ACCESS_DENIED,
        )


# MCP specific errors
class McpError(BaseError):
    """MCP error."""

    def __init__(
        self,
        message: str,
        context: ErrorContext | None = None,
        code: ErrorCode = ErrorCode.MCP_CONFIG_INVALID,
    ):
        """Initialize MCP error."""
        super().__init__(message, ErrorType.MCP_ERROR, code, 500, context)


class McpConfigInvalidError(McpError):
    """MCP config invalid error."""

    def __init__(self, reason: str, context: ErrorContext | None = None):
        """Initialize MCP config invalid error."""
        super().__init__(
            f"MCP configuration is invalid: {reason}",
            context,
            ErrorCode.MCP_CONFIG_INVALID,
        )


class McpToolNotFoundError(McpError):
    """MCP tool not found error."""

    def __init__(self, tool_name: str, context: ErrorContext | None = None):
        """Initialize MCP tool not found error."""
        context = context or ErrorContext()
        context.extra["toolName"] = tool_name
        super().__init__(
            f"MCP tool '{tool_name}' not found",
            context,
            ErrorCode.MCP_TOOL_NOT_FOUND,
        )


# Stream specific errors
class StreamError(BaseError):
    """Stream error."""

    def __init__(
        self,
        message: str,
        context: ErrorContext | None = None,
        code: ErrorCode = ErrorCode.STREAM_WRITE_FAILED,
    ):
        """Initialize stream error."""
        super().__init__(message, ErrorType.STREAM_ERROR, code, 500, context)


class StreamInterruptedError(StreamError):
    """Stream interrupted error."""

    def __init__(self, reason: str, context: ErrorContext | None = None):
        """Initialize stream interrupted error."""
        context = context or ErrorContext()
        context.extra["reason"] = reason
        super().__init__(
            f"Stream was interrupted: {reason}",
            context,
            ErrorCode.STREAM_INTERRUPTED,
        )


# Configuration errors
class ConfigurationError(BaseError):
    """Configuration error."""

    def __init__(
        self,
        message: str,
        context: ErrorContext | None = None,
        code: ErrorCode = ErrorCode.INVALID_CONFIGURATION,
    ):
        """Initialize configuration error."""
        super().__init__(message, ErrorType.CONFIGURATION_ERROR, code, 500, context)


class MissingConfigurationError(ConfigurationError):
    """Missing configuration error."""

    def __init__(self, config_name: str, context: ErrorContext | None = None):
        """Initialize missing configuration error."""
        context = context or ErrorContext()
        context.extra["configName"] = config_name
        super().__init__(
            f"Missing required configuration: {config_name}",
            context,
            ErrorCode.MISSING_CONFIGURATION,
        )


# Health check errors
class HealthCheckError(BaseError):
    """Health check error."""

    def __init__(self, message: str, component: str, context: ErrorContext | None = None):
        """Initialize health check error."""
        context = context or ErrorContext()
        context.extra["component"] = component
        super().__init__(
            message,
            ErrorType.HEALTH_CHECK_ERROR,
            ErrorCode.HEALTH_CHECK_FAILED,
            503,
            context,
        )

