"""Health check utilities for server monitoring."""

import asyncio
import platform
from datetime import datetime
from pathlib import Path
from typing import Any

from uniaiagent.config import settings
from uniaiagent.core.claude_executor import executor
from uniaiagent.services import health_logger, log_health_check


class HealthCheckResult:
    """Health check result data class."""

    def __init__(
        self,
        status: str,
        message: str,
        details: dict[str, Any] | None = None,
        timestamp: str | None = None,
    ):
        """Initialize health check result."""
        self.status = status
        self.message = message
        self.details = details or {}
        self.timestamp = timestamp or datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
        }


class HealthStatus:
    """Overall health status."""

    def __init__(
        self,
        status: str,
        timestamp: str,
        uptime: float,
        version: str,
        checks: dict[str, HealthCheckResult],
    ):
        """Initialize health status."""
        self.status = status
        self.timestamp = timestamp
        self.uptime = uptime
        self.version = version
        self.checks = checks

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status,
            "timestamp": self.timestamp,
            "uptime": self.uptime,
            "version": self.version,
            "checks": {k: v.to_dict() for k, v in self.checks.items()},
        }


async def resolve_claude_path() -> str | None:
    """Resolve Claude CLI executable path."""
    return await executor.resolve_claude_path()


async def check_claude_cli() -> HealthCheckResult:
    """Check if Claude CLI is available and working."""
    timestamp = datetime.utcnow().isoformat() + "Z"

    try:
        claude_path = await resolve_claude_path()
        command = claude_path or settings.claude_cli_path or "claude"

        process = await asyncio.create_subprocess_exec(
            command,
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5.0)
            exit_code = await asyncio.wait_for(asyncio.to_thread(lambda: process.returncode), timeout=0.1)

            if exit_code == 0:
                version = stdout.decode().strip() if stdout else "unknown"
                return HealthCheckResult(
                    status="healthy",
                    message="Claude CLI is available and responsive",
                    details={
                        "version": version,
                        "exitCode": exit_code,
                        "command": command,
                    },
                    timestamp=timestamp,
                )
            else:
                return HealthCheckResult(
                    status="unhealthy",
                    message="Claude CLI returned non-zero exit code",
                    details={
                        "exitCode": exit_code,
                        "stdout": stdout.decode().strip() if stdout else "",
                        "stderr": stderr.decode().strip() if stderr else "",
                        "command": command,
                    },
                    timestamp=timestamp,
                )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return HealthCheckResult(
                status="unhealthy",
                message="Claude CLI check timed out",
                details={
                    "timeout": "5000ms",
                    "command": command,
                },
                timestamp=timestamp,
            )
    except FileNotFoundError:
        error_message = "Claude CLI not found"
        suggestion = ""
        if platform.system() == "Windows":
            suggestion = (
                "On Windows, ensure Claude CLI is installed via npm (npm install -g @anthropic-ai/claude) "
                "and is in your PATH, or set CLAUDE_CLI_PATH environment variable to the full path "
                "including .cmd extension (e.g., C:\\Users\\username\\AppData\\Roaming\\npm\\claude.cmd)"
            )
        else:
            suggestion = (
                "Ensure Claude CLI is installed and available in your PATH, "
                "or set CLAUDE_CLI_PATH environment variable to the full path"
            )

        return HealthCheckResult(
            status="unhealthy",
            message="Claude CLI is not available or not working",
            details={
                "error": error_message,
                "command": settings.claude_cli_path or "claude",
                "platform": platform.system(),
                "suggestion": suggestion,
            },
            timestamp=timestamp,
        )
    except Exception as error:
        return HealthCheckResult(
            status="unhealthy",
            message="Failed to check Claude CLI",
            details={
                "error": str(error),
            },
            timestamp=timestamp,
        )


async def check_workspace() -> HealthCheckResult:
    """Check workspace directory accessibility."""
    timestamp = datetime.utcnow().isoformat() + "Z"
    base_workspace_path = settings.workspace_base

    try:
        # Check if base workspace path exists and is accessible
        if not base_workspace_path.exists():
            return HealthCheckResult(
                status="unhealthy",
                message="Workspace base path does not exist",
                details={
                    "path": str(base_workspace_path),
                },
                timestamp=timestamp,
            )

        if not base_workspace_path.is_dir():
            return HealthCheckResult(
                status="unhealthy",
                message="Workspace base path is not a directory",
                details={
                    "path": str(base_workspace_path),
                    "type": "file",
                },
                timestamp=timestamp,
            )

        # Try to create a test directory to verify write permissions
        test_dir = base_workspace_path / ".health-check-test"
        try:
            test_dir.mkdir(exist_ok=True)
            test_dir.rmdir()

            return HealthCheckResult(
                status="healthy",
                message="Workspace directory is accessible and writable",
                details={
                    "path": str(base_workspace_path),
                    "readable": True,
                    "writable": True,
                },
                timestamp=timestamp,
            )
        except OSError as write_error:
            return HealthCheckResult(
                status="degraded",
                message="Workspace directory is readable but not writable",
                details={
                    "path": str(base_workspace_path),
                    "readable": True,
                    "writable": False,
                    "writeError": str(write_error),
                },
                timestamp=timestamp,
            )
    except Exception as error:
        return HealthCheckResult(
            status="unhealthy",
            message="Workspace directory is not accessible",
            details={
                "path": str(base_workspace_path),
                "error": str(error),
            },
            timestamp=timestamp,
        )


async def check_mcp_config() -> HealthCheckResult:
    """Check MCP configuration file."""
    timestamp = datetime.utcnow().isoformat() + "Z"
    mcp_config_path = settings.resolved_mcp_config_path

    if not mcp_config_path:
        return HealthCheckResult(
            status="healthy",
            message="MCP is disabled (no configuration file found)",
            details={
                "enabled": False,
                "configPath": None,
            },
            timestamp=timestamp,
        )

    if mcp_config_path.exists():
        try:
            # Try to read and parse the config file
            import json

            config_content = mcp_config_path.read_text()
            json.loads(config_content)  # Validate JSON

            return HealthCheckResult(
                status="healthy",
                message="MCP configuration file is valid",
                details={
                    "enabled": True,
                    "configPath": str(mcp_config_path),
                },
                timestamp=timestamp,
            )
        except json.JSONDecodeError as error:
            return HealthCheckResult(
                status="degraded",
                message="MCP configuration file is invalid JSON",
                details={
                    "enabled": True,
                    "configPath": str(mcp_config_path),
                    "error": str(error),
                },
                timestamp=timestamp,
            )
        except Exception as error:
            return HealthCheckResult(
                status="degraded",
                message="MCP configuration file cannot be read",
                details={
                    "enabled": True,
                    "configPath": str(mcp_config_path),
                    "error": str(error),
                },
                timestamp=timestamp,
            )
    else:
        return HealthCheckResult(
            status="healthy",
            message="MCP is disabled (no configuration file found)",
            details={
                "enabled": False,
                "configPath": str(mcp_config_path),
            },
            timestamp=timestamp,
        )


def get_uptime() -> float:
    """Get process uptime in seconds."""
    import time

    try:
        # Try to get start time from process
        start_time = getattr(get_uptime, "_start_time", None)
        if start_time is None:
            start_time = time.time()
            setattr(get_uptime, "_start_time", start_time)
        return time.time() - start_time
    except Exception:
        return 0.0


async def get_version() -> str:
    """Get application version from pyproject.toml or __init__.py."""
    try:
        # Try to read from pyproject.toml
        pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
        if pyproject_path.exists():
            try:
                import tomli

                content = pyproject_path.read_text()
                data = tomli.loads(content)
                return data.get("tool", {}).get("poetry", {}).get("version", "unknown")
            except ImportError:
                # Fallback to simple parsing if tomli not available
                content = pyproject_path.read_text()
                for line in content.split("\n"):
                    if line.strip().startswith("version"):
                        match = __import__("re").search(r'version\s*=\s*"([^"]+)"', line)
                        if match:
                            return match.group(1)
    except Exception:
        pass

    try:
        # Try to get version from pyproject.toml
        import tomli
        pyproject_path = Path(__file__).parent.parent.parent.parent / "pyproject.toml"
        if pyproject_path.exists():
            with open(pyproject_path, "rb") as f:
                pyproject = tomli.load(f)
                return pyproject.get("project", {}).get("version", "0.7.1")
    except Exception:
        pass
    return "0.7.1"  # Fallback version


async def perform_health_check() -> HealthStatus:
    """Perform comprehensive health check."""
    timestamp = datetime.utcnow().isoformat() + "Z"

    health_logger.debug(
        type="health_check_start",
        msg="Starting comprehensive health check",
    )

    # Run all checks in parallel
    claude_cli, workspace, mcp_config, version = await asyncio.gather(
        check_claude_cli(),
        check_workspace(),
        check_mcp_config(),
        get_version(),
    )

    # Log individual check results
    log_health_check("claude-cli", claude_cli.status, {
        "message": claude_cli.message,
        "details": claude_cli.details,
    })

    log_health_check("workspace", workspace.status, {
        "message": workspace.message,
        "details": workspace.details,
    })

    log_health_check("mcp-config", mcp_config.status, {
        "message": mcp_config.message,
        "details": mcp_config.details,
    })

    # Determine overall status
    checks = {
        "claudeCli": claude_cli,
        "workspace": workspace,
        "mcpConfig": mcp_config,
    }
    statuses = [check.status for check in checks.values()]

    if "unhealthy" in statuses:
        overall_status = "unhealthy"
    elif "degraded" in statuses:
        overall_status = "degraded"
    else:
        overall_status = "healthy"

    # Log overall health status
    health_logger.info(
        overall_status=overall_status,
        check_results={
            "claudeCli": claude_cli.status,
            "workspace": workspace.status,
            "mcpConfig": mcp_config.status,
        },
        uptime=get_uptime(),
        version=version,
        type="health_check_complete",
        msg=f"Health check completed with status: {overall_status}",
    )

    return HealthStatus(
        status=overall_status,
        timestamp=timestamp,
        uptime=get_uptime(),
        version=version,
        checks=checks,
    )
