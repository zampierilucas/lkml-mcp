# LKML MCP Server

Read the Linux kernel mailing lists from inside your AI assistant — no browser tabs, no `git format-patch` gymnastics, no scrolling through lore.kernel.org's HTML.

Ask *"what did the reviewers say about my RISC-V series?"* or *"grab v3 of this patchset so I can `git am` it"* and get a structured answer back. The server talks to [lore.kernel.org](https://lore.kernel.org) (and any compatible public-inbox archive) and hands your assistant clean, parsed threads instead of raw HTML.

## Why

Following kernel review happens over email, and email tooling is hostile to LLMs: deeply nested quotes, MIME soup, bot noise, threads scattered across dozens of replies. This server does the unglamorous parsing so your assistant can reason about the actual conversation — who reviewed what, which tags landed, what changed between versions.

Works against **any** list on lore.kernel.org without hardcoding names — lkml, netdev, linux-riscv, devicetree, kvm, and the rest — plus per-inbox instances like `inbox.sourceware.org` for GCC/Glibc/GDB.

## Tools

| Tool | Ask it for… | You get back |
|------|-------------|--------------|
| `lkml_get_thread` | A full discussion | Every message with subject/from/date/message-id/in-reply-to/body, bot noise filtered out, quoted context preserved |
| `lkml_get_thread_summary` | The shape of a thread | Reply hierarchy, participant list, and review tags (Reviewed-by, Acked-by, Tested-by…) |
| `lkml_get_raw` | One message, untouched | Raw RFC822 with all headers, MIME, and inline diffs |
| `lkml_get_patch` | Something to apply | File paths to clean mbox files ready for `git am` — single patch or whole series |
| `lkml_search_patches` | Patches matching criteria | Series and individual patches by keyword, subsystem, author, or date |
| `lkml_get_user_series` | What someone's been posting | Recent series (cover letters + patches grouped) and standalone messages by email |
| `lkml_compare_patch_versions` | What changed between revisions | Subject changes, file diffs, and added/removed patches across two versions |

## In practice

You don't call these tools directly; you talk to your assistant and it picks the right one. A few things you might say:

- *"Pull up the thread for `20251111105634.1684751-1-lzampier@redhat.com` and tell me if anyone objected."*
- *"Summarize the review tags on this series — did it get enough Reviewed-bys to merge?"*
- *"Find patches touching the riscv subsystem from the last week."*
- *"Compare v2 and v3 of this patchset and show me which files changed."*
- *"Download the whole series as an mbox so I can apply it locally."*

## Installation

Claude Code, one line:

```bash
claude mcp add -s user lkml uvx -- --from "git+https://github.com/zampierilucas/lkml-mcp" lkml-mcp
```

Any other MCP client takes the same `uvx` command — drop this into its config:

```json
{
  "mcpServers": {
    "lkml": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/zampierilucas/lkml-mcp", "lkml-mcp"]
    }
  }
}
```

<details>
<summary>Other setups — Claude Desktop, local clone</summary>

**Claude Desktop** — download `lkml.mcpb` from this repo (or build it with `mcpb pack . lkml.mcpb`), then Settings → Extensions → drag it in → **Enable**.

**Local clone** — for hacking on the server itself (needs Python 3.10+):
```bash
git clone https://github.com/zampierilucas/lkml-mcp.git
cd lkml-mcp && pip install -e .
```
Then point your client at `python -m lkml_mcp.server` instead of the `uvx` command.
</details>

## Tool reference

<details>
<summary><code>lkml_get_thread</code> — fetch a full thread</summary>

- `message_id` (string, required) — with or without angle brackets

Returns every message in the thread, each with `subject`, `from`, `date`, `message-id`, `in-reply-to`, and `body`.

The tool keeps the conversation reconstructable in two ways:

1. **Thread structure** — the `in-reply-to` field links each reply to its parent, so the discussion tree (and its branches) can be rebuilt:
   ```
   Message A (initial patch)
   ├─ Message B (in-reply-to: A) — reviewer comment
   │  └─ Message C (in-reply-to: B) — author response
   └─ Message D (in-reply-to: A) — different reviewer comment
   ```

2. **Quoted context** — the full body, including quoted `>` lines, is preserved so inline replies stay anchored to what they're responding to:
   ```
   > +    ret = kvm_read_guest(vcpu->kvm, gpa, &data, sizeof(data));
   > +    if (ret < 0)
   > +        return ret;

   This looks correct, but you should also handle the case where ret == 0
   since kvm_read_guest() can return 0 for a partial read.
   ```
</details>

<details>
<summary><code>lkml_get_thread_summary</code> — reply tree, participants, tags</summary>

- `message_id` (string, required) — any message in the thread
- `inbox` (string, optional) — required for sourceware-style instances
- `include_bots` (boolean, default `false`)

Returns the reply hierarchy, participant list, and review tags (Reviewed-by, Acked-by, Tested-by, etc.).
</details>

<details>
<summary><code>lkml_get_raw</code> — one message, raw RFC822</summary>

- `message_id` (string, required) — with or without angle brackets

Returns the raw RFC822 message including all headers and MIME content.
</details>

<details>
<summary><code>lkml_get_patch</code> — git am-ready mbox</summary>

- `message_id` (string, required)
- `inbox` (string, optional) — required for sourceware-style instances
- `series` (boolean, default `false`) — `true` fetches every patch in the series
- `include_bots` (boolean, default `false`)

Returns file paths to clean mbox files suitable for `git am`.
</details>

<details>
<summary><code>lkml_search_patches</code> — search by keyword/subsystem/author</summary>

- `query` (string, required)
- `inbox` (string, optional) — required for sourceware-style instances
- `subsystem` (string, optional) — e.g. `net`, `kvm`, `riscv`, `mm`
- `author` (string, optional) — email or name
- `since_date` (string, optional) — `YYYYMMDD`
- `max_results` (integer, default `20`, 1–100)
</details>

<details>
<summary><code>lkml_get_user_series</code> — recent series by email</summary>

- `email` (string, required)
- `inbox` (string, optional) — required for sourceware-style instances
- `max_results` (integer, default `50`, 1–200)

Returns recent patch series (cover letters and patches grouped) plus standalone messages.
</details>

<details>
<summary><code>lkml_compare_patch_versions</code> — diff two revisions</summary>

- `old_message_id` (string, required) — cover letter or first patch of the older version
- `new_message_id` (string, required) — cover letter or first patch of the newer version
- `inbox` (string, optional) — required for sourceware-style instances

Returns subject changes, file differences, and new/removed patches between the two versions.
</details>

## How it works

The server fetches from lore.kernel.org using stable message-ID URLs with automatic list detection:

- **Threads:** `https://lore.kernel.org/r/{message-id}/t.mbox.gz` (compressed mbox)
- **Raw messages:** `https://lore.kernel.org/r/{message-id}/raw` (RFC822)

The `/r/` (redirect) endpoint forwards to `/all/`, which gives cross-list access without hardcoding mailing-list names — so the same URL works whether the message lives on lkml, linux-riscv, netdev, or anywhere else. Messages are parsed into the structured fields above for easy consumption by LLM tools.

## Configuration

### Different archive (`LKML_BASE_URL`)

Defaults to `https://lore.kernel.org`. Point it elsewhere by setting `LKML_BASE_URL`:

```json
{
  "mcpServers": {
    "lkml": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/zampierilucas/lkml-mcp", "lkml-mcp"],
      "env": { "LKML_BASE_URL": "https://custom-lore-instance.org" }
    }
  }
}
```

Local:
```bash
export LKML_BASE_URL="https://custom-lore-instance.org"
python -m lkml_mcp.server
```

### Transport (stdio / SSE / Streamable HTTP)

Runs on stdio by default; can also be exposed over HTTP so multiple clients share one process. Streamable HTTP is stateless under the 2026-07-28 spec — requests can hit any instance behind a load balancer. SSE is deprecated and kept only for older clients.

| Flag | Default | Env override |
|------|---------|--------------|
| `--transport {stdio,sse,streamable-http}` | `stdio` | `LKML_MCP_TRANSPORT` |
| `--host` | `0.0.0.0` | `LKML_MCP_HOST` |
| `--port` | `8772` | `LKML_MCP_PORT` |

Run as a daemon:
```bash
lkml-mcp --transport streamable-http --host 0.0.0.0 --port 8772
# or
lkml-mcp --transport sse --host 0.0.0.0 --port 8772
```

Client endpoints:
- Streamable HTTP: `http://<host>:8772/mcp`
- SSE: `http://<host>:8772/sse` (POSTs to `/messages/`)

Attach the running daemon to Claude Code:
```bash
claude mcp add -s user -t http lkml http://127.0.0.1:8772/mcp
# or for SSE:
claude mcp add -s user -t sse lkml http://127.0.0.1:8772/sse
```

### Multiple archives at once

Run more than one instance to read different archives side by side — say, the kernel lists on lore.kernel.org and GCC/Glibc on inbox.sourceware.org:

```json
{
  "mcpServers": {
    "lkml": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/zampierilucas/lkml-mcp", "lkml-mcp"]
    },
    "sourceware": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/zampierilucas/lkml-mcp", "lkml-mcp"],
      "env": { "LKML_BASE_URL": "https://inbox.sourceware.org" }
    }
  }
}
```

- `lkml` → kernel lists (no `inbox` parameter needed)
- `sourceware` → GCC, Glibc, GDB, binutils (`inbox` parameter **required**)

### Instance types

The server auto-detects which kind of public-inbox instance it's talking to:

| | Universal redirect (lore.kernel.org) | Per-inbox (inbox.sourceware.org) |
|---|---|---|
| `/r/` redirect endpoint | ✅ | ❌ |
| `inbox` parameter | optional | **required** |
| Routing | auto-routes to the right list | you name the inbox |

Common sourceware inboxes: `gcc`, `gcc-patches`, `libc-alpha`, `gdb-patches`, `binutils`.

