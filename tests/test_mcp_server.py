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
