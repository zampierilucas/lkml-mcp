"""MCP server for LKML thread retrieval."""

import asyncio
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .client import LKMLAPIError, LKMLClient
from .handlers import (
    handle_lkml_get_raw,
    handle_lkml_get_thread,
    handle_lkml_get_user_series,
    handle_lkml_search_patches,
)

server = Server("lkml-mcp")
client = LKMLClient()


@server.list_tools()
async def list_tools() -> List[Tool]:
    """List available tools."""
    return [
        Tool(
            name="lkml_get_thread",
            description=(
                "Fetch a full LKML thread by message ID from lore.kernel.org. "
                "Returns all messages in the thread with subject, from, date, "
                "message-id, in-reply-to, and body content. By default, "
                "filters out automated bot messages (kernel test robot, "
                "CI bots, etc.)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": (
                            "The message ID to fetch (e.g., '20251111105634.1684751-1-lzampier@redhat.com'). "
                            "Can be provided with or without angle brackets."
                        ),
                    },
                    "include_bots": {
                        "type": "boolean",
                        "description": (
                            "If true, include automated bot messages (kernel test robot, CI notifications, etc.). "
                            "If false or omitted (default), filter them out."
                        ),
                        "default": False,
                    },
                },
                "required": ["message_id"],
            },
        ),
        Tool(
            name="lkml_get_raw",
            description=(
                "Fetch a single LKML message in raw RFC822 format from lore.kernel.org. "
                "Useful for getting raw MIME bodies, headers, or inline diffs."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": (
                            "The message ID to fetch (e.g., '20251111105634.1684751-1-lzampier@redhat.com'). "
                            "Can be provided with or without angle brackets."
                        ),
                    }
                },
                "required": ["message_id"],
            },
        ),
        Tool(
            name="lkml_get_user_series",
            description=(
                "Find recent patch series and messages by user email address. "
                "Returns a list of patch series (with cover letters and "
                "patches grouped together) and standalone messages. Useful "
                "for discovering what patches a user has recently proposed "
                "or been involved in."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "User email address (e.g., 'lzampier@redhat.com')",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of messages to retrieve (default: 50)",
                        "default": 50,
                        "minimum": 1,
                        "maximum": 200,
                    },
                },
                "required": ["email"],
            },
        ),
        Tool(
            name="lkml_search_patches",
            description=(
                "Search for patches by keywords, subsystem, author, or other criteria. "
                "Returns matching patch series and individual patches from lore.kernel.org."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query string (e.g., 'kvm', 'memory leak', 'driver bug fix')",
                    },
                    "subsystem": {
                        "type": "string",
                        "description": "Filter by subsystem (e.g., 'net', 'kvm', 'riscv', 'mm'). Optional.",
                    },
                    "author": {
                        "type": "string",
                        "description": "Filter by author email or name. Optional.",
                    },
                    "since_date": {
                        "type": "string",
                        "description": (
                            "Only return patches since this date (YYYYMMDD format, e.g., '20250101'). Optional."
                        ),
                        "pattern": "^\\d{8}$",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 20)",
                        "default": 20,
                        "minimum": 1,
                        "maximum": 100,
                    },
                },
                "required": ["query"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Optional[Dict[str, Any]]):
    """Handle tool calls."""
    arguments = arguments or {}

    try:
        if name == "lkml_get_thread":
            return await handle_lkml_get_thread(client, arguments)
        elif name == "lkml_get_raw":
            return await handle_lkml_get_raw(client, arguments)
        elif name == "lkml_get_user_series":
            return await handle_lkml_get_user_series(client, arguments)
        elif name == "lkml_search_patches":
            return await handle_lkml_search_patches(client, arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except LKMLAPIError as e:
        return [TextContent(type="text", text=f"LKML API Error: {e}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="lkml-mcp",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def asyncio_main() -> None:
    """Entry point for console scripts."""
    asyncio.run(main())


if __name__ == "__main__":
    asyncio_main()
