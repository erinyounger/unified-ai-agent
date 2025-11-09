"""Error types and enums."""

from enum import Enum
from typing import Any


class ErrorType(str, Enum):
    """Error type enumeration."""

    VALIDATION_ERROR = "validation_error"
    AUTHENTICATION_ERROR = "authentication_error"
    AUTHORIZATION_ERROR = "authorization_error"
    NOT_FOUND_ERROR = "not_found_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    SYSTEM_ERROR = "system_error"
    CLAUDE_CLI_ERROR = "claude_cli_error"
    WORKSPACE_ERROR = "workspace_error"
    MCP_ERROR = "mcp_error"
    STREAM_ERROR = "stream_error"
    CONFIGURATION_ERROR = "configuration_error"
    HEALTH_CHECK_ERROR = "health_check_error"


class ErrorCode(str, Enum):
    """Error code enumeration."""

    # Validation errors
    INVALID_REQUEST = "invalid_request"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_FIELD_VALUE = "invalid_field_value"
    INVALID_JSON = "invalid_json"

    # Authentication/Authorization errors
    MISSING_API_KEY = "missing_api_key"
    INVALID_API_KEY = "invalid_api_key"
    INSUFFICIENT_PERMISSIONS = "insufficient_permissions"

    # Resource errors
    RESOURCE_NOT_FOUND = "resource_not_found"
    WORKSPACE_NOT_FOUND = "workspace_not_found"
    SESSION_NOT_FOUND = "session_not_found"

    # Rate limiting
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"

    # System errors
    INTERNAL_SERVER_ERROR = "internal_server_error"
    SERVICE_UNAVAILABLE = "service_unavailable"
    TIMEOUT_ERROR = "timeout_error"

    # Claude CLI specific
    CLAUDE_CLI_NOT_FOUND = "claude_cli_not_found"
    CLAUDE_CLI_VERSION_MISMATCH = "claude_cli_version_mismatch"
    CLAUDE_CLI_EXECUTION_FAILED = "claude_cli_execution_failed"
    CLAUDE_CLI_TIMEOUT = "claude_cli_timeout"

    # Workspace errors
    WORKSPACE_ACCESS_DENIED = "workspace_access_denied"
    WORKSPACE_CREATION_FAILED = "workspace_creation_failed"

    # MCP errors
    MCP_CONFIG_INVALID = "mcp_config_invalid"
    MCP_SERVER_UNAVAILABLE = "mcp_server_unavailable"
    MCP_TOOL_NOT_FOUND = "mcp_tool_not_found"

    # Stream errors
    STREAM_INTERRUPTED = "stream_interrupted"
    STREAM_WRITE_FAILED = "stream_write_failed"

    # Configuration errors
    INVALID_CONFIGURATION = "invalid_configuration"
    MISSING_CONFIGURATION = "missing_configuration"

    # Health check errors
    HEALTH_CHECK_FAILED = "health_check_failed"


class ErrorResponse:
    """Standardized error response format."""

    def __init__(
        self,
        message: str,
        error_type: ErrorType,
        code: ErrorCode,
        details: dict[str, Any] | None = None,
        request_id: str | None = None,
    ):
        """Initialize error response."""
        from datetime import datetime

        self.error = {
            "message": message,
            "type": error_type.value,
            "code": code.value,
            "details": details or {},
            "requestId": request_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {"error": self.error}


class ErrorContext:
    """Error context information."""

    def __init__(
        self,
        request_id: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        workspace: str | None = None,
        endpoint: str | None = None,
        method: str | None = None,
        user_agent: str | None = None,
        client_ip: str | None = None,
        **kwargs: Any,
    ):
        """Initialize error context."""
        self.request_id = request_id
        self.user_id = user_id
        self.session_id = session_id
        self.workspace = workspace
        self.endpoint = endpoint
        self.method = method
        self.user_agent = user_agent
        self.client_ip = client_ip
        self.extra = kwargs

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result: dict[str, Any] = {
            "requestId": self.request_id,
            "userId": self.user_id,
            "sessionId": self.session_id,
            "workspace": self.workspace,
            "endpoint": self.endpoint,
            "method": self.method,
            "userAgent": self.user_agent,
            "clientIp": self.client_ip,
        }
        result.update(self.extra)
        return {k: v for k, v in result.items() if v is not None}


class ValidationErrorDetail:
    """Validation error detail."""

    def __init__(self, field: str, value: Any, message: str, code: str):
        """Initialize validation error detail."""
        self.field = field
        self.value = value
        self.message = message
        self.code = code

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "field": self.field,
            "value": self.value,
            "message": self.message,
            "code": self.code,
        }


class SystemErrorDetail:
    """System error detail."""

    def __init__(
        self,
        component: str,
        operation: str,
        original_error: str | None = None,
        stack_trace: str | None = None,
    ):
        """Initialize system error detail."""
        self.component = component
        self.operation = operation
        self.original_error = original_error
        self.stack_trace = stack_trace

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result: dict[str, Any] = {
            "component": self.component,
            "operation": self.operation,
        }
        if self.original_error:
            result["originalError"] = self.original_error
        if self.stack_trace:
            result["stackTrace"] = self.stack_trace
        return result

