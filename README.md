# LKML MCP Server

A Model Context Protocol (MCP) server for accessing Linux Kernel Mailing List threads via lore.kernel.org. This server provides tools to fetch complete email threads and raw message content from any kernel mailing list archive (lkml, linux-riscv, netdev, etc.).

## Tools

- **lkml_get_thread**: Fetch a full thread by message ID, returning all messages in the thread with structured metadata (subject, from, date, message-id, in-reply-to, body content). By default, filters out automated bot messages
- **lkml_get_raw**: Fetch a single message in raw RFC822 format, useful for getting raw MIME bodies, headers, or inline diffs
- **lkml_get_user_series**: Find recent patch series and messages by user email address. Returns a list of patch series with cover letters and patches grouped together, plus standalone messages
- **lkml_search_patches**: Search for patches by keywords, subsystem, author, or other criteria. Returns matching patch series and individual patches
- **Cross-mailing-list support**: Works with any mailing list on lore.kernel.org without hardcoding list names (lkml, linux-riscv, netdev, devicetree, etc.)

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

## Tool Reference

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

**Thread Context Preservation**: The tool maintains the full conversation context in two ways:

1. **Thread Structure**: Preserves the `in-reply-to` field linking each reply to its parent message, enabling reconstruction of the discussion tree and tracking of conversation branches.

2. **Quoted Context**: Preserves the complete message body including quoted text (lines starting with `>`) from previous messages. This allows you to see exactly what the user was commenting on by maintaining the quoted lines above their inline responses.

Example thread structure:
```
Message A (initial patch)
├─ Message B (in-reply-to: A) - reviewer comment
│  └─ Message C (in-reply-to: B) - author response
└─ Message D (in-reply-to: A) - different reviewer comment
```

C Example of preserved quoted context in a reply:
```
> +    ret = kvm_read_guest(vcpu->kvm, gpa, &data, sizeof(data));
> +    if (ret < 0)
> +        return ret;

This looks correct, but you should also handle the case where ret == 0
since kvm_read_guest() can return 0 for a partial read.
```

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

## Installation by Platform

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

### Claude Desktop

Install as a Desktop Extension:

1. Download `lkml.mcpb` from this repository or build it: `mcpb pack . lkml.mcpb`
2. Open Claude Desktop → Settings → Extensions
3. Drag and drop `lkml.mcpb` into the Extensions window
4. Click "Enable" to activate the extension

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

## Configuration

### BASE_URL

By default, the server connects to `https://lore.kernel.org`. You can configure it to use a different public-inbox archive by setting the `LKML_BASE_URL` environment variable.

**Claude Code (CLI)**:
```json
{
  "mcpServers": {
    "lkml": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/zampierilucas/lkml-mcp",
        "lkml-mcp"
      ],
      "env": {
        "LKML_BASE_URL": "https://custom-lore-instance.org"
      }
    }
  }
}
```

**Local Installation**:
```bash
export LKML_BASE_URL="https://custom-lore-instance.org"
python -m lkml_mcp.server
```

### Multi-Instance Setup

You can configure multiple MCP server instances to access different public-inbox archives simultaneously. This is useful for accessing both Linux kernel mailing lists (lore.kernel.org) and other projects (like GCC, Glibc on inbox.sourceware.org).

**Claude Code (CLI) - Multiple Servers**:
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
    },
    "sourceware": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/zampierilucas/lkml-mcp",
        "lkml-mcp"
      ],
      "env": {
        "LKML_BASE_URL": "https://inbox.sourceware.org"
      }
    }
  }
}
```

With this setup:
- Use the `lkml` server for Linux kernel mailing lists (no inbox parameter needed)
- Use the `sourceware` server for GCC, Glibc, GDB, binutils lists (inbox parameter required)

### Instance Types

The server automatically detects the public-inbox instance type:

**Universal Redirect Instances (like lore.kernel.org)**:
- Support `/r/` redirect endpoint
- `inbox` parameter is optional
- Automatically routes to the correct mailing list

**Per-Inbox Instances (like inbox.sourceware.org)**:
- Require explicit inbox names
- `inbox` parameter is **required** for all operations
- Common inbox names:
  - `gcc` - GCC general discussion
  - `gcc-patches` - GCC patches
  - `libc-alpha` - Glibc development
  - `gdb-patches` - GDB patches
  - `binutils` - Binutils discussion

## Prerequisites

- Python 3.8+
- **uvx** - Package runner for Python (install with `pip install uv`)
- Internet access to `https://lore.kernel.org` (or your configured BASE_URL)

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
