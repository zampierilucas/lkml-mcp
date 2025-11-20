"""Tool handlers for LKML thread retrieval."""

from typing import Any, Dict, List

from mcp.types import TextContent

from .client import LKMLClient


async def handle_lkml_get_thread(client: LKMLClient, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle lkml_get_thread tool call."""
    message_id = arguments.get("message_id")
    if not message_id:
        raise ValueError("message_id is required")

    include_bots = arguments.get("include_bots", False)
    result = client.get_thread(message_id, include_bots=include_bots)

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

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_lkml_get_raw(client: LKMLClient, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle lkml_get_raw tool call."""
    message_id = arguments.get("message_id")
    if not message_id:
        raise ValueError("message_id is required")

    result = client.get_raw(message_id)

    lines = [
        f"Raw LKML Message for message ID: {result['message_id']}",
        "",
        "--- RAW MESSAGE ---",
        result["raw"],
    ]

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_lkml_get_user_series(client: LKMLClient, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle lkml_get_user_series tool call."""
    email = arguments.get("email")
    if not email:
        raise ValueError("email is required")

    max_results = arguments.get("max_results", 50)
    result = client.get_user_series(email, max_results=max_results)

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

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_lkml_search_patches(client: LKMLClient, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle lkml_search_patches tool call."""
    query = arguments.get("query")
    if not query:
        raise ValueError("query is required")

    subsystem = arguments.get("subsystem")
    author = arguments.get("author")
    since_date = arguments.get("since_date")
    max_results = arguments.get("max_results", 20)

    result = client.search_patches(
        query=query,
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

    return [TextContent(type="text", text="\n".join(lines))]
