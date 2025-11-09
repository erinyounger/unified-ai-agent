"""Unified logging system using structlog."""

import logging
import sys
from typing import Any

import structlog
from structlog.stdlib import LoggerFactory

from uniaiagent.config import settings


def configure_logging() -> None:
    """Configure structlog with appropriate processors."""
    # Determine if we should use pretty printing
    use_pretty = settings.node_env == "development" and sys.stderr.isatty()

    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # Add pretty printing for development
    if use_pretty:
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper(), logging.DEBUG),
    )


# Configure logging on module import
configure_logging()


def get_logger(component: str = "app") -> structlog.stdlib.BoundLogger:
    """Get a logger instance for a component."""
    return structlog.get_logger(component)


def create_request_logger(component: str, request_id: str | None = None) -> structlog.stdlib.BoundLogger:
    """Create a request-scoped logger with correlation ID."""
    import uuid

    correlation_id = request_id or str(uuid.uuid4())
    return structlog.get_logger(component).bind(correlation_id=correlation_id, request_scope=True)


class PerformanceLogger:
    """Performance timing logger utility."""

    def __init__(self, logger: structlog.stdlib.BoundLogger, operation: str) -> None:
        """Initialize performance logger."""
        import time

        self.logger = logger
        self.operation = operation
        self.start_time = time.time()

        self.logger.debug(
            operation=operation,
            phase="start",
            msg=f"Starting operation: {operation}",
        )

    def finish(self, result: str = "success", additional_data: dict[str, Any] | None = None) -> None:
        """Log operation completion with duration."""
        import time

        duration_ms = (time.time() - self.start_time) * 1000
        log_data: dict[str, Any] = {
            "operation": self.operation,
            "phase": "finish",
            "duration_ms": duration_ms,
            "result": result,
        }
        if additional_data:
            log_data.update(additional_data)

        if result == "error":
            self.logger.warn(**log_data, msg=f"Operation completed with error: {self.operation} ({duration_ms:.2f}ms)")
        else:
            self.logger.info(**log_data, msg=f"Operation completed: {self.operation} ({duration_ms:.2f}ms)")


class SecurityLogger:
    """Security logging utilities for sensitive operations."""

    def __init__(self, component: str) -> None:
        """Initialize security logger."""
        self.logger = get_logger(f"security:{component}")

    def log_authentication(
        self, user_id: str, success: bool, additional_data: dict[str, Any] | None = None
    ) -> None:
        """Log authentication attempt."""
        log_data: dict[str, Any] = {
            "user_id": self._mask_user_id(user_id),
            "success": success,
            "type": "authentication",
        }
        if additional_data:
            log_data.update(additional_data)

        if success:
            self.logger.info(**log_data, msg="Authentication successful")
        else:
            self.logger.warn(**log_data, msg="Authentication failed")

    def log_permission_check(
        self, operation: str, allowed: bool, context: dict[str, Any] | None = None
    ) -> None:
        """Log permission check."""
        log_data: dict[str, Any] = {
            "operation": operation,
            "allowed": allowed,
            "type": "permission_check",
        }
        if context:
            log_data.update(context)

        self.logger.info(
            **log_data, msg=f"Permission check: {operation} - {'ALLOWED' if allowed else 'DENIED'}"
        )

    def log_sensitive_operation(self, operation: str, details: dict[str, Any] | None = None) -> None:
        """Log sensitive operation."""
        log_data: dict[str, Any] = {"operation": operation, "type": "sensitive_operation"}
        if details:
            log_data.update(details)

        self.logger.warn(**log_data, msg=f"Sensitive operation performed: {operation}")

    @staticmethod
    def _mask_user_id(user_id: str) -> str:
        """Mask user ID for logging."""
        if len(user_id) <= 4:
            return "***"
        return user_id[:2] + "*" * (len(user_id) - 4) + user_id[-2:]


def log_health_check(
    component: str, status: str, details: dict[str, Any] | None = None
) -> None:  # type: ignore[type-arg]
    """Log health check result."""
    health_logger = get_logger(f"health:{component}")

    log_data: dict[str, Any] = {"status": status, "type": "health_check"}
    if details:
        log_data.update(details)

    if status == "healthy":
        health_logger.info(**log_data, msg=f"Health check passed: {component}")
    elif status == "degraded":
        health_logger.warn(**log_data, msg=f"Health check degraded: {component}")
    else:
        health_logger.error(**log_data, msg=f"Health check failed: {component}")


def log_process_event(
    event: str,
    process_info: dict[str, Any],
    additional_context: dict[str, Any] | None = None,
) -> None:
    """Log process lifecycle event."""
    process_logger = get_logger("process")

    log_data: dict[str, Any] = {"event": event, "type": "process_lifecycle", **process_info}
    if additional_context:
        log_data.update(additional_context)

    if event == "spawn":
        process_logger.info(**log_data, msg=f"Process spawned: {process_info.get('command')} (PID: {process_info.get('pid')})")
    elif event == "exit":
        process_logger.info(**log_data, msg=f"Process exited: PID {process_info.get('pid')} with code {process_info.get('exit_code')}")
    elif event == "error":
        process_logger.error(**log_data, msg=f"Process error: {process_info.get('error')}")
    elif event == "timeout":
        process_logger.warn(**log_data, msg=f"Process timeout: PID {process_info.get('pid')}")
    elif event == "signal":
        process_logger.info(**log_data, msg=f"Process signal: {process_info.get('signal')} to PID {process_info.get('pid')}")


# Default component loggers
server_logger = get_logger("server")
executor_logger = get_logger("executor")
mcp_logger = get_logger("mcp")
health_logger = get_logger("health")
session_logger = get_logger("session")

