"""Core business logic."""

from uniaiagent.core.claude_executor import ClaudeExecutor
from uniaiagent.core.file_processor import file_processor, FileProcessor
from uniaiagent.core.health_checker import HealthStatus, perform_health_check
from uniaiagent.core.session_manager import create_workspace

executor = ClaudeExecutor()

__all__ = [
    "executor",
    "ClaudeExecutor",
    "file_processor",
    "FileProcessor",
    "create_workspace",
    "perform_health_check",
    "HealthStatus",
]
