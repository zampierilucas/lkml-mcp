#!/usr/bin/env python3
"""Test LKML MCP server tool registration and dispatch."""

import sys
from pathlib import Path

import pytest

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mcp.server.mcpserver.exceptions import ToolError

from lkml_mcp.client import LKMLAPIError
from lkml_mcp.tools import mcp

EXPECTED_TOOLS = {
    "lkml_get_thread",
    "lkml_get_raw",
    "lkml_get_user_series",
    "lkml_search_patches",
    "lkml_get_patch",
    "lkml_get_thread_summary",
    "lkml_compare_patch_versions",
}


@pytest.mark.asyncio
async def test_tools_registered():
    tools = {t.name: t for t in await mcp.list_tools()}
    assert set(tools) == EXPECTED_TOOLS

    schema = tools["lkml_get_thread"].input_schema
    assert schema["required"] == ["message_id"]
    assert set(schema["properties"]) == {"message_id", "inbox", "include_bots"}
    assert tools["lkml_get_thread"].output_schema is None


@pytest.mark.asyncio
async def test_call_tool(monkeypatch):
    monkeypatch.setattr(
        "lkml_mcp.tools.client.get_raw",
        lambda message_id, inbox=None: {"message_id": message_id, "raw": "From: someone"},
    )
    result = await mcp.call_tool("lkml_get_raw", {"message_id": "test@example.com"})

    assert not result.is_error
    assert "From: someone" in result.content[0].text


EMPTY_RESULTS = {
    "get_thread": {"message_id": "m", "messages": []},
    "get_raw": {"message_id": "m", "raw": ""},
    "get_user_series": {"email": "e", "series": []},
    "get_patch": {"message_id": "m", "series": False, "patches": []},
    "get_thread_summary": {
        "subject": "s", "author": "a", "date": "d", "total_messages": 0,
        "participants": [], "tags": [], "messages": [],
    },
    "compare_patch_versions": {
        "old_version": {"version": "v1", "patch_count": 0, "message_id": "old"},
        "new_version": {"version": "v2", "patch_count": 0, "message_id": "new"},
        "changes": [], "patches_added": [], "patches_removed": [],
    },
    "search_patches": {"query": "q", "filters": {}, "total_results": 0, "results": []},
}

TOOL_ARGS = {
    "lkml_get_thread": {"message_id": "m@example.com", "inbox": "lkml", "include_bots": True},
    "lkml_get_raw": {"message_id": "m@example.com", "inbox": "lkml"},
    "lkml_get_user_series": {"email": "e@example.com", "inbox": "lkml", "max_results": 5},
    "lkml_get_patch": {"message_id": "m@example.com", "inbox": "lkml", "series": True},
    "lkml_get_thread_summary": {"message_id": "m@example.com", "include_bots": True},
    "lkml_compare_patch_versions": {"old_message_id": "a@example.com", "new_message_id": "b@example.com"},
    "lkml_search_patches": {"query": "riscv", "subsystem": "net", "author": "x", "since_date": "20250101"},
}


@pytest.mark.parametrize("tool_name", sorted(EXPECTED_TOOLS))
@pytest.mark.asyncio
async def test_every_tool_dispatches(tool_name, monkeypatch):
    """Each tool reaches its client method and forwards the arguments it was given."""
    client_method = tool_name.removeprefix("lkml_")
    forwarded = []

    def record(*args, **kwargs):
        forwarded.extend(args)
        forwarded.extend(kwargs.values())
        return EMPTY_RESULTS[client_method]

    monkeypatch.setattr(f"lkml_mcp.tools.client.{client_method}", record)
    result = await mcp.call_tool(tool_name, TOOL_ARGS[tool_name])

    assert not result.is_error
    assert result.content[0].text
    # every argument must reach the client, positionally or by keyword
    for key, value in TOOL_ARGS[tool_name].items():
        assert value in forwarded, f"{tool_name} dropped {key}"


@pytest.mark.asyncio
async def test_missing_required_argument():
    with pytest.raises(ToolError, match="message_id"):
        await mcp.call_tool("lkml_get_thread", {})


@pytest.mark.asyncio
async def test_client_error_surfaces(monkeypatch):
    def boom(*args, **kwargs):
        raise LKMLAPIError("no such message")

    monkeypatch.setattr("lkml_mcp.tools.client.get_raw", boom)

    with pytest.raises(ToolError, match="no such message"):
        await mcp.call_tool("lkml_get_raw", {"message_id": "missing@example.com"})


@pytest.mark.asyncio
async def test_unknown_tool():
    with pytest.raises(ToolError, match="Unknown tool"):
        await mcp.call_tool("nonexistent_tool", {})
