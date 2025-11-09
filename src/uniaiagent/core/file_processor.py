"""File processing utilities for URL/Data URI handling."""

import base64
from dataclasses import dataclass
from typing import Any

import aiohttp

from uniaiagent.services import server_logger


@dataclass
class ProcessedFile:
    """Processed file data structure."""

    file: bytes
    filename: str
    content_type: str


class FileProcessor:
    """File processor for handling various file input formats."""

    @staticmethod
    def is_data_uri(url: str) -> bool:
        """Check if string is a data URI."""
        return url.startswith("data:")

    @staticmethod
    def is_http_url(url: str) -> bool:
        """Check if string is a HTTP/HTTPS URL."""
        return url.startswith("http://") or url.startswith("https://")

    @staticmethod
    def extract_content_type_from_data_uri(data_uri: str) -> str:
        """Extract content type from data URI."""
        if ";" in data_uri:
            match = data_uri.split(";")[0]
            return match.split(":")[1] if ":" in match else "application/octet-stream"
        return "application/octet-stream"

    @staticmethod
    def extract_filename_from_url(url: str) -> str:
        """Extract filename from URL."""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            pathname = parsed.path
            filename = pathname.split("/")[-1] if pathname else "unknown"
            return filename if "." in filename else f"{filename}.bin"
        except Exception:
            return "unknown.bin"

    @staticmethod
    def generate_filename_from_content_type(content_type: str) -> str:
        """Generate filename from content type."""
        extension_map: dict[str, str] = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/gif": "gif",
            "image/webp": "webp",
            "image/avif": "avif",
            "text/plain": "txt",
            "application/pdf": "pdf",
            "application/json": "json",
            "text/csv": "csv",
            "application/octet-stream": "bin",
        }

        extension = extension_map.get(content_type.split(";")[0], "bin")
        import time

        timestamp = int(time.time() * 1000)
        return f"file_{timestamp}.{extension}"

    @staticmethod
    def process_data_uri(data_uri: str) -> ProcessedFile:
        """Process data URI and convert to processed file."""
        server_logger.debug(
            type="data_uri_processing",
            data_uri_prefix=data_uri[:50] + "...",
            msg="Processing data URI",
        )

        try:
            # Extract content type
            content_type = FileProcessor.extract_content_type_from_data_uri(data_uri)

            # Extract base64 data
            if "," not in data_uri:
                raise ValueError("Invalid data URI format: missing comma separator")
            base64_data = data_uri.split(",", 1)[1]
            if not base64_data:
                raise ValueError("Invalid data URI format: missing base64 data")

            # Decode base64
            file_data = base64.b64decode(base64_data)

            # Generate filename
            filename = FileProcessor.generate_filename_from_content_type(content_type)

            result = ProcessedFile(file=file_data, filename=filename, content_type=content_type)

            server_logger.info(
                type="data_uri_processed",
                filename=filename,
                content_type=content_type,
                size=len(file_data),
                msg=f"Data URI processed: {filename}",
            )

            return result
        except Exception as error:
            server_logger.error(
                type="data_uri_error",
                error=str(error),
                msg="Failed to process data URI",
            )
            raise ValueError(f"Failed to process data URI: {error}") from error

    @staticmethod
    async def process_url(url: str) -> ProcessedFile:
        """Download file from URL and convert to processed file."""
        server_logger.debug(
            type="url_processing",
            url=url,
            msg="Processing URL",
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    response.raise_for_status()

                    # Get content
                    file_data = await response.read()

                    # Extract content type from response headers
                    content_type = response.headers.get("Content-Type", "application/octet-stream")
                    # Remove charset if present
                    content_type = content_type.split(";")[0].strip()

                    # Extract filename from URL
                    filename = FileProcessor.extract_filename_from_url(url)

                    result = ProcessedFile(file=file_data, filename=filename, content_type=content_type)

                    server_logger.info(
                        type="url_processed",
                        url=url,
                        filename=filename,
                        content_type=content_type,
                        size=len(file_data),
                        msg=f"URL processed: {filename}",
                    )

                    return result
        except Exception as error:
            server_logger.error(
                type="url_error",
                url=url,
                error=str(error),
                msg="Failed to process URL",
            )
            raise ValueError(f"Failed to download from URL: {error}") from error

    @staticmethod
    async def process_file_input(input_data: str | ProcessedFile) -> ProcessedFile:
        """Process any file input (data URI, URL, or already processed file)."""
        if isinstance(input_data, ProcessedFile):
            # Already a ProcessedFile
            return input_data

        if FileProcessor.is_data_uri(input_data):
            return FileProcessor.process_data_uri(input_data)

        if FileProcessor.is_http_url(input_data):
            return await FileProcessor.process_url(input_data)

        raise ValueError(f"Unsupported file input format: {input_data[:100]}")

    @staticmethod
    def build_prompt_with_files(user_prompt: str, file_paths: list[str]) -> str:
        """Build Claude CLI prompt with file paths."""
        if not file_paths:
            return user_prompt

        file_list = " ".join(file_paths)
        return f"Files: {file_list}\n\n{user_prompt}"

    @staticmethod
    def extract_image_urls(
        content: str | list[dict[str, Any]],
    ) -> list[str]:
        """Extract image URLs from OpenAI message content."""
        if isinstance(content, str):
            return []

        image_urls: list[str] = []
        for item in content:
            if item.get("type") == "image_url" and item.get("image_url", {}).get("url"):
                image_urls.append(item["image_url"]["url"])

        return image_urls

    @staticmethod
    def extract_text_content(content: str | list[dict[str, Any]]) -> str:
        """Extract text content from OpenAI message content."""
        if isinstance(content, str):
            return content

        text_parts: list[str] = []
        for item in content:
            if item.get("type") == "text" and item.get("text"):
                text_parts.append(item["text"])

        return "\n".join(text_parts)


# Export singleton instance
file_processor = FileProcessor()

