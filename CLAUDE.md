# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start

### Installation

```bash
# Using uv (recommended)
cd python
uv sync

# Or using pip
pip install -r requirements-dev.txt
```

### Running the Server

```bash
# Development mode
uv run uvicorn src.main:app --host 0.0.0.0 --port 3000 --reload

# Production mode
uvicorn src.main:app --host 0.0.0.0 --port 3000
```

### API Endpoints

- **GET** `/health` - Health check (public)
- **POST** `/v1/chat/completions` - OpenAI-compatible streaming API
- **POST** `/api/claude` - Native Claude API
- **PUT** `/process` - File upload for OpenWebUI integration

## Development Commands

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_api_health.py -v

# Run in watch mode
pytest -f
```

### Code Quality

```bash
# Format code
black src/ tests/

# Lint and auto-fix
ruff check --fix src/ tests/

# Type checking
mypy src/

# Run all checks
black src/ tests/ && ruff check --fix src/ tests/ && mypy src/
```

## Architecture Overview

This is a Python 3.11+ FastAPI application that proxies requests to the Claude Code CLI. It provides both native and OpenAI-compatible API endpoints with streaming support.

### Core Components

**API Layer** (`src/uniaiagent/api/`)
- `routes/openai.py` - OpenAI-compatible endpoint (`/v1/chat/completions`)
- `routes/claude.py` - Native Claude endpoint (`/api/claude`)
- `routes/health.py` - Health check (`/health`)
- `routes/process.py` - File upload (`/process`)
- `middleware/` - Authentication and request validation

**Core Services** (`src/uniaiagent/core/`)
- `claude_executor.py` - Manages Claude CLI process execution, timeouts, and streaming
- `session_manager.py` - Creates and manages isolated workspaces per session
- `health_checker.py` - Monitors Claude CLI availability, workspace access, and MCP config
- `stream_processor.py` - Transforms Claude output to OpenAI SSE format
- `file_processor.py` - Handles file uploads and path resolution

**Transformers** (`src/uniaiagent/services/`)
- `openai_transformer.py` - Converts OpenAI requests to Claude format, extracts session info from message content

**Models & Configuration** (`src/uniaiagent/`)
- `config.py` - Pydantic settings for environment variables
- `models/types.py` - Pydantic models for API requests/responses

### Key Design Patterns

1. **Streaming Architecture**: All endpoints use Server-Sent Events (SSE) for real-time responses
2. **Session Management**: Workspaces are isolated per session, supporting custom workspace names
3. **Dual API Design**: Both native and OpenAI-compatible endpoints route to the same executor
4. **Structured Logging**: Uses `structlog` for JSON-formatted, request-correlated logs
5. **Parameter Extraction**: OpenAI endpoint extracts config from message content (e.g., `workspace=name`, `session-id=xxx`)

### Request Flow

**OpenAI Endpoint**:
1. Request → `openai_transformer.py` converts to Claude format
2. Extracts session info from message content (workspace, allowed-tools, etc.)
3. Calls `claude_executor.py` to spawn Claude CLI process
4. Streams output through `stream_processor.py` to OpenAI SSE format
5. Response → Server-Sent Events

**Native Endpoint**:
1. Request with direct Claude parameters
2. Calls `claude_executor.py` directly
3. Streams raw Claude JSON output
4. Response → Server-Sent Events

### Configuration

Key environment variables (see `src/uniaiagent/config.py`):
- `PORT` (3000) - Server port
- `HOST` (0.0.0.0) - Server host
- `CLAUDE_CLI_PATH` - Path to Claude CLI (auto-detected if not set)
- `API_KEY` - Single API key (optional, disables auth if not set)
- `API_KEYS` - Multiple API keys, comma-separated
- `CLAUDE_TOTAL_TIMEOUT_MS` (3600000) - Total process timeout
- `CLAUDE_INACTIVITY_TIMEOUT_MS` (300000) - Inactivity timeout
- `WORKSPACE_BASE_PATH` (.) - Base directory for workspaces
- `MCP_CONFIG_PATH` - MCP server configuration
- `LOG_LEVEL` (debug) - Logging level
- `NODE_ENV` (development) - Environment mode

## Testing Strategy

### Test Structure
- `conftest.py` - Test client fixtures
- `test_api_health.py` - Health endpoint tests
- `test_functional_comparison.py` - Compares Python vs TypeScript version behavior
- `api_request_test.py` - API endpoint tests

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test
pytest tests/test_api_health.py::test_health_endpoint -v

# Run with coverage report
pytest --cov=src --cov-report=term-missing --cov-report=html

# Run async tests
pytest tests/ -v --asyncio-mode=auto
```

## Key Implementation Details

### Session Recovery
The OpenAI endpoint supports session recovery by extracting `session-id` from assistant message content:
```python
# Response contains: session-id=abc-123-def
# Next request includes: {"role": "assistant", "content": "session-id=abc-123-def"}
```

### Parameter Extraction
Config is extracted from message content using regex (see `openai_transformer.py:72-100`):
- `workspace=name` - Custom workspace
- `session-id=xxx` - Session recovery
- `allowed-tools=["read_file","write_file"]` - Tool permissions
- `thinking=true|false` - Thinking visualization

### File Support
- 200+ file formats via `python-magic` and `filetype`
- Files uploaded via `/process` endpoint are saved to workspace with UUID names
- Absolute file paths sent to Claude for processing

### Error Handling
- Custom exceptions in `src/uniaiagent/exceptions/`
- Structured error responses with `error`, `type`, `code` fields
- SSE errors: `data: {"type":"error","error":{...}}`

## Common Development Tasks

### Adding a New API Endpoint
1. Create route in `src/uniaiagent/api/routes/`
2. Register router in `src/main.py`
3. Add request/response models in `src/uniaiagent/models/types.py`
4. Add tests in `tests/`

### Modifying Stream Processing
- Edit `src/uniaiagent/core/stream_processor.py`
- Handles transformation from Claude JSON to OpenAI SSE format
- Manages thinking blocks and code block formatting

### Changing Authentication
- Modify `src/uniaiagent/api/middleware/auth.py`
- Auth status checked on startup (see `src/main.py:29`)
- Supports single or multiple API keys via environment variables

### Workspace Management
- Controlled by `src/uniaiagent/core/session_manager.py`
- Creates `{WORKSPACE_BASE}/{workspace_name}/shared_workspace/`
- Default workspace: `shared`

## Integration Notes

### OpenAI Client Compatibility
The `/v1/chat/completions` endpoint is compatible with OpenAI client libraries:
```python
from openai import OpenAI
client = OpenAI(api_key="sk-...", base_url="http://localhost:3000/v1")
```

### MCP Integration
- MCP config loaded from `mcp-config.json` (relative to project root)
- Path configurable via `MCP_CONFIG_PATH` env var
- Passed to Claude CLI via `--mcp-config` flag

### Process Management
- Uses `asyncio.subprocess` for async process execution
- Active processes tracked in `claude_executor.py:31`
- Cleanup on application shutdown (see `src/main.py:61`)
