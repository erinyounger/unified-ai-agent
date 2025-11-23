# UniAiAgent

## 功能特性

- ✅ **流式 API**: 实时 Claude Code 响应（Server-Sent Events）
- ✅ **文件支持**: 支持 200+ 文件格式
- ✅ **认证**: Bearer token 认证（OpenAI 兼容）
- ✅ **健康监控**: 内置健康检查端点
- ✅ **工作区管理**: 隔离的工作区，支持自定义命名
- ✅ **系统提示**: 支持自定义系统提示
- ✅ **MCP 支持**: Model Context Protocol 集成
- ✅ **会话管理**: 恢复 Claude Code 会话
- ✅ **OpenAI API 兼容**: 完全兼容 OpenAI chat completions API
- ✅ **权限控制**: 细粒度的工具权限管理
- ✅ **Thinking 可视化**: 代码块格式和 thinking 标签切换
- ✅ **结构化日志**: 完整的日志记录，包含安全和性能监控

## 技术栈

- **Python 3.11+**
- **FastAPI** - 现代、快速的 Web 框架
- **Uvicorn** - ASGI 服务器
- **Pydantic** - 数据验证和设置管理
- **structlog** - 结构化日志
- **aiohttp** - 异步 HTTP 客户端

## 安装

详细安装说明请查看 [INSTALLATION.md](./INSTALLATION.md)。

### 使用 uv（推荐，最快）

```bash
cd python
uv sync
```

### 使用 Poetry

```bash
cd python
poetry install
```

### 使用 pip

```bash
cd python
pip install -r requirements.txt
```

## 配置

1. 复制环境变量示例文件：

```bash
cp .env.example .env
```

2. 编辑 `.env` 文件，设置你的配置：

```bash
# 必需：Claude CLI 路径（如果不在 PATH 中）
CLAUDE_CLI_PATH=/path/to/claude

# 可选：API 密钥（用于生产环境）
API_KEY=sk-your-api-key-here
```

## 运行

### 开发模式

```bash
# 使用 uv（推荐）
uv run uvicorn src.main:app --host 0.0.0.0 --port 3000

# 使用 Poetry
poetry run uvicorn src.main:app --host 0.0.0.0 --port 3000

# 或使用 pip（需要先激活虚拟环境）
uvicorn src.main:app --host 0.0.0.0 --port 3000
```

### 生产模式

```bash
uvicorn src.main:app --host 0.0.0.0 --port 3000
```

服务器将在 `http://localhost:3000` 启动（默认端口 3000）。

## API 接口文档

所有 API 端点都支持 Bearer Token 认证（通过 `Authorization` 请求头）。如果未设置 `API_KEY` 环境变量，认证将被禁用。

### 1. 健康检查端点

#### GET /health

检查服务健康状态，包括 Claude CLI 可用性、工作区访问性和 MCP 配置。

**请求示例：**

```bash
curl http://localhost:3000/health
```

**响应格式：**

```json
{
  "status": "healthy",
  "timestamp": "2025-11-07T13:36:37.189063Z",
  "uptime": 1234.56,
  "version": "0.7.1",
  "checks": {
    "claudeCli": {
      "status": "healthy",
      "message": "Claude CLI is available and responsive",
      "details": {
        "version": "2.0.34 (Claude Code)",
        "exitCode": 0,
        "command": "claude"
      },
      "timestamp": "2025-11-07T13:36:37.189732Z"
    },
    "workspace": {
      "status": "healthy",
      "message": "Workspace directory is accessible and writable",
      "details": {
        "path": "/path/to/workspace",
        "readable": true,
        "writable": true
      },
      "timestamp": "2025-11-07T13:36:37.192782Z"
    },
    "mcpConfig": {
      "status": "healthy",
      "message": "MCP is disabled (no configuration file found)",
      "details": {
        "enabled": false,
        "configPath": null
      },
      "timestamp": "2025-11-07T13:36:37.193263Z"
    }
  }
}
```

**状态码：**

- `200 OK`: 服务健康
- `503 Service Unavailable`: 服务不健康

---

### 2. OpenAI 兼容端点

#### POST /v1/chat/completions

提供与 OpenAI Chat Completions API 完全兼容的接口，支持流式响应。

**⚠️ 重要：** 此端点**仅支持流式响应**（`stream=true`）。非流式请求将返回 400 错误。

**请求头：**

```
Authorization: Bearer <your-api-key>
Content-Type: application/json
```

**请求体：**

```json
{
  "model": "MiniMax-M2",
  "messages": [
    {
      "role": "system",
      "content": "你是一个友好的助手。"
    },
    {
      "role": "user",
      "content": "你好，请介绍一下你自己。"
    }
  ],
  "stream": true,
  "temperature": 0.7,
  "max_tokens": 1000
}
```

**参数说明：**

| 参数          | 类型    | 必填 | 说明                                              |
| ------------- | ------- | ---- | ------------------------------------------------- |
| `model`       | string  | 否   | 模型名称（忽略，仅用于兼容性）                    |
| `messages`    | array   | 是   | 消息列表，支持 `system`、`user`、`assistant` 角色 |
| `stream`      | boolean | 是   | **必须为 `true`**，非流式请求将返回错误           |
| `temperature` | number  | 否   | 温度参数（当前未使用）                            |
| `max_tokens`  | number  | 否   | 最大 token 数（当前未使用）                       |

**响应格式（Server-Sent Events）：**

```
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1234567890,"model":"MiniMax-M2","choices":[{"index":0,"delta":{"content":"你好"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1234567890,"model":"MiniMax-M2","choices":[{"index":0,"delta":{"content":"，我是"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1234567890,"model":"MiniMax-M2","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

**Python 示例：**

```python
from openai import OpenAI

client = OpenAI(
    api_key="your-api-key",
    base_url="http://localhost:3000/v1"
)

messages = [
    {"role": "system", "content": "你是一个友好的助手。"},
    {"role": "user", "content": "你好，请介绍一下你自己。"}
]

stream = client.chat.completions.create(
    model="MiniMax-M2",
    messages=messages,
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content is not None:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

**cURL 示例：**

```bash
curl -X POST http://localhost:3000/v1/chat/completions \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "MiniMax-M2",
    "messages": [
      {"role": "user", "content": "你好"}
    ],
    "stream": true
  }'
```

**错误响应：**

```json
{
  "error": {
    "message": "Only streaming is supported. Set 'stream' to true.",
    "type": "invalid_request_error",
    "code": "invalid_request"
  }
}
```

**高级参数配置：**

OpenAI 兼容端点支持通过消息内容指定额外的配置参数。这些参数可以在 `system` 消息或 `user` 消息中指定。

**支持的参数：**

| 参数                           | 格式示例                                   | 说明                                     |
| ------------------------------ | ------------------------------------------ | ---------------------------------------- |
| `workspace`                    | `workspace=my-workspace`                   | 指定工作区名称，默认为 "shared"          |
| `session-id`                   | `session-id=abc123-def456-...`             | 会话 ID（从之前的 assistant 响应中获取） |
| `dangerously-skip-permissions` | `dangerously-skip-permissions=true`        | 跳过权限检查（危险操作）                 |
| `allowed-tools`                | `allowed-tools=["read_file","write_file"]` | 允许使用的工具列表                       |
| `disallowed-tools`             | `disallowed-tools=["execute_command"]`     | 禁止使用的工具列表                       |
| `thinking`                     | `thinking=true`                            | 是否显示 thinking 过程                   |

**参数优先级：** 当前 user 消息 > 之前的 assistant 消息 > system 消息

**示例 1：在 system 消息中指定工作区和工具权限**

```python
from openai import OpenAI

client = OpenAI(
    api_key="your-api-key",
    base_url="http://localhost:3000/v1"
)

messages = [
    {
        "role": "system",
        "content": "你是一个专业的代码助手。workspace=my-project allowed-tools=[\"read_file\",\"write_file\"]"
    },
    {
        "role": "user",
        "content": "请读取 main.py 文件"
    }
]

stream = client.chat.completions.create(
    model="MiniMax-M2",
    messages=messages,
    stream=True
)
```

**示例 2：在 user 消息中指定配置**

```python
messages = [
    {
        "role": "user",
        "content": "workspace=test-project thinking=true 请帮我写一个 Python 函数"
    }
]
```

**示例 3：恢复会话（使用 session-id）**

```python
# 第一次请求
messages = [
    {"role": "user", "content": "你好"}
]

stream = client.chat.completions.create(
    model="MiniMax-M2",
    messages=messages,
    stream=True
)

session_id = None
for chunk in stream:
    content = chunk.choices[0].delta.content
    if content:
        print(content, end="", flush=True)
        # 从响应中提取 session-id（通常在 thinking 块中）
        if "session-id=" in content:
            import re
            match = re.search(r"session-id=([a-f0-9-]+)", content)
            if match:
                session_id = match.group(1)

# 第二次请求，恢复会话
if session_id:
    messages = [
        {"role": "assistant", "content": f"session-id={session_id}"},
        {"role": "user", "content": "继续之前的对话"}
    ]

    stream = client.chat.completions.create(
        model="MiniMax-M2",
        messages=messages,
        stream=True
    )
```

**示例 4：使用 cURL 指定参数**

```bash
curl -X POST http://localhost:3000/v1/chat/completions \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "MiniMax-M2",
    "messages": [
      {
        "role": "system",
        "content": "workspace=my-project allowed-tools=[\"read_file\"]"
      },
      {
        "role": "user",
        "content": "读取 config.json"
      }
    ],
    "stream": true
  }'
```

**注意事项：**

1. **session-id** 只能从之前的 assistant 响应中获取，不能手动指定
2. 参数格式必须严格按照示例格式，使用空格分隔
3. `allowed-tools` 和 `disallowed-tools` 使用 JSON 数组格式，工具名用双引号包裹
4. 布尔值参数使用 `true` 或 `false`（小写）
5. 参数会被自动从消息内容中移除，不会发送给 Claude

---

### 3. Claude API 端点

#### POST /api/claude

原生 Claude API 端点，提供更细粒度的控制选项。

**请求头：**

```
Authorization: Bearer <your-api-key>
Content-Type: application/json
```

**请求体：**

```json
{
  "prompt": "请帮我写一个 Python 函数来计算斐波那契数列",
  "session-id": "optional-session-id",
  "workspace": "my-workspace",
  "system-prompt": "你是一个专业的 Python 开发助手",
  "dangerously-skip-permissions": false,
  "allowed-tools": ["read_file", "write_file"],
  "disallowed-tools": ["execute_command"],
  "files": ["/path/to/file1.py", "/path/to/file2.py"]
}
```

**参数说明：**

| 参数                           | 类型          | 必填 | 说明                                         |
| ------------------------------ | ------------- | ---- | -------------------------------------------- |
| `prompt`                       | string        | 是   | 用户提示内容                                 |
| `session-id`                   | string        | 否   | 会话 ID，用于恢复之前的会话                  |
| `workspace`                    | string        | 否   | 工作区名称，默认为 "shared"                  |
| `system-prompt`                | string        | 否   | 系统提示，用于设置助手的行为                 |
| `dangerously-skip-permissions` | boolean       | 否   | 是否跳过权限检查（危险操作）                 |
| `allowed-tools`                | array[string] | 否   | 允许使用的工具列表                           |
| `disallowed-tools`             | array[string] | 否   | 禁止使用的工具列表                           |
| `files`                        | array[string] | 否   | 文件路径列表（绝对路径或相对于工作区的路径） |

**响应格式（Server-Sent Events）：**

````
data: {"type":"system","subtype":"init","cwd":"/path/to/workspace","session_id":"..."}

data: {"type":"assistant","message":{"id":"...","type":"message","role":"assistant","content":[{"type":"text","text":"以下是计算斐波那契数列的 Python 函数："}]}}

data: {"type":"assistant","message":{"id":"...","type":"message","role":"assistant","content":[{"type":"text","text":"\n\n```python\ndef fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)\n```"}]}}

data: {"type":"result","result":"..."}
````

**Python 示例：**

```python
import requests

url = "http://localhost:3000/api/claude"
headers = {
    "Authorization": "Bearer your-api-key",
    "Content-Type": "application/json"
}
data = {
    "prompt": "请帮我写一个 Python 函数来计算斐波那契数列",
    "system-prompt": "你是一个专业的 Python 开发助手",
    "workspace": "my-workspace"
}

response = requests.post(url, json=data, headers=headers, stream=True)

for line in response.iter_lines(decode_unicode=True):
    if line:
        print(line)
```

**cURL 示例：**

```bash
curl -X POST http://localhost:3000/api/claude \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "请帮我写一个 Python 函数来计算斐波那契数列",
    "system-prompt": "你是一个专业的 Python 开发助手",
    "workspace": "my-workspace"
  }'
```

---

### 4. 文件处理端点

#### PUT /process

外部文档加载器端点，用于 OpenWebUI 等集成。接收文件数据并保存到工作区，返回文件路径。

**请求头：**

```
Authorization: Bearer <your-api-key>
Content-Type: application/octet-stream
```

**请求体：**

文件的二进制数据（直接作为请求体发送）。

**响应格式：**

```json
{
  "page_content": "/path/to/workspace/files/uuid-xxxxx.pdf",
  "metadata": {
    "source": "document.pdf"
  }
}
```

**Python 示例：**

```python
import requests

url = "http://localhost:3000/process"
headers = {
    "Authorization": "Bearer your-api-key",
    "Content-Type": "application/octet-stream"
}

with open("document.pdf", "rb") as f:
    file_data = f.read()

response = requests.put(url, data=file_data, headers=headers)
result = response.json()

print(f"文件已保存到: {result['page_content']}")
print(f"显示名称: {result['metadata']['source']}")
```

**cURL 示例：**

```bash
curl -X PUT http://localhost:3000/process \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @document.pdf
```

**错误响应：**

```json
{
  "error": {
    "message": "No file data provided",
    "type": "invalid_request_error",
    "code": "invalid_request"
  }
}
```

---

## 认证

所有 API 端点（除了 `/health`）都支持 Bearer Token 认证：

```bash
Authorization: Bearer <your-api-key>
```

如果未设置 `API_KEY` 环境变量，认证将被禁用，所有请求都会被允许。

**设置 API Key：**

1. 在 `.env` 文件中设置：

   ```bash
   API_KEY=sk-your-api-key-here
   ```

2. 或在环境变量中设置：
   ```bash
   export API_KEY=sk-your-api-key-here
   ```

---

## 错误处理

所有错误响应都遵循统一的格式：

```json
{
  "error": {
    "message": "错误描述",
    "type": "error_type",
    "code": "error_code",
    "requestId": "optional-request-id",
    "timestamp": "2025-11-07T13:36:37.189063Z"
  }
}
```

**常见错误类型：**

- `invalid_request_error`: 请求参数错误（400）
- `authentication_error`: 认证失败（401）
- `permission_error`: 权限不足（403）
- `not_found_error`: 资源未找到（404）
- `system_error`: 系统内部错误（500）

**流式响应中的错误：**

流式响应中的错误会以 SSE 格式返回：

```
data: {"type":"error","error":{"message":"错误描述","type":"error_type","code":"error_code"}}
```

---

## 工作区管理

工作区用于隔离不同会话的文件和上下文。每个工作区都有独立的文件系统目录。

**默认工作区：** `shared`

**自定义工作区：** 在请求中指定 `workspace` 参数，工作区将自动创建。

**工作区路径：** `{WORKSPACE_BASE}/{workspace_name}/shared_workspace`

---

## 会话管理

通过 `session-id` 参数可以恢复之前的 Claude Code 会话，继续之前的对话上下文。

**使用会话：**

```json
{
  "prompt": "继续之前的对话",
  "session-id": "previous-session-id"
}
```

---

## 工具权限控制

通过 `allowed-tools` 和 `disallowed-tools` 参数可以精确控制 Claude 可以使用的工具。

**示例：**

```json
{
  "prompt": "读取文件",
  "allowed-tools": ["read_file"],
  "disallowed-tools": ["write_file", "execute_command"]
}
```

⚠️ **警告：** `dangerously-skip-permissions` 选项会跳过所有权限检查，仅在完全信任的环境中使用。

## 开发

### 代码格式化

```bash
black src/ tests/
ruff check --fix src/ tests/
```

### 类型检查

```bash
mypy src/
```

### 运行测试

```bash
pytest
pytest --cov=src --cov-report=html
```

### 功能对比验证

```bash
# 确保 TypeScript 版本在 3000 端口运行
# Python 版本在 3000 端口运行
pytest tests/test_functional_comparison.py -v
```

## 与 TypeScript 版本的对比

详细的功能对比验证方案请参考 [FUNCTIONAL_COMPARISON.md](./FUNCTIONAL_COMPARISON.md)。

## 项目结构

```
python/
├── src/
│   ├── main.py              # FastAPI 应用入口
│   ├── config.py            # 配置管理
│   ├── api/                 # API 路由和中间件
│   ├── core/                # 核心业务逻辑
│   ├── services/            # 服务层
│   ├── models/              # 数据模型
│   └── exceptions/          # 异常处理
└── tests/                   # 测试套件
```

## 许可证

与原项目相同。

## 贡献

欢迎提交 Issue 和 Pull Request！
