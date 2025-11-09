"""Authentication middleware for Claude Code Server."""

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from uniaiagent.config import settings
from uniaiagent.services import SecurityLogger

security = HTTPBearer(auto_error=False)
security_logger = SecurityLogger("auth")


def is_auth_enabled() -> bool:
    """Check if authentication is enabled."""
    return settings.is_auth_enabled


def authenticate_request(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> None:
    """
    FastAPI dependency for authentication.

    Args:
        credentials: HTTP Bearer token credentials

    Raises:
        HTTPException: If authentication fails
    """
    # Skip authentication if not enabled
    if not is_auth_enabled():
        security_logger.log_permission_check(
            "api_access",
            True,
            {"reason": "authentication_disabled"},
        )
        return

    if not credentials:
        security_logger.log_authentication(
            "anonymous",
            False,
            {"reason": "missing_or_invalid_bearer_token"},
        )
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Bearer token",
        )

    api_key = credentials.credentials

    if api_key not in settings.valid_api_keys:
        security_logger.log_authentication(
            api_key[:8] + "...",
            False,
            {"reason": "invalid_api_key"},
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
        )

    # Authentication successful
    security_logger.log_authentication(
        api_key[:8] + "...",
        True,
        {"keyPrefix": api_key[:8]},
    )

    security_logger.log_permission_check(
        "api_access",
        True,
        {"authenticatedKey": api_key[:8] + "..."},
    )


def get_auth_status() -> dict[str, any]:  # type: ignore[type-arg]
    """Get authentication status and configuration info."""
    valid_api_keys = settings.valid_api_keys
    enabled = len(valid_api_keys) > 0
    result: dict[str, any] = {  # type: ignore[type-arg]
        "enabled": enabled,
        "keyCount": len(valid_api_keys),
    }

    if not enabled:
        import secrets

        sample_key = f"sk-{secrets.token_hex(32)}"
        result["sampleKey"] = sample_key

    return result
