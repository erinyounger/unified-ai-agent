"""Configuration management using Pydantic Settings."""

import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Server Configuration
    port: int = Field(default=3000, description="Server port")
    host: str = Field(default="0.0.0.0", description="Server host")
    node_env: str = Field(default="development", alias="NODE_ENV", description="Environment mode")

    # Claude CLI Configuration
    claude_cli_path: Optional[str] = Field(
        default=None, alias="CLAUDE_CLI_PATH", description="Path to Claude CLI executable"
    )
    claude_total_timeout_ms: int = Field(
        default=3600000, alias="CLAUDE_TOTAL_TIMEOUT_MS", description="Total timeout for Claude processes (ms)"
    )
    claude_inactivity_timeout_ms: int = Field(
        default=300000,
        alias="CLAUDE_INACTIVITY_TIMEOUT_MS",
        description="Inactivity timeout for Claude processes (ms)",
    )
    process_kill_timeout_ms: int = Field(
        default=5000, alias="PROCESS_KILL_TIMEOUT_MS", description="Timeout before force-killing processes (ms)"
    )

    # Workspace Configuration
    workspace_base_path: str = Field(
        default=".", alias="WORKSPACE_BASE_PATH", description="Base directory for workspace creation"
    )

    # MCP Configuration
    mcp_config_path: Optional[str] = Field(
        default=None, alias="MCP_CONFIG_PATH", description="Path to MCP configuration file"
    )

    # Authentication
    api_key: Optional[str] = Field(default=None, alias="API_KEY", description="Single API key")
    api_keys: Optional[str] = Field(default=None, alias="API_KEYS", description="Multiple API keys (comma-separated)")

    # Logging
    log_level: str = Field(default="debug", alias="LOG_LEVEL", description="Logging level")

    # Get project root directory (parent of src/)
    _project_root = Path(__file__).parent.parent.parent
    _env_file_path = _project_root / ".env"

    model_config = SettingsConfigDict(
        env_file=str(_env_file_path),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def valid_api_keys(self) -> set[str]:
        """Get set of valid API keys from environment."""
        keys: set[str] = set()
        if self.api_key:
            keys.add(self.api_key)
        if self.api_keys:
            keys.update(k.strip() for k in self.api_keys.split(",") if k.strip())
        return keys

    @property
    def is_auth_enabled(self) -> bool:
        """Check if authentication is enabled."""
        return len(self.valid_api_keys) > 0

    @property
    def workspace_base(self) -> Path:
        """Get workspace base path as Path object."""
        if os.path.isabs(self.workspace_base_path):
            return Path(self.workspace_base_path)
        # Relative to project root (python directory)
        return Path(__file__).parent.parent / self.workspace_base_path

    @property
    def resolved_mcp_config_path(self) -> Optional[Path]:
        """Get resolved MCP config path."""
        if not self.mcp_config_path:
            # Default: ../mcp-config.json relative to project root
            default_path = Path(__file__).parent.parent.parent / "mcp-config.json"
            return default_path if default_path.exists() else None

        if os.path.isabs(self.mcp_config_path):
            return Path(self.mcp_config_path)
        # Relative to project root
        return Path(__file__).parent.parent.parent / self.mcp_config_path


# Global settings instance
settings = Settings()

