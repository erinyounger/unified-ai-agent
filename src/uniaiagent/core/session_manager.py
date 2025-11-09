"""Workspace management for Claude sessions."""

import os
from pathlib import Path

from uniaiagent.config import settings
from uniaiagent.services import session_logger


async def create_workspace(workspace_name: str | None = None) -> Path:
    """
    Create workspace directory for Claude session.

    Args:
        workspace_name: Custom workspace name or None for shared workspace

    Returns:
        Path to created workspace directory

    Raises:
        OSError: When workspace creation fails due to permissions or other filesystem issues
    """
    base_workspace_path = settings.workspace_base
    if workspace_name:
        workspace_path = base_workspace_path / "workspace" / workspace_name
    else:
        workspace_path = base_workspace_path / "shared_workspace"

    session_logger.debug(
        workspace_name=workspace_name or "shared",
        workspace_path=str(workspace_path),
        base_workspace_path=str(base_workspace_path),
        type="workspace_creation_start",
        msg=f"Creating workspace: {workspace_name or 'shared'}",
    )

    try:
        workspace_path.mkdir(parents=True, exist_ok=True)

        session_logger.info(
            workspace_name=workspace_name or "shared",
            workspace_path=str(workspace_path),
            type="workspace_created",
            msg=f"Workspace created successfully: {workspace_path}",
        )

        return workspace_path
    except OSError as error:
        error_code = getattr(error, "winerror", error.errno) if hasattr(error, "errno") else None
        error_message = str(error)

        error_context = {
            "workspace_name": workspace_name or "shared",
            "workspace_path": str(workspace_path),
            "error_code": error_code,
            "error_message": error_message,
            "type": "workspace_creation_error",
        }

        if error_code == os.errno.EEXIST:
            # Directory already exists - this is actually fine with exist_ok=True
            session_logger.debug(
                **error_context,
                type="workspace_already_exists",
                msg=f"Workspace already exists: {workspace_path}",
            )
            return workspace_path
        elif error_code == os.errno.EACCES:
            # Permission denied
            session_logger.error(
                **error_context,
                type="workspace_permission_denied",
                msg="Permission denied creating workspace directory",
            )
            raise OSError(
                f"Permission denied: Cannot create workspace directory at {workspace_path}. "
                "Check filesystem permissions."
            ) from error
        elif error_code == os.errno.ENOTDIR:
            # Parent is not a directory
            session_logger.error(
                **error_context,
                type="workspace_invalid_parent",
                msg="Invalid parent directory for workspace",
            )
            raise OSError(f"Invalid path: Parent of {workspace_path} is not a directory.") from error
        elif error_code == os.errno.ENOSPC:
            # No space left on device
            session_logger.error(
                **error_context,
                type="workspace_no_space",
                msg="Insufficient disk space for workspace creation",
            )
            raise OSError(
                f"Insufficient disk space: Cannot create workspace directory at {workspace_path}."
            ) from error
        else:
            # Other filesystem errors
            session_logger.error(
                **error_context,
                error=str(error),
                type="workspace_unknown_error",
                msg="Unknown error creating workspace directory",
            )
            raise OSError(
                f"Failed to create workspace directory at {workspace_path}: {error_message or 'Unknown error'}"
            ) from error

