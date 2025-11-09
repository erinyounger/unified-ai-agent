"""OpenAI to Claude API transformation utilities."""

import base64
import re
import uuid
from pathlib import Path
from typing import Any

from uniaiagent.core import file_processor
from uniaiagent.models.types import OpenAIMessage, OpenAIRequest, SessionInfo
from uniaiagent.services import server_logger


class OpenAITransformer:
    """Handles transformation between OpenAI and Claude API formats."""

    @staticmethod
    def extract_session_info(messages: list[OpenAIMessage]) -> SessionInfo | None:
        """Extract session information from OpenAI messages."""
        result: dict[str, Any] = {}
        found_session = False

        # Start from the end and work backwards to find the most recent assistant message
        for i in range(len(messages) - 2, -1, -1):
            if messages[i].role == "assistant":
                message_content = messages[i].content
                if not isinstance(message_content, str):
                    continue  # Skip non-string content

                content = message_content

                session_match = re.search(r"(?:^|\s)session-id=([a-f0-9-]+)", content, re.MULTILINE)
                if session_match:
                    result["session_id"] = session_match.group(1)
                    found_session = True

                workspace_match = re.search(r"(?:^|\s)workspace=([^\s\n]+)", content, re.MULTILINE)
                if workspace_match:
                    result["workspace"] = workspace_match.group(1)

                danger_match = re.search(r"(?:^|\s)dangerously-skip-permissions=(\w+)", content, re.MULTILINE)
                if danger_match:
                    result["dangerously_skip_permissions"] = danger_match.group(1).lower() == "true"

                allowed_match = re.search(r"(?:^|\s)allowed-tools=\[([^\]]*)\]", content, re.MULTILINE)
                if allowed_match:
                    match_content = allowed_match.group(1).strip()
                    if match_content:
                        result["allowed_tools"] = [
                            tool.strip().strip('"\'') for tool in match_content.split(",") if tool.strip()
                        ]
                    else:
                        result["allowed_tools"] = []

                disallowed_match = re.search(r"(?:^|\s)disallowed-tools=\[([^\]]*)\]", content, re.MULTILINE)
                if disallowed_match:
                    match_content = disallowed_match.group(1).strip()
                    if match_content:
                        result["disallowed_tools"] = [
                            tool.strip().strip('"\'') for tool in match_content.split(",") if tool.strip()
                        ]
                    else:
                        result["disallowed_tools"] = []

                # Stop at the first assistant message with session info
                if found_session:
                    break

        return SessionInfo(**result) if found_session else None

    @staticmethod
    def extract_message_config(user_message: str) -> tuple[dict[str, Any], str]:
        """Extract configuration from user message."""
        config: dict[str, Any] = {}

        workspace_match = re.search(r"(?:^|\s)workspace=([^\s\n]+)", user_message, re.MULTILINE)
        if workspace_match:
            config["workspace"] = workspace_match.group(1)

        danger_match = re.search(r"(?:^|\s)dangerously-skip-permissions=(\w+)", user_message, re.MULTILINE)
        if danger_match:
            config["dangerously_skip_permissions"] = danger_match.group(1).lower() == "true"

        allowed_match = re.search(r"(?:^|\s)allowed-tools=\[([^\]]*)\]", user_message, re.MULTILINE)
        if allowed_match:
            content = allowed_match.group(1).strip()
            if content:
                config["allowed_tools"] = [tool.strip().strip('"\'') for tool in content.split(",") if tool.strip()]
            else:
                config["allowed_tools"] = []

        disallowed_match = re.search(r"(?:^|\s)disallowed-tools=\[([^\]]*)\]", user_message, re.MULTILINE)
        if disallowed_match:
            content = disallowed_match.group(1).strip()
            if content:
                config["disallowed_tools"] = [tool.strip().strip('"\'') for tool in content.split(",") if tool.strip()]
            else:
                config["disallowed_tools"] = []

        thinking_match = re.search(r"(?:^|\s)thinking=(\w+)", user_message, re.MULTILINE)
        if thinking_match:
            config["show_thinking"] = thinking_match.group(1).lower() == "true"

        # Extract prompt
        prompt_match = re.search(r'(?:^|\s)prompt="([^"]+)"', user_message, re.MULTILINE)
        if prompt_match:
            cleaned_prompt = prompt_match.group(1)
        else:
            # Remove settings from message
            cleaned_prompt = re.sub(r"(?:^|\s)workspace=[^\s\n]+", "", user_message, flags=re.MULTILINE)
            cleaned_prompt = re.sub(r"(?:^|\s)dangerously-skip-permissions=\w+", "", cleaned_prompt, flags=re.MULTILINE)
            cleaned_prompt = re.sub(r"(?:^|\s)allowed-tools=\[[^\]]*\]", "", cleaned_prompt, flags=re.MULTILINE)
            cleaned_prompt = re.sub(r"(?:^|\s)disallowed-tools=\[[^\]]*\]", "", cleaned_prompt, flags=re.MULTILINE)
            cleaned_prompt = re.sub(r"(?:^|\s)thinking=\w+", "", cleaned_prompt, flags=re.MULTILINE)
            cleaned_prompt = re.sub(r'(?:^|\s)prompt="[^"]+"', "", cleaned_prompt, flags=re.MULTILINE)
            cleaned_prompt = re.sub(r"(?:^|\s)prompt=", "", cleaned_prompt, flags=re.MULTILINE)
            cleaned_prompt = re.sub(r"\s+", " ", cleaned_prompt).strip()
            if not cleaned_prompt:
                cleaned_prompt = user_message

        return config, cleaned_prompt

    @staticmethod
    async def process_files(openai_request: OpenAIRequest, workspace_path: Path) -> list[str]:
        """Process files from OpenAI request and convert to file paths."""
        file_paths: list[str] = []

        try:
            # Process message content for files and images (only from the last user message)
            last_message = openai_request.messages[-1] if openai_request.messages else None
            if last_message and last_message.role == "user" and isinstance(last_message.content, list):
                for content_part in last_message.content:
                    if content_part.type == "image_url" and content_part.image_url:
                        # Process image_url
                        file_upload = await file_processor.process_file_input(content_part.image_url.get("url", ""))
                        file_id = str(uuid.uuid4())
                        filename = f"image_{file_id}.{OpenAITransformer._get_image_extension(content_part.image_url.get('url', ''))}"
                        file_path = workspace_path / filename

                        file_path.write_bytes(file_upload.file)
                        file_paths.append(str(file_path))

                        server_logger.info(
                            type="image_processed",
                            filename=filename,
                            source="image_url",
                            size=len(file_upload.file),
                            msg=f"Image processed from image_url: {filename}",
                        )

                    elif content_part.type == "file" and content_part.file:
                        # Process file content part
                        file_data = content_part.file.get("file_data", "")
                        filename = content_part.file.get("filename")

                        if not file_data:
                            server_logger.warn(
                                type="file_data_missing",
                                filename=filename,
                                msg="File content part missing file_data",
                            )
                            continue

                        try:
                            # Decode base64 file data
                            file_buffer = base64.b64decode(file_data)
                            file_id = str(uuid.uuid4())
                            safe_filename = filename or f"file_{file_id}"
                            file_path = workspace_path / safe_filename

                            file_path.write_bytes(file_buffer)
                            file_paths.append(str(file_path))

                            server_logger.info(
                                type="file_processed",
                                filename=safe_filename,
                                source="file_data",
                                size=len(file_buffer),
                                msg=f"File processed from file_data: {safe_filename}",
                            )
                        except Exception as error:
                            server_logger.error(
                                type="file_data_decode_error",
                                filename=filename,
                                error=str(error),
                                msg=f"Failed to decode file_data for: {filename}",
                            )
        except Exception as error:
            server_logger.error(
                type="file_processing_error",
                error=str(error),
                msg="Failed to process files from OpenAI request",
            )
            raise

        return file_paths

    @staticmethod
    def _get_image_extension(url: str) -> str:
        """Get file extension from image URL or data URL."""
        if url.startswith("data:image/"):
            match = re.search(r"data:image/([^;]+)", url)
            return match.group(1) if match else "png"

        extension = Path(url).suffix[1:].lower() if Path(url).suffix else ""
        return extension or "png"

    @staticmethod
    async def convert_request(openai_request: OpenAIRequest) -> dict[str, Any]:
        """Convert OpenAI request to Claude API parameters."""
        messages = openai_request.messages

        # Extract system prompt
        system_prompt: str | None = None
        system_prompt_config: dict[str, Any] = {}
        message_start_index = 0
        if messages and messages[0].role == "system":
            system_prompt = (
                messages[0].content
                if isinstance(messages[0].content, str)
                else file_processor.extract_text_content(messages[0].content)
            )
            message_start_index = 1

            # Extract config from system prompt for first request
            config, _ = OpenAITransformer.extract_message_config(system_prompt)
            system_prompt_config = config

        # Get the latest user message and extract text content
        last_message = messages[-1] if messages else None
        user_message = (
            file_processor.extract_text_content(last_message.content)
            if last_message
            and last_message.role == "user"
            and not isinstance(last_message.content, str)
            else (last_message.content if last_message and last_message.role == "user" else "")
        )

        # Extract session info from previous messages
        previous_session_info = OpenAITransformer.extract_session_info(messages[message_start_index:])

        # Extract config from current message
        current_config, cleaned_prompt = OpenAITransformer.extract_message_config(user_message)

        # Merge session info with precedence: current message > previous session > system prompt
        session_info_dict: dict[str, Any] = {
            **system_prompt_config,
            **(previous_session_info.model_dump(exclude_none=True) if previous_session_info else {}),
            **current_config,
        }

        # Create workspace for file processing
        # Import here to avoid circular dependency
        from uniaiagent.core.session_manager import create_workspace
        workspace_path = await create_workspace(session_info_dict.get("workspace"))

        # Process files from the request
        file_paths = await OpenAITransformer.process_files(openai_request, workspace_path)

        # Build final prompt with file paths
        final_prompt = file_processor.build_prompt_with_files(cleaned_prompt, file_paths)

        return {
            "prompt": final_prompt,
            "system_prompt": system_prompt,
            "session_info": session_info_dict,
            "file_paths": file_paths,
        }

    @staticmethod
    def format_session_info(session_info: dict[str, Any]) -> str:
        """Format session information for the thinking block."""
        info = ""

        if session_info.get("session_id"):
            info += f"session-id={session_info['session_id']}\n"
        if session_info.get("workspace"):
            info += f"workspace={session_info['workspace']}\n"
        if session_info.get("dangerously_skip_permissions") is not None:
            info += f"dangerously-skip-permissions={session_info['dangerously_skip_permissions']}\n"
        if session_info.get("allowed_tools"):
            tools_str = ",".join(f'"{tool}"' for tool in session_info["allowed_tools"])
            info += f"allowed-tools=[{tools_str}]\n"
        if session_info.get("disallowed_tools"):
            tools_str = ",".join(f'"{tool}"' for tool in session_info["disallowed_tools"])
            info += f"disallowed-tools=[{tools_str}]\n"
        if session_info.get("show_thinking") is not None:
            info += f"thinking={session_info['show_thinking']}\n"

        return info

    @staticmethod
    def create_chunk(
        message_id: str,
        content: str | None = None,
        finish_reason: str | None = None,
        role: str | None = None,
    ) -> dict[str, Any]:
        """Create an OpenAI chunk object."""
        import time

        delta: dict[str, Any] = {}

        if role:
            delta["role"] = role
        if content is not None:
            delta["content"] = content

        chunk = {
            "id": message_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "claude-code",
            "system_fingerprint": f"fp_{int(time.time() * 1000):x}",
            "choices": [
                {
                    "index": 0,
                    "delta": delta,
                    "logprobs": None,
                    "finish_reason": finish_reason or None,
                },
            ],
        }

        return chunk
