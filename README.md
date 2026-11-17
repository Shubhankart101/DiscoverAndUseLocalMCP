# Discover and Use Local MCP Capabilities

[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg)](https://www.python.org/)
[![FastMCP](https://img.shields.io/badge/FastMCP-4.0.4-orange.svg)](https://gofastmcp.com)
[![Pytest](https://img.shields.io/badge/pytest-8.4.1-green.svg)](https://docs.pytest.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A robust, asynchronous maintenance host that interfaces with a local Model Context Protocol (MCP) server over standard input and output (`stdio`). The host configures the server subprocess, discovers and validates declared MCP primitives (Resources, Tools, and Prompts), and dispatches typed requests safely with strict capability verification.

---

## Agent Flow & Architecture

```
+---------------------------------------------------------------------------------------+
|                                      Agent Loop                                       |
|                                                                                       |
|   1. Discover MCP Capabilities                                                        |
|      (resources, tools, prompts)                                                      |
|                 │                                                                     |
|                 ▼                                                                     |
|   2. Model selects one MCP request                                                    |
|                 │                                                                     |
|                 ▼                                                                     |
|   3. Safe Execution Dispatcher (execute_request)                                      |
|      ├── Unknown primitive / mismatched identifier? ──> Return ok=False (No session)  |
|      └── Supported primitive & matching identifier:                                   |
|            • Resource ("equipment://catalog")    ──> session.read_resource(...)       |
|            • Tool     ("check_availability")     ──> session.call_tool(...)           |
|            • Prompt   ("maintenance_prompt")     ──> session.get_prompt(...)          |
|                 │                                                                     |
|                 ▼                                                                     |
|   4. Normalize Text Blocks into MCPResult.content via collect_text                    |
|                 │                                                                     |
|                 ▼                                                                     |
|   5. Return MCPResult to Host Model -> Final Model Answer                             |
+---------------------------------------------------------------------------------------+
```

### Communication Topology

```
+───────────────────────────+                     +───────────────────────────+
|      Maintenance Host     |   Standard Input    |     Local MCP Server      |
|  (DiscoverAndUseLocalMCP) | ──────────────────> |        (server.py)        |
|                           |   Standard Output   |                           |
|   • FastMCP Client        | <────────────────── |   • FastMCP Stdio Server  |
|   • Capability Discovery  |                     |   • Equipment Catalog     |
|   • Safe Typed Dispatcher |                     |   • Availability Checker  |
+───────────────────────────+                     +───────────────────────────+
```

---

## Required Capabilities

| Primitive | Declared Identifier | Description | Input / Arguments |
|:---|:---|:---|:---|
| **Resource** | `equipment://catalog` | Equipment inventory catalog in JSON format | *None* |
| **Tool** | `check_availability` | Checks equipment availability by ID | `{"equipment_id": str}` |
| **Prompt** | `maintenance_prompt` | Prepares maintenance request template | `{"equipment_id": str}` |

---

## Core Components

### 1. `build_server_params(server_path: str) -> StdioTransport`
Configures process parameters for launching the local MCP server over standard input/output.
- Uses `sys.executable` to ensure execution within the active Python environment.
- Passes `args=[server_path]`, strictly containing only the supplied path without arbitrary shell flags or hard-coded Python binaries.

### 2. `discover_capabilities(session) -> CapabilitySet`
Discovers and verifies available capabilities exposed by the server.
- Queries `session.list_resources()`, `session.list_tools()`, and `session.list_prompts()`.
- Unpacks resource URIs, tool names, and prompt names as strings while preserving the exact order returned by the server.
- Validates presence of all three required identifiers (`equipment://catalog`, `check_availability`, `maintenance_prompt`).
- Raises `MissingCapabilityError` immediately if any required capability is missing.

### 3. `execute_request(session, request: MCPRequest) -> MCPResult`
Safely dispatches a typed MCP request to the underlying server session.
- Normalizes primitive representations (`PrimitiveType` members and case-insensitive strings like `"resource"`, `"tool"`, `"prompt"`).
- **Safety Gate**: Verifies that the primitive and identifier match one of the three required capabilities. For unknown primitives or mismatched identifiers:
  - Returns `MCPResult(ok=False, primitive=..., identifier=..., content=(), error="unknown_capability")`.
  - **Does not invoke any session execution method**, shielding the server from unauthorized or malformed requests.
- Invokes the appropriate session API:
  - Resource: `await session.read_resource(request.identifier)`
  - Tool: `await session.call_tool(request.identifier, request.arguments)`
  - Prompt: `await session.get_prompt(request.identifier, request.arguments)`
- Normalizes returned text blocks into a uniform tuple of strings (`MCPResult.content`) using `collect_text()`.
- Preserves the identifier and normalized `PrimitiveType` in the result.

---

## Data Models

```python
class PrimitiveType(str, Enum):
    RESOURCE = "resource"
    TOOL = "tool"
    PROMPT = "prompt"

@dataclass(frozen=True)
class CapabilitySet:
    resources: tuple[str, ...]
    tools: tuple[str, ...]
    prompts: tuple[str, ...]

@dataclass(frozen=True)
class MCPRequest:
    primitive: PrimitiveType | str
    identifier: str
    arguments: dict[str, Any]

@dataclass(frozen=True)
class MCPResult:
    ok: bool
    primitive: PrimitiveType | str
    identifier: str
    content: tuple[str, ...]
    error: str | None
```

---

## Installation & Setup

### Prerequisites
- Python 3.10+
- `pip`

```powershell
# Clone or navigate to the repository
cd DiscoverAndUseLocalMCP

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

---

## Quickstart & Usage

```python
import asyncio
from fastmcp import Client
from main import build_server_params, discover_capabilities, execute_request
from utils.models import MCPRequest, PrimitiveType

async def main():
    # 1. Build stdio transport parameters
    params = build_server_params("server.py")

    # 2. Open session to local server
    async with Client(params) as session:
        # 3. Discover and validate capabilities
        caps = await discover_capabilities(session)
        print("Resources:", caps.resources)
        print("Tools:", caps.tools)
        print("Prompts:", caps.prompts)

        # 4. Execute Resource request
        res_req = MCPRequest(
            primitive="resource",
            identifier="equipment://catalog",
            arguments={},
        )
        res_result = await execute_request(session, res_req)
        print("Catalog JSON:", res_result.content[0])

        # 5. Execute Tool request
        tool_req = MCPRequest(
            primitive=PrimitiveType.TOOL,
            identifier="check_availability",
            arguments={"equipment_id": "drill-01"},
        )
        tool_result = await execute_request(session, tool_req)
        print("Tool Output:", tool_result.content[0])

        # 6. Safe handling of unknown requests (no session call executed)
        unknown_req = MCPRequest(
            primitive="tool",
            identifier="reboot_system",
            arguments={},
        )
        safe_result = await execute_request(session, unknown_req)
        print("Safe rejection:", safe_result.ok, safe_result.error)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Testing

The test suite covers:
- Transport creation with exact Python executable and argument list.
- Discovery and order preservation across resources, tools, and prompts.
- Proper raising of `MissingCapabilityError` when any capability is absent.
- Full compatibility with wrapper models, dictionaries, and raw string items.
- Dispatch of Resource, Tool, and Prompt requests with correct session methods and arguments.
- Text block extraction and normalization via `collect_text()`.
- Safe rejection path: unknown primitives, mismatched identifiers, and cross-primitive calls return `ok=False` and `error="unknown_capability"` without calling session methods.
- End-to-end integration tests spawning the actual `server.py` subprocess over stdio.

Run the test suite:

```powershell
pytest -v
```

---

## Repository Structure

```
DiscoverAndUseLocalMCP/
├── main.py              # Implementation of build_server_params, discover_capabilities, execute_request
├── server.py            # Local FastMCP equipment server running over stdio
├── requirements.txt     # Python dependencies (fastmcp, pytest, groq)
├── pytest.ini           # Pytest configuration
├── LICENSE              # MIT License
├── README.md            # Detailed documentation
├── utils/
│   ├── client.py        # Client async context manager
│   ├── content.py       # collect_text normalizer helper
│   ├── host_agent.py    # Groq-compatible host runner
│   └── models.py        # CapabilitySet, MCPRequest, MCPResult, PrimitiveType
└── tests/
    └── test_main.py     # Unit and integration test suite (18 tests)
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
