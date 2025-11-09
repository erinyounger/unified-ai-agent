"""Stream processing utilities for OpenAI-compatible streaming."""

import json
from typing import Any

from uniaiagent.models.types import StreamJsonData
from uniaiagent.services import get_logger
# Import will be done later to avoid circular dependency

logger = get_logger("stream-processor")


def is_text_block(block: dict[str, Any]) -> bool:
    """Type guard for text block."""
    return isinstance(block, dict) and block.get("type") == "text"


def is_thinking_block(block: dict[str, Any]) -> bool:
    """Type guard for thinking block."""
    return isinstance(block, dict) and block.get("type") == "thinking"


def is_tool_use_block(block: dict[str, Any]) -> bool:
    """Type guard for tool use block."""
    return isinstance(block, dict) and block.get("type") == "tool_use"


def is_tool_result_block(block: dict[str, Any]) -> bool:
    """Type guard for tool result block."""
    return isinstance(block, dict) and block.get("type") == "tool_result"


class StreamProcessor:
    """Handles Claude CLI stream processing and conversion to OpenAI format."""

    def __init__(self, chunk_size: int = 100, show_thinking: bool = False):
        """Initialize stream processor."""
        self.in_thinking = False
        self.session_printed = False
        self.message_id = f"chatcmpl-{int(__import__('time').time() * 1000)}"
        self.chunk_size = chunk_size
        self.show_thinking = show_thinking
        self.original_write = None

    def set_original_write(self, original_write: Any) -> None:
        """Set the original write method to avoid infinite loops."""
        self.original_write = original_write

    def escape_nested_code_blocks(self, content: str) -> str:
        """Escape nested code blocks in content to prevent breaking outer code blocks."""
        return content.replace("```", "` ` `")

    def split_into_chunks(self, text: str) -> list[str]:
        """Split text into chunks for streaming."""
        chunks: list[str] = []
        for i in range(0, len(text), self.chunk_size):
            chunks.append(text[i : i + self.chunk_size])
        return chunks

    def send_chunk(
        self,
        write_func: Any,
        content: str | None = None,
        finish_reason: str | None = None,
        role: str | None = None,
    ) -> None:
        """Send a chunk to the stream."""
        try:
            # Import here to avoid circular dependency
            from uniaiagent.services import OpenAITransformer
            
            chunk = OpenAITransformer.create_chunk(self.message_id, content, finish_reason, role)
            chunk_str = f"data: {json.dumps(chunk)}\n\n"
            if self.original_write:
                self.original_write(chunk_str)
            else:
                write_func(chunk_str)
        except Exception as error:
            logger.error(
                error=str(error),
                type="chunk_write_error",
                msg="Failed to write chunk to stream",
            )
            import traceback
            logger.error(
                traceback=traceback.format_exc(),
                type="chunk_write_traceback",
                msg="Chunk write error traceback",
            )

    def process_system_init(
        self,
        json_data: StreamJsonData,
        session_info: dict[str, Any],
        write_func: Any,
    ) -> None:
        """Process system initialization message."""
        session_id = json_data.session_id
        if session_id and not self.session_printed:
            self.session_printed = True

            # Build session info content
            from uniaiagent.services import OpenAITransformer
            formatted_session_info = OpenAITransformer.format_session_info({
                **session_info,
                "session_id": session_id,
            })

            # Send initial chunk with role
            self.send_chunk(write_func, None, None, "assistant")

            # Send session info in chunks
            chunks = self.split_into_chunks(formatted_session_info)
            for chunk in chunks:
                self.send_chunk(write_func, chunk)

    def process_assistant_message(
        self,
        json_data: StreamJsonData,
        write_func: Any,
    ) -> None:
        """Process assistant message."""
        message = json_data.message or {}
        content = message.get("content", [])
        stop_reason = message.get("stop_reason")
        is_final_response = stop_reason == "end_turn"

        for item in content:
            if is_text_block(item):
                # Close thinking when text content arrives
                if self.in_thinking:
                    if self.show_thinking:
                        self.send_chunk(write_func, "\n</thinking>\n")
                    self.in_thinking = False

                text_content = item.get("text", "")
                full_text = f"\n{text_content}"
                chunks = self.split_into_chunks(full_text)
                for i, chunk in enumerate(chunks):
                    finish = "stop" if (i == len(chunks) - 1 and is_final_response) else None
                    self.send_chunk(write_func, chunk, finish)

            elif is_thinking_block(item):
                # Always process thinking content
                thinking_content = item.get("thinking", "")

                if self.show_thinking:
                    if not self.in_thinking:
                        self.send_chunk(write_func, "\n<thinking>\n")
                        self.in_thinking = True
                    full_text = f"\n💭 {thinking_content}\n\n"
                else:
                    full_text = f"\n```💭 Thinking\n{self.escape_nested_code_blocks(thinking_content)}\n```\n\n"

                chunks = self.split_into_chunks(full_text)
                for chunk in chunks:
                    self.send_chunk(write_func, chunk)

            elif is_tool_use_block(item):
                # Always process tool use content
                tool_name = item.get("name", "")
                tool_input = json.dumps(item.get("input", {}))

                if self.show_thinking:
                    if not self.in_thinking:
                        self.send_chunk(write_func, "\n<thinking>\n")
                        self.in_thinking = True
                    full_text = f"\n🔧 Using {tool_name}: {tool_input}\n\n"
                else:
                    full_text = f"\n```🔧 Tool use ({tool_name})\nUsing {tool_name}: {self.escape_nested_code_blocks(tool_input)}\n```\n\n"

                chunks = self.split_into_chunks(full_text)
                for chunk in chunks:
                    self.send_chunk(write_func, chunk)

        # Send empty delta with finish_reason for final response
        if is_final_response and all(not is_text_block(item) for item in content):
            # Close thinking if still open at end of final response
            if self.in_thinking:
                if self.show_thinking:
                    self.send_chunk(write_func, "\n</thinking>\n")
                self.in_thinking = False

            self.send_chunk(write_func, None, "stop")

    def process_user_message(
        self,
        json_data: StreamJsonData,
        write_func: Any,
    ) -> None:
        """Process user message (tool results)."""
        message = json_data.message or {}
        content = message.get("content", [])

        for item in content:
            if is_tool_result_block(item):
                # Always process tool result content
                tool_content = item.get("content", "")
                is_error = item.get("is_error", False)
                prefix = "\n❌ Tool Error: " if is_error else "\n✅ Tool Result: "

                if self.show_thinking:
                    if not self.in_thinking:
                        self.send_chunk(write_func, "\n<thinking>\n")
                        self.in_thinking = True
                    full_text = prefix + tool_content + "\n\n"
                else:
                    result_icon = "❌" if is_error else "✅"
                    result_type = "Tool Error" if is_error else "Tool Result"
                    full_text = f"\n```{result_icon} {result_type}\n{self.escape_nested_code_blocks(tool_content)}\n```\n\n"

                chunks = self.split_into_chunks(full_text)
                for chunk in chunks:
                    self.send_chunk(write_func, chunk)

    def process_success_result(self, write_func: Any) -> None:
        """Process success result."""
        # Close thinking block if still open
        if self.in_thinking:
            if self.show_thinking:
                self.send_chunk(write_func, "\n</thinking>\n")
            self.in_thinking = False

        # Send final chunk with stop reason
        self.send_chunk(write_func, None, "stop")

    def process_error(
        self,
        json_data: StreamJsonData,
        write_func: Any,
    ) -> None:
        """Process error message."""
        if self.in_thinking:
            if self.show_thinking:
                self.send_chunk(write_func, "\n</thinking>\n")
            self.in_thinking = False

        if isinstance(json_data.error, str):
            error_message = json_data.error
        elif isinstance(json_data.error, dict):
            error_message = json_data.error.get("message", str(json_data.error))
        elif json_data.error:
            error_message = str(json_data.error)
        else:
            error_message = "Unknown error"

        full_text = (
            f"⚠️ {error_message}\n\n"
            if self.show_thinking
            else f"\n```⚠️ Error\n{self.escape_nested_code_blocks(error_message)}\n```\n\n"
        )
        chunks = self.split_into_chunks(full_text)
        for i, chunk in enumerate(chunks):
            finish = "stop" if i == len(chunks) - 1 else None
            self.send_chunk(write_func, chunk, finish)

    def process_unknown(
        self,
        json_data: StreamJsonData,
        write_func: Any,
    ) -> None:
        """Process unknown message type."""
        data_dict = json_data.model_dump()
        logger.warn(
            unknown_type=json_data.type,
            data=data_dict,
            type="unknown_json_type",
            msg=f"Received unknown JSON data type: {json_data.type}",
        )

        # Always process unknown data for debugging
        unknown_content = f"Unknown data type '{json_data.type}': {json.dumps(data_dict, indent=2)}"
        unknown_text = (
            f"\n🔍 {unknown_content}\n\n"
            if self.show_thinking
            else f"\n```🔍 Debug\n{self.escape_nested_code_blocks(unknown_content)}\n```\n\n"
        )

        if self.show_thinking:
            if not self.in_thinking:
                self.send_chunk(write_func, "\n<thinking>\n")
                self.in_thinking = True

        chunks = self.split_into_chunks(unknown_text)
        for chunk in chunks:
            self.send_chunk(write_func, chunk)

    def process_chunk(
        self,
        chunk: bytes | str,
        session_info: dict[str, Any],
        write_func: Any,
    ) -> bool:
        """Process a single data chunk from Claude CLI."""
        chunk_str = chunk.decode() if isinstance(chunk, bytes) else chunk
        if not chunk_str.startswith("data: "):
            return True

        try:
            json_str = chunk_str.replace("data: ", "").strip()
            if not json_str:
                return True

            json_data_dict = json.loads(json_str)
            # Create StreamJsonData with flexible parsing
            json_data = StreamJsonData.model_validate(json_data_dict)

            if json_data.type == "system" and json_data.subtype == "init":
                self.process_system_init(json_data, session_info, write_func)
            elif json_data.type == "assistant":
                self.process_assistant_message(json_data, write_func)
            elif json_data.type == "user":
                self.process_user_message(json_data, write_func)
            elif json_data.type == "result" and json_data.subtype == "success":
                self.process_success_result(write_func)
                return False  # Signal end of stream
            elif json_data.type == "error":
                self.process_error(json_data, write_func)
            else:
                self.process_unknown(json_data, write_func)
        except Exception as error:
            logger.error(
                error=str(error),
                chunk=chunk_str[:100] + "..." if len(chunk_str) > 100 else chunk_str,
                type="json_parse_error",
                msg="Failed to parse JSON data",
            )
            import traceback
            logger.error(
                traceback=traceback.format_exc(),
                type="json_parse_traceback",
                msg="JSON parse error traceback",
            )

        return True  # Continue processing

    def cleanup(self, write_func: Any) -> None:
        """Clean up any open thinking blocks."""
        if self.in_thinking:
            if self.show_thinking:
                self.send_chunk(write_func, "\n</thinking>\n")
            self.in_thinking = False
