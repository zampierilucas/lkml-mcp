"""MCP server for LKML thread retrieval."""

import argparse
import os

from .tools import mcp

DEFAULT_TRANSPORT = "stdio"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8772
VALID_TRANSPORTS = ("stdio", "sse", "streamable-http")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="lkml-mcp", description="MCP server for LKML thread retrieval")
    parser.add_argument(
        "--transport",
        choices=VALID_TRANSPORTS,
        default=os.environ.get("LKML_MCP_TRANSPORT", DEFAULT_TRANSPORT),
        help="Transport to use (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("LKML_MCP_HOST", DEFAULT_HOST),
        help="Bind host for sse/streamable-http (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("LKML_MCP_PORT", DEFAULT_PORT)),
        help="Bind port for sse/streamable-http (default: 8772)",
    )
    return parser.parse_args(argv)


def asyncio_main() -> None:
    """Entry point for console scripts."""
    args = _parse_args()
    kwargs = {} if args.transport == "stdio" else {"host": args.host, "port": args.port}
    mcp.run(args.transport, **kwargs)


if __name__ == "__main__":
    asyncio_main()
