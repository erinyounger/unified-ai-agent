"""Claude API endpoint."""

import asyncio
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from uniaiagent.api.middleware import authenticate_request
from uniaiagent.core import executor, file_processor
from uniaiagent.core.session_manager import create_workspace
from uniaiagent.exceptions.handlers import create_stream_error_response
from uniaiagent.models.types import ClaudeApiRequest, ClaudeOptions
from uniaiagent.services import PerformanceLogger, create_request_logger

router = APIRouter()


async def stream_claude_response(
    request: ClaudeApiRequest,
    http_request: Request,
) -> AsyncIterator[str]:
    """Stream Claude API response."""
    request_logger = create_request_logger("claude-api", getattr(http_request.state, "request_id", None))
    perf_logger = PerformanceLogger(request_logger, "claude-api-request")

    # Track if we need to cleanup
    cleanup_needed = True

    try:
        # Process files if provided
        final_prompt = request.prompt
        if request.files and len(request.files) > 0:
            workspace_path = await create_workspace(request.workspace)
            processed_files: list[str] = []

            for file_path in request.files:
                # Use absolute paths for Claude
                from pathlib import Path

                absolute_path = file_path
                if not Path(file_path).is_absolute():
                    absolute_path = str(workspace_path / file_path)
                processed_files.append(absolute_path)

            # Build prompt with files
            final_prompt = file_processor.build_prompt_with_files(request.prompt, processed_files)

            request_logger.info(
                type="files_processed",
                file_count=len(request.files),
                files=processed_files,
                msg=f"Files processed for Claude API: {len(processed_files)} files",
            )

        # Convert request to ClaudeOptions
        options = ClaudeOptions(
            workspace=request.workspace,
            system_prompt=request.system_prompt,
            dangerously_skip_permissions=request.dangerously_skip_permissions,
            allowed_tools=request.allowed_tools,
            disallowed_tools=request.disallowed_tools,
        )

        # Stream Claude response
        # executor returns raw lines, we format them as SSE
        async for line in executor.execute_and_stream(final_prompt, request.session_id, options):
            # Line is already a JSON string from Claude CLI
            try:
                if not line.startswith("data: "):
                    yield f"data: {line}\n\n"
                else:
                    # Already formatted
                    if not line.endswith("\n\n"):
                        yield line + "\n\n"
                    else:
                        yield line
            except (RuntimeError, GeneratorExit) as e:
                # Client disconnected
                request_logger.info(
                    type="client_disconnected",
                    error=str(e),
                    msg="Client disconnected during streaming",
                )
                # Don't raise - let it close naturally
                return

        # If we got here, stream completed successfully
        cleanup_needed = False
        perf_logger.finish("success")
    except asyncio.CancelledError:
        # Request was cancelled (client disconnected)
        request_logger.info(
            type="request_cancelled",
            msg="Request was cancelled (client likely disconnected)",
        )
        perf_logger.finish("cancelled")
        # Don't raise - let it close
        cleanup_needed = False
    except Exception as error:
        request_logger.error(
            error=str(error),
            type="api_error",
            msg="Claude API request failed",
        )
        perf_logger.finish("error", {"error": str(error)})
        # Only yield error if we haven't started streaming
        yield create_stream_error_response(error, getattr(http_request.state, "request_id", None))
    finally:
        # Ensure cleanup happens
        if cleanup_needed:
            request_logger.info(
                type="stream_cleanup",
                msg="Performing final cleanup",
            )


@router.post("/api/claude")
async def claude_api(
    request: ClaudeApiRequest,
    http_request: Request,
    _: None = Depends(authenticate_request),
):
    """Claude API endpoint."""
    return StreamingResponse(
        stream_claude_response(request, http_request),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )
