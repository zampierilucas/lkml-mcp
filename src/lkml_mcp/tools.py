"""Tool definitions for LKML thread retrieval."""

import os
from typing import Annotated

from mcp.server import MCPServer
from pydantic import Field

from .client import LKMLClient

mcp = MCPServer("lkml-mcp", version="0.1.0")
client = LKMLClient(base_url=os.environ.get("LKML_BASE_URL", "https://lore.kernel.org"))

MessageId = Annotated[
    str,
    Field(description="Message ID (e.g., '20251111105634.1684751-1-lzampier@redhat.com')"),
]
Inbox = Annotated[
    str | None,
    Field(description="Inbox/list name (required for sourceware-style instances, optional for lore.kernel.org)"),
]
IncludeBots = Annotated[
    bool,
    Field(description="Include automated bot messages (kernel test robot, CI bots)."),
]


@mcp.tool(
    description=(
        "Fetch a full LKML thread by message ID from lore.kernel.org or compatible public-inbox instances. "
        "Returns all messages in the thread with subject, from, date, "
        "message-id, in-reply-to, and body content. By default, "
        "filters out automated bot messages (kernel test robot, "
        "CI bots, etc.)."
    ),
    structured_output=False,
)
async def lkml_get_thread(message_id: MessageId, inbox: Inbox = None, include_bots: IncludeBots = False) -> str:
    result = client.get_thread(message_id, inbox=inbox, include_bots=include_bots)

    lines = [
        f"LKML Thread: {result['message_id']}",
        f"Messages: {len(result['messages'])}",
        "",
    ]

    for i, msg in enumerate(result["messages"], 1):
        from_field = msg["from"]
        if "<" in from_field:
            from_name = from_field.split("<")[0].strip()
            from_email = from_field.split("<")[1].rstrip(">")
            from_display = f"{from_name} <{from_email}>"
        else:
            from_display = from_field

        lines.append(f"[{i}] {msg['subject']}")
        lines.append(f"    From: {from_display}")
        lines.append(f"    Date: {msg['date']}")

        if msg.get("in_reply_to"):
            reply_to_id = msg["in_reply_to"].strip("<>")
            lines.append(f"    Reply-To: {reply_to_id}")

        if msg.get("diff_path"):
            lines.append(f"    Diff: {msg['diff_path']}")

        lines.append("")
        for line in msg["body"].split("\n"):
            lines.append(f"    {line}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool(
    description=(
        "Fetch a single LKML message in raw RFC822 format from lore.kernel.org or compatible public-inbox instances. "
        "Useful for getting raw MIME bodies, headers, or inline diffs."
    ),
    structured_output=False,
)
async def lkml_get_raw(message_id: MessageId, inbox: Inbox = None) -> str:
    result = client.get_raw(message_id, inbox=inbox)

    lines = [
        f"Raw LKML Message for message ID: {result['message_id']}",
        "",
        "--- RAW MESSAGE ---",
        result["raw"],
    ]

    return "\n".join(lines)


@mcp.tool(
    description=(
        "Find recent patch series and messages by user email address. "
        "Returns a list of patch series (with cover letters and "
        "patches grouped together) and standalone messages. Useful "
        "for discovering what patches a user has recently proposed "
        "or been involved in."
    ),
    structured_output=False,
)
async def lkml_get_user_series(
    email: Annotated[str, Field(description="User email address (e.g., 'lzampier@redhat.com')")],
    inbox: Inbox = None,
    max_results: Annotated[int, Field(ge=1, le=200, description="Maximum number of messages to retrieve")] = 50,
) -> str:
    result = client.get_user_series(email, inbox=inbox, max_results=max_results)

    lines = [
        f"Recent patch series for: {result['email']}",
        f"Found {len(result['series'])} series",
        "",
        "Use the message_id with lkml_get_thread to fetch the full series.",
        "",
    ]

    for i, series in enumerate(result["series"], 1):
        lines.append(f"[{i}] {series['title']}")
        lines.append(f"    Message ID: {series['message_id']}")
        lines.append(f"    Type: {series['type']}")
        lines.append(f"    Total patches: {series['total_patches']}")
        lines.append(f"    Updated: {series['updated']}")
        lines.append(f"    URL: {series['url']}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool(
    description=(
        "Fetch patches from lore.kernel.org in git am-ready mbox format. "
        "Can fetch a single patch or all patches in a series. "
        "Returns file paths to clean mbox files suitable for 'git am'."
    ),
    structured_output=False,
)
async def lkml_get_patch(
    message_id: MessageId,
    inbox: Inbox = None,
    include_bots: IncludeBots = False,
    series: Annotated[
        bool,
        Field(description="If true, fetch all patches in the series. If false, fetch only this single patch."),
    ] = False,
) -> str:
    result = client.get_patch(message_id, inbox=inbox, include_bots=include_bots, series=series)

    lines = [
        f"Patches for: {result['message_id']}",
        f"Series mode: {result['series']}",
        f"Patches saved: {len(result['patches'])}",
        "",
        "Files are git am-ready. Apply with: git am <path>",
        "",
    ]

    for i, patch in enumerate(result["patches"], 1):
        lines.append(f"[{i}] {patch['subject']}")
        lines.append(f"    Message ID: {patch['message_id']}")
        lines.append(f"    Path: {patch['path']}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool(
    description=(
        "Get a structured summary of an LKML thread: reply hierarchy, "
        "participants, and review tags (Reviewed-by, Acked-by, etc.)."
    ),
    structured_output=False,
)
async def lkml_get_thread_summary(
    message_id: MessageId, inbox: Inbox = None, include_bots: IncludeBots = False
) -> str:
    result = client.get_thread_summary(message_id, inbox=inbox, include_bots=include_bots)

    lines = [
        f"Thread Summary: {result['subject']}",
        f"Author: {result['author']}",
        f"Date: {result['date']}",
        f"Messages: {result['total_messages']}",
        "",
    ]

    if result["participants"]:
        lines.append("Participants:")
        for p in result["participants"]:
            email_part = f" <{p['email']}>" if p["email"] else ""
            lines.append(f"  {p['name']}{email_part} - {p['count']} message(s)")
        lines.append("")

    if result["tags"]:
        lines.append("Review Tags:")
        for tag in result["tags"]:
            email_part = f" <{tag['email']}>" if tag["email"] else ""
            lines.append(f"  {tag['type']}: {tag['name']}{email_part}")
        lines.append("")

    lines.append("Message Tree:")
    for m in result["messages"]:
        indent = "  " * m["depth"]
        patch_marker = " [PATCH]" if m["is_patch"] else ""
        lines.append(f"  {indent}{m['subject']}{patch_marker}")
        lines.append(f"  {indent}  From: {m['from']} | Date: {m['date']}")
        if m["tags"]:
            tag_strs = [f"{t['type']}: {t['name']}" for t in m["tags"]]
            lines.append(f"  {indent}  Tags: {', '.join(tag_strs)}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool(
    description=(
        "Compare two versions of a patch series. Shows subject changes, "
        "file differences, and new/removed patches between versions."
    ),
    structured_output=False,
)
async def lkml_compare_patch_versions(
    old_message_id: Annotated[
        str, Field(description="Message ID of the older version's cover letter or first patch")
    ],
    new_message_id: Annotated[
        str, Field(description="Message ID of the newer version's cover letter or first patch")
    ],
    inbox: Inbox = None,
) -> str:
    result = client.compare_patch_versions(old_message_id, new_message_id, inbox=inbox)

    old_v = result["old_version"]
    new_v = result["new_version"]

    lines = [
        "Patch Version Comparison",
        f"Old: {old_v['version']} ({old_v['patch_count']} patches) - {old_v['message_id']}",
        f"New: {new_v['version']} ({new_v['patch_count']} patches) - {new_v['message_id']}",
        "",
    ]

    if result["changes"]:
        lines.append("Changed Patches:")
        for c in result["changes"]:
            changed = "YES" if c["subject_changed"] else "no"
            lines.append(f"  [{c['patch_number']}] Subject changed: {changed}")
            if c["subject_changed"]:
                lines.append(f"    Old: {c['old_subject']}")
                lines.append(f"    New: {c['new_subject']}")
            else:
                lines.append(f"    {c['new_subject']}")
            if c["files_added"]:
                lines.append(f"    Files added: {', '.join(c['files_added'])}")
            if c["files_removed"]:
                lines.append(f"    Files removed: {', '.join(c['files_removed'])}")
            if c["old_stats"] or c["new_stats"]:
                lines.append(f"    Old stats: {c['old_stats'] or 'N/A'}")
                lines.append(f"    New stats: {c['new_stats'] or 'N/A'}")
            lines.append("")

    if result["patches_added"]:
        lines.append(f"New Patches (added in {new_v['version']}):")
        for p in result["patches_added"]:
            lines.append(f"  [{p['patch_number']}] {p['subject']}")
        lines.append("")

    if result["patches_removed"]:
        lines.append(f"Removed Patches (dropped from {old_v['version']}):")
        for p in result["patches_removed"]:
            lines.append(f"  [{p['patch_number']}] {p['subject']}")
        lines.append("")

    if not result["changes"] and not result["patches_added"] and not result["patches_removed"]:
        lines.append("No differences found between versions.")

    return "\n".join(lines)


@mcp.tool(
    description=(
        "Search for patches by keywords, subsystem, author, or other criteria. "
        "Returns matching patch series and individual patches from lore.kernel.org "
        "or compatible public-inbox instances."
    ),
    structured_output=False,
)
async def lkml_search_patches(
    query: Annotated[str, Field(description="Search query string")],
    inbox: Inbox = None,
    subsystem: Annotated[
        str | None, Field(description="Filter by subsystem (e.g., 'net', 'kvm', 'riscv', 'mm')")
    ] = None,
    author: Annotated[str | None, Field(description="Filter by author email or name")] = None,
    since_date: Annotated[
        str | None,
        Field(pattern=r"^\d{8}$", description="Return patches since this date in YYYYMMDD format"),
    ] = None,
    max_results: Annotated[int, Field(ge=1, le=100, description="Maximum number of results to return")] = 20,
) -> str:
    result = client.search_patches(
        query=query,
        inbox=inbox,
        subsystem=subsystem,
        author=author,
        since_date=since_date,
        max_results=max_results,
    )

    lines = [
        f"Search results for: {result['query']}",
        "",
    ]

    filters = result["filters"]
    active_filters = []
    if filters.get("subsystem"):
        active_filters.append(f"Subsystem: {filters['subsystem']}")
    if filters.get("author"):
        active_filters.append(f"Author: {filters['author']}")
    if filters.get("since_date"):
        active_filters.append(f"Since: {filters['since_date']}")

    if active_filters:
        lines.append("Filters: " + ", ".join(active_filters))
        lines.append("")

    lines.append(f"Found {result['total_results']} results")
    lines.append("")
    lines.append("Use the message_id with lkml_get_thread to fetch full details.")
    lines.append("")

    for i, item in enumerate(result["results"], 1):
        lines.append(f"[{i}] {item['title']}")
        lines.append(f"    Message ID: {item['message_id']}")
        lines.append(f"    Author: {item['author']}")
        lines.append(f"    Updated: {item['updated']}")

        if item["is_patch"] and item["patch_info"]:
            patch_info = item["patch_info"]
            info_parts = []

            if patch_info.get("version"):
                info_parts.append(f"v{patch_info['version']}")

            if patch_info.get("is_series"):
                info_parts.append(f"patch {patch_info['patch_number']}/{patch_info['total_patches']}")
            else:
                info_parts.append("standalone patch")

            if info_parts:
                lines.append(f"    Patch: {', '.join(info_parts)}")

        lines.append(f"    URL: {item['url']}")
        lines.append("")

    return "\n".join(lines)
