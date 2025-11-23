"""Type definitions for Claude Code Server."""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ClaudeOptions(BaseModel):
    """Claude execution options."""

    workspace: Optional[str] = None
    system_prompt: Optional[str] = Field(None, alias="system-prompt")
    dangerously_skip_permissions: Optional[bool] = Field(None, alias="dangerously-skip-permissions")
    allowed_tools: Optional[list[str]] = Field(None, alias="allowed-tools")
    disallowed_tools: Optional[list[str]] = Field(None, alias="disallowed-tools")
    skills: Optional[list[str]] = Field(None, alias="skills")
    skill_options: Optional[dict[str, Any]] = Field(None, alias="skill-options")

    class Config:
        """Pydantic config."""

        populate_by_name = True


class ClaudeApiRequest(BaseModel):
    """Claude API request model."""

    prompt: str
    session_id: Optional[str] = Field(None, alias="session-id")
    workspace: Optional[str] = None
    system_prompt: Optional[str] = Field(None, alias="system-prompt")
    dangerously_skip_permissions: Optional[bool] = Field(None, alias="dangerously-skip-permissions")
    allowed_tools: Optional[list[str]] = Field(None, alias="allowed-tools")
    disallowed_tools: Optional[list[str]] = Field(None, alias="disallowed-tools")
    skills: Optional[list[str]] = Field(None, alias="skills")
    skill_options: Optional[dict[str, Any]] = Field(None, alias="skill-options")
    files: Optional[list[str]] = None

    class Config:
        """Pydantic config."""

        populate_by_name = True


class OpenAIMessageContentItem(BaseModel):
    """OpenAI message content item."""

    type: Literal["text", "image_url", "file"]
    text: Optional[str] = None
    image_url: Optional[dict[str, str]] = None
    file: Optional[dict[str, str]] = None


class OpenAIMessage(BaseModel):
    """OpenAI message model."""

    role: Literal["system", "user", "assistant"]
    content: str | list[OpenAIMessageContentItem]


class OpenAIRequest(BaseModel):
    """OpenAI API request model."""

    model: Optional[str] = None
    messages: list[OpenAIMessage]
    stream: bool = True
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class SessionInfo(BaseModel):
    """Session information model."""

    session_id: Optional[str] = None
    workspace: Optional[str] = None
    dangerously_skip_permissions: Optional[bool] = None
    allowed_tools: Optional[list[str]] = None
    disallowed_tools: Optional[list[str]] = None
    show_thinking: Optional[bool] = None
    skills: Optional[list[str]] = None
    skill_options: Optional[dict[str, Any]] = None


# Content block types based on Anthropic SDK
class TextBlock(BaseModel):
    """Text content block."""

    type: Literal["text"] = "text"
    text: str


class ThinkingBlock(BaseModel):
    """Thinking content block."""

    type: Literal["thinking"] = "thinking"
    thinking: str


class ToolUseBlock(BaseModel):
    """Tool use content block."""

    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: dict[str, Any]


class ToolResultBlock(BaseModel):
    """Tool result content block."""

    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: str
    is_error: Optional[bool] = None


ContentBlock = TextBlock | ThinkingBlock | ToolUseBlock | ToolResultBlock


class StreamJsonData(BaseModel):
    """Stream JSON data model."""

    type: str
    subtype: Optional[str] = None
    session_id: Optional[str] = None
    message: Optional[dict[str, Any]] = None
    duration_ms: Optional[int] = None
    duration_api_ms: Optional[int] = None
    is_error: Optional[bool] = None
    num_turns: Optional[int] = None
    result: Optional[str] = None
    total_cost_usd: Optional[float] = None
    error: Optional[str | dict[str, Any]] = None

