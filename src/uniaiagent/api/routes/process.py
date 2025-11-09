"""External document loader endpoint."""

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from uniaiagent.api.middleware import authenticate_request
from uniaiagent.config import settings
from uniaiagent.exceptions.custom_errors import InvalidRequestError
from uniaiagent.exceptions.types import ErrorCode, ErrorContext
from uniaiagent.services import PerformanceLogger, create_request_logger

router = APIRouter()


@router.put("/process")
async def process_file(
    http_request: Request,
    _: None = Depends(authenticate_request),
):
    """External document loader endpoint for OpenWebUI integration."""
    request_logger = create_request_logger("external-doc-loader", getattr(http_request.state, "request_id", None))
    perf_logger = PerformanceLogger(request_logger, "external-doc-loader-request")

    try:
        # Get the raw body as bytes
        file_data = await http_request.body()

        if not file_data or len(file_data) == 0:
            raise InvalidRequestError(
                "No file data provided",
                ErrorContext(
                    request_id=getattr(http_request.state, "request_id", None),
                    endpoint=str(http_request.url.path),
                    method=http_request.method,
                ),
                ErrorCode.INVALID_REQUEST,
            )

        # Determine file extension from magic numbers
        try:
            import filetype

            kind = filetype.guess(file_data)
            file_extension = f".{kind.extension}" if kind else ".txt"
        except Exception:
            # Fallback to .txt if filetype detection fails
            file_extension = ".txt"

        # Create files directory in workspace base
        workspace_base_path = settings.workspace_base
        files_directory = workspace_base_path / "files"

        try:
            files_directory.mkdir(parents=True, exist_ok=True)
        except Exception as mkdir_error:
            request_logger.error(
                error=str(mkdir_error),
                files_directory=str(files_directory),
                type="directory_creation_error",
                msg="Failed to create files directory",
            )
            raise

        # Generate unique filename with UUID
        file_id = str(uuid.uuid4())
        file_name = f"{file_id}{file_extension}"
        file_path = files_directory / file_name

        # Save file to disk
        try:
            file_path.write_bytes(file_data)
        except Exception as write_error:
            request_logger.error(
                error=str(write_error),
                file_path=str(file_path),
                file_size=len(file_data),
                type="file_write_error",
                msg="Failed to write file to disk",
            )
            raise

        # Create filename for source display (without UUID for cleaner display)
        display_file_name = f"document{file_extension}"

        request_logger.info(
            type="file_saved",
            file_path=str(file_path),
            file_size=len(file_data),
            content_type=http_request.headers.get("content-type", "application/octet-stream"),
            file_id=file_id,
            display_file_name=display_file_name,
            msg=f"External document saved: {file_name}",
        )

        # Return response in OpenWebUI External Document Loader format
        response = {
            "page_content": str(file_path),
            "metadata": {
                "source": display_file_name,
            },
        }

        perf_logger.finish("success")
        return JSONResponse(content=response)
    except InvalidRequestError:
        raise
    except Exception as error:
        request_logger.error(
            error=str(error),
            type="external_doc_loader_error",
            msg="External Document Loader request failed",
        )
        perf_logger.finish("error", {"error": str(error)})
        raise
