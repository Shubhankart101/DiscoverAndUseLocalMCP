"""Discover and Use Local MCP Capabilities.

A maintenance host connects to a supplied local MCP server over stdio. Complete
only build_server_params, discover_capabilities, and execute_request.

The server script, session context manager, request/result types, identifiers,
content helper, Groq-compatible host, and cleanup harness are supplied. Pytest
uses a local subprocess or fake session and makes no external network call.

Required behavior:
- build_server_params returns a FastMCP StdioTransport with command=sys.executable
  and args containing only the supplied server_path.
- discover_capabilities calls all three list methods, records resource URIs,
  tool names, and prompt names in returned order, and raises
  MissingCapabilityError if any required identifier is absent.
- execute_request supports only the declared Resource, Tool, and Prompt.
- Resource reads pass the declared URI. Tool calls pass the request arguments.
  Prompt retrieval passes the request arguments.
- Normalize returned text blocks into MCPResult.content without losing the
  requested primitive type or identifier.
- Unknown primitive values or identifiers return MCPResult with ok=False and
  error="unknown_capability" without calling the session.

Not required: writing a server, transport internals, process cleanup code,
OAuth, external apps, real model calls during evaluation, or deployment.
"""

from __future__ import annotations

import sys

from fastmcp.client.transports import StdioTransport

from utils.content import collect_text
from utils.models import (
    REQUIRED_PROMPT,
    REQUIRED_RESOURCE,
    REQUIRED_TOOL,
    CapabilitySet,
    MCPRequest,
    MCPResult,
    MissingCapabilityError,
    PrimitiveType,
)


def build_server_params(server_path: str) -> StdioTransport:
    return StdioTransport(command=sys.executable, args=[server_path])


async def discover_capabilities(session) -> CapabilitySet:
    raw_resources = await session.list_resources()
    raw_tools = await session.list_tools()
    raw_prompts = await session.list_prompts()

    res_items = getattr(raw_resources, "resources", raw_resources)
    tool_items = getattr(raw_tools, "tools", raw_tools)
    prompt_items = getattr(raw_prompts, "prompts", raw_prompts)

    def _get_uri(item: object) -> str:
        if hasattr(item, "uri"):
            return str(item.uri)
        if isinstance(item, dict) and "uri" in item:
            return str(item["uri"])
        return str(item)

    def _get_name(item: object) -> str:
        if hasattr(item, "name"):
            return str(item.name)
        if isinstance(item, dict) and "name" in item:
            return str(item["name"])
        return str(item)

    resources = tuple(_get_uri(item) for item in res_items)
    tools = tuple(_get_name(item) for item in tool_items)
    prompts = tuple(_get_name(item) for item in prompt_items)

    if REQUIRED_RESOURCE not in resources:
        raise MissingCapabilityError(f"Missing required resource: {REQUIRED_RESOURCE}")
    if REQUIRED_TOOL not in tools:
        raise MissingCapabilityError(f"Missing required tool: {REQUIRED_TOOL}")
    if REQUIRED_PROMPT not in prompts:
        raise MissingCapabilityError(f"Missing required prompt: {REQUIRED_PROMPT}")

    return CapabilitySet(resources=resources, tools=tools, prompts=prompts)


async def execute_request(session, request: MCPRequest) -> MCPResult:
    primitive: PrimitiveType | None = None
    if isinstance(request.primitive, PrimitiveType):
        primitive = request.primitive
    elif isinstance(request.primitive, str):
        try:
            primitive = PrimitiveType(request.primitive.lower())
        except (ValueError, KeyError):
            primitive = None

    if primitive is None or (
        (primitive == PrimitiveType.RESOURCE and request.identifier != REQUIRED_RESOURCE)
        or (primitive == PrimitiveType.TOOL and request.identifier != REQUIRED_TOOL)
        or (primitive == PrimitiveType.PROMPT and request.identifier != REQUIRED_PROMPT)
    ):
        return MCPResult(
            ok=False,
            primitive=primitive if primitive is not None else request.primitive,
            identifier=request.identifier,
            content=(),
            error="unknown_capability",
        )

    if primitive == PrimitiveType.RESOURCE:
        raw = await session.read_resource(request.identifier)
        contents = getattr(raw, "contents", raw)
        blocks = contents if isinstance(contents, (list, tuple)) else [contents]
        content = collect_text(blocks)
    elif primitive == PrimitiveType.TOOL:
        raw = await session.call_tool(request.identifier, request.arguments)
        tool_content = getattr(raw, "content", raw)
        blocks = tool_content if isinstance(tool_content, (list, tuple)) else [tool_content]
        content = collect_text(blocks)
    elif primitive == PrimitiveType.PROMPT:
        raw = await session.get_prompt(request.identifier, request.arguments)
        messages = getattr(raw, "messages", raw)
        if not isinstance(messages, (list, tuple)):
            messages = [messages]
        blocks = []
        for m in messages:
            c = getattr(m, "content", None)
            if isinstance(c, str):
                blocks.append(m)
            elif isinstance(c, (list, tuple)):
                blocks.extend(c)
            elif c is not None:
                blocks.append(c)
            else:
                blocks.append(m)
        content = collect_text(blocks)

    return MCPResult(
        ok=True,
        primitive=primitive,
        identifier=request.identifier,
        content=content,
        error=None,
    )
