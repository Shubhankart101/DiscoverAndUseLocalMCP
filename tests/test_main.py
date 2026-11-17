from __future__ import annotations

import asyncio
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from main import (
    build_server_params,
    discover_capabilities,
    execute_request,
)
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


# ==============================================================================
# TODO 1 Tests: build_server_params
# ==============================================================================


def test_build_server_params_returns_stdio_transport():
    transport = build_server_params("server.py")
    assert isinstance(transport, StdioTransport)
    assert transport.command == sys.executable
    assert transport.args == ["server.py"]


def test_build_server_params_custom_path():
    custom_path = "path/to/custom_server.py"
    transport = build_server_params(custom_path)
    assert isinstance(transport, StdioTransport)
    assert transport.command == sys.executable
    assert transport.args == [custom_path]


# ==============================================================================
# TODO 2 Tests: discover_capabilities
# ==============================================================================


def test_discover_capabilities_success_with_mock():
    session = AsyncMock()
    session.list_resources.return_value = [
        SimpleNamespace(uri="custom://alpha"),
        SimpleNamespace(uri=REQUIRED_RESOURCE),
    ]
    session.list_tools.return_value = [
        SimpleNamespace(name=REQUIRED_TOOL),
        SimpleNamespace(name="extra_tool"),
    ]
    session.list_prompts.return_value = [
        SimpleNamespace(name="extra_prompt"),
        SimpleNamespace(name=REQUIRED_PROMPT),
    ]

    caps = asyncio.run(discover_capabilities(session))

    assert isinstance(caps, CapabilitySet)
    # Order preservation
    assert caps.resources == ("custom://alpha", REQUIRED_RESOURCE)
    assert caps.tools == (REQUIRED_TOOL, "extra_tool")
    assert caps.prompts == ("extra_prompt", REQUIRED_PROMPT)


def test_discover_capabilities_missing_resource():
    session = AsyncMock()
    session.list_resources.return_value = [SimpleNamespace(uri="other://catalog")]
    session.list_tools.return_value = [SimpleNamespace(name=REQUIRED_TOOL)]
    session.list_prompts.return_value = [SimpleNamespace(name=REQUIRED_PROMPT)]

    with pytest.raises(MissingCapabilityError, match=REQUIRED_RESOURCE):
        asyncio.run(discover_capabilities(session))


def test_discover_capabilities_missing_tool():
    session = AsyncMock()
    session.list_resources.return_value = [SimpleNamespace(uri=REQUIRED_RESOURCE)]
    session.list_tools.return_value = [SimpleNamespace(name="other_tool")]
    session.list_prompts.return_value = [SimpleNamespace(name=REQUIRED_PROMPT)]

    with pytest.raises(MissingCapabilityError, match=REQUIRED_TOOL):
        asyncio.run(discover_capabilities(session))


def test_discover_capabilities_missing_prompt():
    session = AsyncMock()
    session.list_resources.return_value = [SimpleNamespace(uri=REQUIRED_RESOURCE)]
    session.list_tools.return_value = [SimpleNamespace(name=REQUIRED_TOOL)]
    session.list_prompts.return_value = [SimpleNamespace(name="other_prompt")]

    with pytest.raises(MissingCapabilityError, match=REQUIRED_PROMPT):
        asyncio.run(discover_capabilities(session))


def test_discover_capabilities_with_wrapper_objects():
    session = AsyncMock()
    session.list_resources.return_value = SimpleNamespace(
        resources=[SimpleNamespace(uri=REQUIRED_RESOURCE)]
    )
    session.list_tools.return_value = SimpleNamespace(
        tools=[SimpleNamespace(name=REQUIRED_TOOL)]
    )
    session.list_prompts.return_value = SimpleNamespace(
        prompts=[SimpleNamespace(name=REQUIRED_PROMPT)]
    )

    caps = asyncio.run(discover_capabilities(session))
    assert caps.resources == (REQUIRED_RESOURCE,)
    assert caps.tools == (REQUIRED_TOOL,)
    assert caps.prompts == (REQUIRED_PROMPT,)


def test_execute_request_invalid_type_primitive_no_session_call():
    session = AsyncMock()
    req = MCPRequest(
        primitive=123,  # type: ignore[arg-type]
        identifier=REQUIRED_RESOURCE,
        arguments={},
    )

    result = asyncio.run(execute_request(session, req))
    assert result.ok is False
    assert result.error == "unknown_capability"
    assert result.content == ()
    assert result.primitive == 123
    session.read_resource.assert_not_called()


def test_integration_with_open_local_session():
    from utils.client import open_local_session

    async def run_session_test():
        params = build_server_params("server.py")
        async with open_local_session(params) as session:
            caps = await discover_capabilities(session)
            assert REQUIRED_RESOURCE in caps.resources

            # Tool call on non-existent item
            req = MCPRequest("tool", REQUIRED_TOOL, {"equipment_id": "non-existent"})
            res = await execute_request(session, req)
            assert res.ok is True
            assert res.primitive == PrimitiveType.TOOL
            data = json.loads(res.content[0])
            assert data["found"] is False

    asyncio.run(run_session_test())



# ==============================================================================
# TODO 3 Tests: execute_request
# ==============================================================================


def test_execute_request_unknown_primitive_no_session_call():
    session = AsyncMock()
    req = MCPRequest(
        primitive="invalid_primitive",
        identifier=REQUIRED_RESOURCE,
        arguments={},
    )

    result = asyncio.run(execute_request(session, req))

    assert isinstance(result, MCPResult)
    assert result.ok is False
    assert result.error == "unknown_capability"
    assert result.content == ()
    assert result.identifier == REQUIRED_RESOURCE
    assert result.primitive == "invalid_primitive"

    session.read_resource.assert_not_called()
    session.call_tool.assert_not_called()
    session.get_prompt.assert_not_called()


def test_execute_request_mismatched_resource_identifier_no_session_call():
    session = AsyncMock()
    req = MCPRequest(
        primitive="resource",
        identifier="equipment://unauthorized",
        arguments={},
    )

    result = asyncio.run(execute_request(session, req))

    assert result.ok is False
    assert result.error == "unknown_capability"
    assert result.content == ()
    assert result.identifier == "equipment://unauthorized"

    session.read_resource.assert_not_called()
    session.call_tool.assert_not_called()
    session.get_prompt.assert_not_called()


def test_execute_request_mismatched_tool_identifier_no_session_call():
    session = AsyncMock()
    req = MCPRequest(
        primitive=PrimitiveType.TOOL,
        identifier="dangerous_tool",
        arguments={"key": "val"},
    )

    result = asyncio.run(execute_request(session, req))

    assert result.ok is False
    assert result.error == "unknown_capability"
    assert result.content == ()

    session.read_resource.assert_not_called()
    session.call_tool.assert_not_called()
    session.get_prompt.assert_not_called()


def test_execute_request_mismatched_prompt_identifier_no_session_call():
    session = AsyncMock()
    req = MCPRequest(
        primitive="prompt",
        identifier="arbitrary_prompt",
        arguments={},
    )

    result = asyncio.run(execute_request(session, req))

    assert result.ok is False
    assert result.error == "unknown_capability"
    assert result.content == ()

    session.read_resource.assert_not_called()
    session.call_tool.assert_not_called()
    session.get_prompt.assert_not_called()


def test_execute_request_cross_primitive_identifier_no_session_call():
    session = AsyncMock()
    # Resource primitive with tool identifier
    req = MCPRequest(
        primitive="resource",
        identifier=REQUIRED_TOOL,
        arguments={},
    )

    result = asyncio.run(execute_request(session, req))

    assert result.ok is False
    assert result.error == "unknown_capability"
    assert result.content == ()

    session.read_resource.assert_not_called()
    session.call_tool.assert_not_called()
    session.get_prompt.assert_not_called()


def test_execute_request_valid_resource_success():
    session = AsyncMock()
    session.read_resource.return_value = [
        SimpleNamespace(text='{"drill-01": {"name": "Cordless Drill"}}')
    ]

    req = MCPRequest(
        primitive="resource",
        identifier=REQUIRED_RESOURCE,
        arguments={},
    )

    result = asyncio.run(execute_request(session, req))

    assert result.ok is True
    assert result.error is None
    assert result.primitive == PrimitiveType.RESOURCE
    assert result.identifier == REQUIRED_RESOURCE
    assert result.content == ('{"drill-01": {"name": "Cordless Drill"}}',)
    session.read_resource.assert_awaited_once_with(REQUIRED_RESOURCE)


def test_execute_request_valid_tool_success():
    session = AsyncMock()
    session.call_tool.return_value = SimpleNamespace(
        content=[SimpleNamespace(text='{"found": true}')]
    )

    args = {"equipment_id": "drill-01"}
    req = MCPRequest(
        primitive=PrimitiveType.TOOL,
        identifier=REQUIRED_TOOL,
        arguments=args,
    )

    result = asyncio.run(execute_request(session, req))

    assert result.ok is True
    assert result.error is None
    assert result.primitive == PrimitiveType.TOOL
    assert result.identifier == REQUIRED_TOOL
    assert result.content == ('{"found": true}',)
    session.call_tool.assert_awaited_once_with(REQUIRED_TOOL, args)


def test_execute_request_valid_prompt_success():
    session = AsyncMock()
    session.get_prompt.return_value = SimpleNamespace(
        messages=[
            SimpleNamespace(
                role="user",
                content=SimpleNamespace(text="Prepare a maintenance request for drill-01."),
            )
        ]
    )

    args = {"equipment_id": "drill-01"}
    req = MCPRequest(
        primitive="PROMPT",
        identifier=REQUIRED_PROMPT,
        arguments=args,
    )

    result = asyncio.run(execute_request(session, req))

    assert result.ok is True
    assert result.error is None
    assert result.primitive == PrimitiveType.PROMPT
    assert result.identifier == REQUIRED_PROMPT
    assert result.content == ("Prepare a maintenance request for drill-01.",)
    session.get_prompt.assert_awaited_once_with(REQUIRED_PROMPT, args)


# ==============================================================================
# End-to-End Integration Tests with Local server.py
# ==============================================================================


def test_integration_with_local_server():
    async def run_integration():
        transport = build_server_params("server.py")
        async with Client(transport) as session:
            # 1. Discover capabilities
            caps = await discover_capabilities(session)
            assert REQUIRED_RESOURCE in caps.resources
            assert REQUIRED_TOOL in caps.tools
            assert REQUIRED_PROMPT in caps.prompts

            # 2. Execute Resource request
            r_req = MCPRequest(
                primitive=PrimitiveType.RESOURCE,
                identifier=REQUIRED_RESOURCE,
                arguments={},
            )
            r_res = await execute_request(session, r_req)
            assert r_res.ok is True
            assert r_res.primitive == PrimitiveType.RESOURCE
            assert r_res.identifier == REQUIRED_RESOURCE
            assert len(r_res.content) == 1
            catalog_data = json.loads(r_res.content[0])
            assert "drill-01" in catalog_data

            # 3. Execute Tool request
            t_req = MCPRequest(
                primitive="tool",
                identifier=REQUIRED_TOOL,
                arguments={"equipment_id": "drill-01"},
            )
            t_res = await execute_request(session, t_req)
            assert t_res.ok is True
            assert t_res.primitive == PrimitiveType.TOOL
            assert t_res.identifier == REQUIRED_TOOL
            assert len(t_res.content) == 1
            tool_data = json.loads(t_res.content[0])
            assert tool_data["found"] is True
            assert tool_data["available"] is True

            # 4. Execute Prompt request
            p_req = MCPRequest(
                primitive="prompt",
                identifier=REQUIRED_PROMPT,
                arguments={"equipment_id": "meter-02"},
            )
            p_res = await execute_request(session, p_req)
            assert p_res.ok is True
            assert p_res.primitive == PrimitiveType.PROMPT
            assert p_res.identifier == REQUIRED_PROMPT
            assert len(p_res.content) == 1
            assert "meter-02" in p_res.content[0]

            # 5. Execute safe rejection of unknown capability
            bad_req = MCPRequest(
                primitive="tool",
                identifier="system_reboot",
                arguments={},
            )
            bad_res = await execute_request(session, bad_req)
            assert bad_res.ok is False
            assert bad_res.error == "unknown_capability"
            assert bad_res.content == ()

    asyncio.run(run_integration())
