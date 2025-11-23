"""OpenAI compatible API endpoint."""

import asyncio
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from uniaiagent.api.middleware import authenticate_request
from uniaiagent.core import executor
from uniaiagent.core.stream_processor import StreamProcessor
from uniaiagent.exceptions.handlers import create_stream_error_response
from uniaiagent.models.types import ClaudeOptions, OpenAIRequest
from uniaiagent.services import PerformanceLogger, create_request_logger
from uniaiagent.services import OpenAITransformer

router = APIRouter()


async def stream_openai_response(
    request: OpenAIRequest,
    http_request: Request,
) -> AsyncIterator[str]:
    """Stream OpenAI compatible response."""
    # Note: stream check is done in the route handler before creating StreamingResponse
    # This function assumes stream=True

    request_logger = create_request_logger("openai-api", getattr(http_request.state, "request_id", None))
    perf_logger = PerformanceLogger(request_logger, "openai-api-request")

    # Track if we need to cleanup
    cleanup_needed = True

    try:
        # Convert OpenAI request to Claude API parameters
        converted = await OpenAITransformer.convert_request(request)
        prompt = converted["prompt"]
        system_prompt = converted["system_prompt"]
        session_info = converted["session_info"]
        file_paths = converted["file_paths"]

        request_logger.info(
            endpoint="/v1/chat/completions",
            request_data={
                "promptLength": len(prompt),
                "sessionId": session_info.get("session_id"),
                "workspace": session_info.get("workspace", "default"),
                "systemPromptLength": len(system_prompt) if system_prompt else 0,
                "dangerouslySkipPermissions": session_info.get("dangerously_skip_permissions", False),
                "allowedToolsCount": len(session_info.get("allowed_tools", [])),
                "disallowedToolsCount": len(session_info.get("disallowed_tools", [])),
                "messagesCount": len(request.messages),
                "fileCount": len(file_paths),
            },
            type="api_request",
            msg="OpenAI API request received",
        )

        # Create stream processor with thinking setting
        show_thinking = session_info.get("show_thinking", False)
        stream_processor = StreamProcessor(chunk_size=100, show_thinking=show_thinking)

        # Convert ClaudeOptions
        options = ClaudeOptions(
            workspace=session_info.get("workspace"),
            system_prompt=system_prompt,
            dangerously_skip_permissions=session_info.get("dangerously_skip_permissions"),
            allowed_tools=session_info.get("allowed_tools"),
            disallowed_tools=session_info.get("disallowed_tools"),
            skills=session_info.get("skills"),
            skill_options=session_info.get("skill_options"),
        )

        # Stream Claude response and process through stream processor
        # Collect chunks in a list first, then yield them
        # This ensures we can yield at least one response
        collected_chunks: list[str] = []
        stream_error: Exception | None = None

        def write_chunk(chunk: str) -> None:
            """Write chunk to collected chunks."""
            collected_chunks.append(chunk)

        stream_processor.set_original_write(write_chunk)

        # Process stream directly
        try:
            async for line in executor.execute_and_stream(prompt, session_info.get("session_id"), options):
                # executor returns raw lines, format as data: if needed
                if not line.startswith("data: "):
                    line = f"data: {line}"
                if not line.endswith("\n\n"):
                    line = line.rstrip() + "\n\n"

                # Process through stream processor
                continue_processing = stream_processor.process_chunk(
                    line, session_info, write_chunk
                )

                # Yield chunks as they are collected
                while collected_chunks:
                    chunk = collected_chunks.pop(0)
                    try:
                        yield chunk
                    except (RuntimeError, GeneratorExit):
                        # Client disconnected
                        request_logger.info(
                            type="client_disconnected",
                            msg="Client disconnected during streaming",
                        )
                        return

                if not continue_processing:
                    break

            # Cleanup and send final message
            stream_processor.cleanup(write_chunk)
            write_chunk("data: [DONE]\n\n")

            # Yield any remaining chunks
            while collected_chunks:
                chunk = collected_chunks.pop(0)
                try:
                    yield chunk
                except (RuntimeError, GeneratorExit):
                    # Client disconnected
                    request_logger.info(
                        type="client_disconnected",
                        msg="Client disconnected during final chunk yield",
                    )
                    return

        except asyncio.CancelledError:
            # Request was cancelled (client disconnected)
            request_logger.info(
                type="request_cancelled",
                msg="Request was cancelled (client likely disconnected)",
            )
            perf_logger.finish("cancelled")
            # Don't raise - let it close
            cleanup_needed = False
            return
        except Exception as e:
            request_logger.error(
                error=str(e),
                type="stream_processing_error",
                msg="Error in stream processing",
            )
            import traceback
            request_logger.error(
                traceback=traceback.format_exc(),
                type="stream_processing_traceback",
                msg="Stream processing traceback",
            )
            stream_error = e
            # Yield error response
            yield create_stream_error_response(e, getattr(http_request.state, "request_id", None))

        # If we got here, stream completed successfully
        cleanup_needed = False
        if stream_error:
            perf_logger.finish("error", {"error": str(stream_error)})
        else:
            perf_logger.finish("success")
    except Exception as error:
        request_logger.error(
            error=str(error),
            type="api_error",
            msg="OpenAI API request failed",
        )
        perf_logger.finish("error", {"error": str(error)})
        yield create_stream_error_response(error, getattr(http_request.state, "request_id", None))
    finally:
        # Ensure cleanup happens
        if cleanup_needed:
            request_logger.info(
                type="stream_cleanup",
                msg="Performing final cleanup",
            )


@router.post("/v1/chat/completions")
async def chat_completions(
    request: OpenAIRequest,
    http_request: Request,
    _: None = Depends(authenticate_request),
):
    """OpenAI compatible chat completions endpoint."""
    # Check streaming requirement before creating StreamingResponse
    if not request.stream:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail="Only streaming is supported. Set 'stream' to true."
        )
    
    return StreamingResponse(
        stream_openai_response(request, http_request),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )
