# LKML MCP Server

A Model Context Protocol (MCP) server for accessing Linux Kernel Mailing List threads via lore.kernel.org. This server provides tools to fetch complete email threads and raw message content from any kernel mailing list archive (lkml, linux-riscv, netdev, etc.).

## Features

- **lkml_get_thread**: Fetch a full thread by message ID, returning all messages in the thread with structured metadata (subject, from, date, message-id, in-reply-to, body content)
- **lkml_get_raw**: Fetch a single message in raw RFC822 format, useful for getting raw MIME bodies, headers, or inline diffs
- **Cross-mailing-list support**: Works with any mailing list on lore.kernel.org without hardcoding list names (lkml, linux-riscv, netdev, devicetree, etc.)

## Prerequisites

- Python 3.8+
- **uvx** - Package runner for Python (install with `pip install uv`)
- Internet access to `https://lore.kernel.org`

## Installation by Platform

### Claude Desktop

Install as a Desktop Extension:

1. Download `lkml.mcpb` from this repository or build it: `mcpb pack . lkml.mcpb`
2. Open Claude Desktop → Settings → Extensions
3. Drag and drop `lkml.mcpb` into the Extensions window
4. Click "Enable" to activate the extension

### Claude Code (CLI)

Add to Claude Code MCP configuration:

```bash
claude mcp add -s user lkml uvx -- --from "git+https://github.com/zampierilucas/lkml-mcp" lkml-mcp
```

Or manually edit `~/.claude.json`:
```json
{
  "mcpServers": {
    "lkml": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/zampierilucas/lkml-mcp",
        "lkml-mcp"
      ]
    }
  }
}
```

### Cursor IDE

1. Open Cursor Settings (⌘+, on Mac, Ctrl+, on Windows/Linux)
2. Navigate to **Tools & MCP** → **Add Custom MCP**
3. Add the server configuration:

```json
{
  "lkml": {
    "command": "uvx",
    "args": [
      "--from",
      "git+https://github.com/zampierilucas/lkml-mcp",
      "lkml-mcp"
    ]
  }
}
```

### Local Installation (All Platforms)

Clone and install locally:
```bash
git clone https://github.com/zampierilucas/lkml-mcp.git
cd lkml-mcp
pip install -e .
```

Then configure in your MCP client:
```json
{
  "mcpServers": {
    "lkml": {
      "command": "python",
      "args": ["-m", "lkml_mcp.server"]
    }
  }
}
```

## Usage Examples

### Fetch a complete thread
```
lkml_get_thread with message_id: "20251111105634.1684751-1-lzampier@redhat.com"
```

### Fetch raw message content
```
lkml_get_raw with message_id: "20251111105634.1684751-1-lzampier@redhat.com"
```

Note: Message IDs can be provided with or without angle brackets (e.g., `<message-id>` or `message-id`).

## API Reference

### lkml_get_thread
- **Parameters**:
  - `message_id` (string) - The message ID to fetch (e.g., '20251111105634.1684751-1-lzampier@redhat.com'). Can be provided with or without angle brackets.
- **Returns**: All messages in the thread with the following fields for each message:
  - `subject`: Email subject line
  - `from`: Sender information
  - `date`: Message timestamp
  - `message-id`: Unique message identifier
  - `in-reply-to`: Parent message ID (if applicable)
  - `body`: Message content

### lkml_get_raw
- **Parameters**:
  - `message_id` (string) - The message ID to fetch (e.g., '20251111105634.1684751-1-lzampier@redhat.com'). Can be provided with or without angle brackets.
- **Returns**: Raw RFC822 formatted message including all headers and MIME content

## How It Works

The server fetches data from lore.kernel.org using stable message ID URLs with automatic mailing list detection:
- Thread data: `https://lore.kernel.org/r/{message-id}/t.mbox.gz` (compressed mbox format)
  - Uses the `/r/` (redirect) endpoint which automatically detects the correct mailing list
  - Works with any list: lkml, linux-riscv, netdev, devicetree, and all others hosted on lore.kernel.org
- Raw messages: `https://lore.kernel.org/r/{message-id}/raw` (RFC822 format)

The `/r/` endpoint redirects to `/all/` which provides cross-list message access without requiring hardcoded mailing list names.

Messages are parsed to extract relevant fields and presented in a structured format for easy consumption by LLM tools.

## Error Handling

The server includes error handling for:
- Invalid message IDs
- Network timeouts
- Missing or unavailable messages
- Malformed mbox/RFC822 content

All errors are returned as structured error messages through the MCP protocol.

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black src/
isort src/

# Type checking
mypy src/
```
