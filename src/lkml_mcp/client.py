"""Client for LKML thread retrieval via lore.kernel.org."""

import email
import gzip
import os
import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote_plus

import requests


class LKMLAPIError(Exception):
    """Custom exception for LKML API errors."""

    pass


def _is_bot_message(from_field: str) -> bool:
    """Detect if a message is from an automated bot.

    Args:
        from_field: The From header of the email

    Returns:
        True if this appears to be a bot message
    """
    bot_patterns = [
        "lkp@intel.com",
        "bot@",
        "no-reply@",
        "robot@",
    ]

    from_lower = from_field.lower()
    return any(pattern in from_lower for pattern in bot_patterns)


def _extract_reply_context(body: str, max_lines: int = 5) -> tuple[str, str | None]:
    """Extract meaningful context from a message body.

    For patches: return (commit message + file list + stats, full diff)
    For replies: return (quoted context + full reply, None)
    For discussions: return (first max_lines of actual content, None)

    Returns:
        Tuple of (context_text, diff_text)
    """
    lines = body.split("\n")

    has_diff = False
    diff_start_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("---") and i < len(lines) - 1:
            if (
                lines[i + 1].startswith("+++")
                or lines[i + 1].strip() == ""
                or re.match(r"^\s+\S+\s+\|\s+\d+", lines[i + 1])
            ):
                has_diff = True
                diff_start_idx = i
                break

    if has_diff and diff_start_idx > 0:
        commit_lines = lines[:diff_start_idx]
        diff_text = "\n".join(lines[diff_start_idx:])

        stats_line = None
        for line in lines[diff_start_idx:]:
            if "file" in line and "changed" in line:
                stats_line = line.strip()
                break

        files_changed = []
        in_diff = False
        for line in lines[diff_start_idx:]:
            if line.startswith("diff --git"):
                in_diff = True
                match = re.search(r"b/(.+)$", line)
                if match:
                    files_changed.append(match.group(1))
            elif line.startswith("---") and in_diff:
                match = re.search(r"a/(.+)$", line)
                if match and match.group(1) not in files_changed:
                    files_changed.append(match.group(1))

        result = []
        commit_text = "\n".join(commit_lines).strip()
        if commit_text:
            result.append(commit_text)

        if files_changed:
            result.append(f"\nFiles changed: {', '.join(files_changed[:5])}")
            if len(files_changed) > 5:
                result.append(f"... and {len(files_changed) - 5} more files")

        if stats_line:
            result.append(f"\n{stats_line}")

        return "\n".join(result), diff_text

    result = []
    quoted_buffer = []

    for line in lines:
        if line.strip() == "--" or line.strip() == "-- ":
            break

        if line.startswith(">"):
            quoted_buffer.append(line)
        else:
            if quoted_buffer:
                result.extend(quoted_buffer[-max_lines:])
                quoted_buffer = []
            result.append(line)

    return "\n".join(result).strip(), None


def _parse_from_field(from_field: str) -> tuple[str, str]:
    """Extract name and email from a From header.

    Args:
        from_field: From header value (e.g., 'Lucas Zampieri <lzampier@redhat.com>')

    Returns:
        Tuple of (name, email)
    """
    if "<" in from_field:
        name = from_field.split("<")[0].strip()
        email_addr = from_field.split("<")[1].rstrip(">").strip()
        return name, email_addr
    return from_field.strip(), ""


def _parse_review_tags(body: str) -> list[dict]:
    """Extract review tags from a message body.

    Scans for Reviewed-by, Acked-by, Tested-by, NAKed-by, Nacked-by,
    and Reported-by tags.

    Args:
        body: Message body text

    Returns:
        List of dicts with type, name, and email
    """
    tag_pattern = re.compile(
        r"^(Reviewed-by|Acked-by|Tested-by|(?:NAKed|Nacked)-by|Reported-by)"
        r":\s*(.+?)\s*(?:<([^>]+)>)?\s*$",
        re.MULTILINE,
    )
    tags = []
    for match in tag_pattern.finditer(body):
        tags.append(
            {
                "type": match.group(1),
                "name": match.group(2).strip(),
                "email": match.group(3) or "",
            }
        )
    return tags


_PATCH_TAG = r"\[[^\]]*\bPATCH\b"
"""Opening of a bracketed patch tag, allowing any prefix: [PATCH], [RFC PATCH v2 1/3],
[RESEND PATCH], [PATCH net-next 1/3]."""


def _is_patch_subject(subject: str) -> bool:
    """Check whether a subject line carries a bracketed patch tag.

    Args:
        subject: Email subject (e.g., '[RFC PATCH 0/1] Add foo')

    Returns:
        True if the subject is tagged as a patch
    """
    return bool(re.search(_PATCH_TAG, subject, flags=re.IGNORECASE))


def _parse_patch_subject(subject: str) -> dict:
    """Extract patch metadata from a subject line.

    Args:
        subject: Email subject (e.g., '[PATCH v5 2/3] Fix foo')

    Returns:
        Dict with is_patch, version, patch_number, total
    """
    match = re.search(
        _PATCH_TAG + r"[^\]]*?(?:\s*v(\d+))?[^\]]*?(?:\s+(\d+)/(\d+))?\]",
        subject,
        flags=re.IGNORECASE,
    )
    if not match:
        return {"is_patch": False, "version": None, "patch_number": None, "total": None}
    return {
        "is_patch": True,
        "version": int(match.group(1)) if match.group(1) else None,
        "patch_number": int(match.group(2)) if match.group(2) else None,
        "total": int(match.group(3)) if match.group(3) else None,
    }


def _extract_patch_metadata(body: str) -> dict:
    """Extract structured patch metadata from a message body.

    Args:
        body: Message body text

    Returns:
        Dict with commit_message, files, stats, has_diff
    """
    lines = body.split("\n")

    has_diff = False
    diff_start_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("---") and i < len(lines) - 1:
            if (
                lines[i + 1].startswith("+++")
                or lines[i + 1].strip() == ""
                or re.match(r"^\s+\S+\s+\|\s+\d+", lines[i + 1])
            ):
                has_diff = True
                diff_start_idx = i
                break

    if not has_diff:
        return {
            "commit_message": body.strip(),
            "files": [],
            "stats": None,
            "has_diff": False,
        }

    commit_message = "\n".join(lines[:diff_start_idx]).strip()

    stats = None
    files = []
    for line in lines[diff_start_idx:]:
        if "file" in line and "changed" in line:
            stats = line.strip()
        if line.startswith("diff --git"):
            match = re.search(r"b/(.+)$", line)
            if match:
                files.append(match.group(1))

    return {
        "commit_message": commit_message,
        "files": files,
        "stats": stats,
        "has_diff": True,
    }


class LKMLClient:
    """Client for fetching LKML threads from lore.kernel.org or compatible archives."""

    def __init__(self, base_url: str = "https://lore.kernel.org", timeout: int = 20):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "lkml-mcp/0.1.0"})
        self.BASE_URL = base_url
        self._supports_universal_redirect = self._detect_universal_redirect_support()

    def _detect_universal_redirect_support(self) -> bool:
        """Detect if this instance supports /r/ redirect endpoint.

        Returns:
            True if instance supports /r/ (like lore.kernel.org)
            False if instance requires explicit inbox names (like inbox.sourceware.org)
        """
        if "lore.kernel.org" in self.BASE_URL:
            return True

        if "inbox.sourceware.org" in self.BASE_URL or "sourceware.org" in self.BASE_URL:
            return False

        test_url = f"{self.BASE_URL}/r/test-redirect-detection@example.com/"
        try:
            response = self.session.head(test_url, timeout=5, allow_redirects=False)
            return response.status_code in (200, 302)
        except Exception:
            return False

    def _build_url(self, message_id: str, inbox: str | None, suffix: str) -> str:
        """Build URL based on instance capabilities.

        Args:
            message_id: The message ID (without angle brackets)
            inbox: Optional inbox name (required for non-universal-redirect instances)
            suffix: URL suffix (e.g., 't.mbox.gz', 'raw')

        Returns:
            Properly formatted URL

        Raises:
            ValueError: If inbox is required but not provided
        """
        if self._supports_universal_redirect:
            return f"{self.BASE_URL}/r/{message_id}/{suffix}"

        if not inbox:
            raise ValueError(
                f"inbox parameter is required for {self.BASE_URL}. "
                f"Please specify which mailing list/inbox to query. "
                f"Examples for sourceware: 'gcc', 'gcc-patches', 'libc-alpha', 'gdb-patches'"
            )
        return f"{self.BASE_URL}/{inbox}/{message_id}/{suffix}"

    def _resolve_search_path(self, inbox: str | None) -> str:
        """Resolve the search path based on instance capabilities.

        Args:
            inbox: Optional inbox name

        Returns:
            Search path string ('all' for universal redirect, or inbox name)

        Raises:
            ValueError: If inbox is required but not provided
        """
        if self._supports_universal_redirect:
            return "all"
        if not inbox:
            raise ValueError(
                f"inbox parameter is required for {self.BASE_URL}. "
                f"Please specify which mailing list/inbox to search. "
                f"Examples for sourceware: 'gcc', 'gcc-patches', 'libc-alpha', 'gdb-patches'"
            )
        return inbox

    @staticmethod
    def _split_mbox(mbox_text: str) -> list[str]:
        """Split mbox text into individual raw messages.

        Args:
            mbox_text: Raw mbox text content

        Returns:
            List of raw message strings
        """
        raw_messages = []
        current_message = []
        for line in mbox_text.split("\n"):
            if line.startswith("From ") and current_message:
                raw_messages.append("\n".join(current_message))
                current_message = []
            else:
                current_message.append(line)
        if current_message:
            raw_messages.append("\n".join(current_message))
        return raw_messages

    def _fetch_mbox(self, message_id: str, inbox: str | None) -> list[str]:
        """Fetch and split an mbox archive for a message thread.

        Args:
            message_id: The message ID (without angle brackets)
            inbox: Optional inbox name

        Returns:
            List of raw message strings from the mbox
        """
        url = self._build_url(message_id, inbox, "t.mbox.gz")
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        mbox_data = gzip.decompress(response.content)
        return self._split_mbox(mbox_data.decode("utf-8", errors="ignore"))

    @staticmethod
    def _decode_payload(msg) -> str:
        """Decode email message payload with charset detection.

        Args:
            msg: An email.message.Message object

        Returns:
            Decoded body text
        """
        if msg.is_multipart():
            body = ""
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        body += payload.decode(charset, errors="ignore")
            return body
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="ignore")
        return ""

    def _parse_atom_entries(self, base_url: str, max_results: int) -> list[dict]:
        """Parse paginated Atom feed entries.

        Args:
            base_url: Base URL for the Atom feed query
            max_results: Maximum number of entries to return

        Returns:
            List of dicts with message_id, title, updated, author, url
        """
        all_entries = []
        page_size = 200
        offset = 0

        while len(all_entries) < max_results:
            url = base_url if offset == 0 else f"{base_url}&o={offset}"
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()

            root = ET.fromstring(response.content)
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "thr": "http://purl.org/syndication/thread/1.0",
            }

            entries_in_page = root.findall("atom:entry", ns)
            if not entries_in_page:
                break

            for entry in entries_in_page:
                if len(all_entries) >= max_results:
                    break
                title_elem = entry.find("atom:title", ns)
                link_elem = entry.find("atom:link", ns)
                updated_elem = entry.find("atom:updated", ns)
                author_elem = entry.find("atom:author/atom:name", ns)

                href = link_elem.get("href") if link_elem is not None else ""
                msg_id = ""
                if href:
                    match = re.search(r"/([^/]+)/?$", href.rstrip("/"))
                    if match:
                        msg_id = match.group(1)

                all_entries.append(
                    {
                        "message_id": msg_id,
                        "title": title_elem.text if title_elem is not None else "",
                        "updated": updated_elem.text if updated_elem is not None else "",
                        "author": author_elem.text if author_elem is not None else "",
                        "url": href,
                    }
                )

            if len(entries_in_page) < page_size:
                break
            offset += page_size

        return all_entries

    @staticmethod
    def _clean_message(msg_text: str) -> str:
        """Strip transport headers from an mbox message for git am.

        Parses the raw message and reconstructs it with only the headers
        that git am needs (From, Subject, Date, Message-ID, In-Reply-To,
        References, MIME-Version, Content-Type, Content-Transfer-Encoding).
        Strips all transport headers (Received, DKIM, ARC, etc.) and
        mbox envelope lines.

        Args:
            msg_text: Raw mbox message text

        Returns:
            Cleaned mbox message text suitable for git am
        """
        msg = email.message_from_string(msg_text)

        # Headers git am needs
        keep_headers = [
            "From", "To", "Cc", "Subject", "Date", "Message-ID",
            "In-Reply-To", "References", "MIME-Version",
            "Content-Type", "Content-Transfer-Encoding",
        ]

        # Build clean header block
        header_lines = []
        for hdr in keep_headers:
            value = msg.get(hdr)
            if value:
                header_lines.append(f"{hdr}: {value}")

        # Get raw body (undecoded, preserving original encoding)
        payload = msg.get_payload(decode=False)
        if isinstance(payload, list):
            # Multipart - fall back to string representation
            body = msg.as_string().split("\n\n", 1)[1] if "\n\n" in msg.as_string() else ""
        elif isinstance(payload, bytes):
            body = payload.decode("utf-8", errors="ignore")
        else:
            body = payload or ""

        # Un-escape >From lines in body
        body_lines = []
        for line in body.split("\n"):
            if line.startswith(">From"):
                body_lines.append(line[1:])
            else:
                body_lines.append(line)
        body = "\n".join(body_lines)

        return "\n".join(header_lines) + "\n\n" + body

    @staticmethod
    def _save_patch(msg_id: str, content: str, patch_dir: str) -> str:
        """Save a clean patch mbox to disk.

        Args:
            msg_id: Message ID (used for filename)
            content: Clean mbox content
            patch_dir: Directory to save to

        Returns:
            Path to saved file
        """
        safe_id = msg_id.replace("/", "_").replace("@", "_at_")
        path = os.path.join(patch_dir, f"{safe_id}.mbox")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def get_thread(
        self, message_id: str, inbox: str | None = None, include_bots: bool = False
    ) -> dict[str, Any]:
        """Fetch one LKML thread by message-id from lore.kernel.org or compatible archives.

        Args:
            message_id: The message ID (e.g., '20251111105634.1684751-1-lzampier@redhat.com')
            inbox: Inbox/list name (required for sourceware-style instances). Examples: 'gcc', 'libc-alpha'
            include_bots: If True, include bot messages. If False (default), filter them out.

        Returns:
            Dictionary containing list of messages with subject/from/date/body

        Raises:
            ValueError: If inbox is required but not provided
        """
        message_id = message_id.strip("<>")

        try:
            raw_messages = self._fetch_mbox(message_id, inbox)
            messages = []

            diff_dir = "/tmp/lkml-mcp"
            os.makedirs(diff_dir, exist_ok=True)

            for raw_msg in raw_messages:
                if not raw_msg.strip():
                    continue
                msg = email.message_from_string(raw_msg)

                body = self._decode_payload(msg)

                from_field = msg.get("from", "")
                if not include_bots and _is_bot_message(from_field):
                    continue

                context, diff_text = _extract_reply_context(body, max_lines=5)
                msg_id = msg.get("message-id", "").strip("<>")
                diff_path = None

                if diff_text:
                    safe_msg_id = msg_id.replace("/", "_").replace("@", "_at_")
                    diff_path = os.path.join(diff_dir, f"{safe_msg_id}.diff")
                    with open(diff_path, "w", encoding="utf-8") as f:
                        f.write(diff_text)

                message_data = {
                    "subject": msg.get("subject", ""),
                    "from": msg.get("from", ""),
                    "date": msg.get("date", ""),
                    "message_id": msg.get("message-id", ""),
                    "in_reply_to": msg.get("in-reply-to", ""),
                    "body": context,
                }

                if diff_path:
                    message_data["diff_path"] = diff_path

                messages.append(message_data)

            return {"message_id": message_id, "messages": messages}

        except ValueError:
            raise
        except requests.exceptions.RequestException as e:
            raise LKMLAPIError(f"Failed to fetch thread: {e}") from e
        except Exception as e:
            raise LKMLAPIError(f"Failed to parse mbox data: {e}") from e

    def get_raw(self, message_id: str, inbox: str | None = None) -> dict[str, Any]:
        """Fetch a single LKML message in raw RFC822 format.

        Args:
            message_id: The message ID (e.g., '20251111105634.1684751-1-lzampier@redhat.com')
            inbox: Inbox/list name (required for sourceware-style instances). Examples: 'gcc', 'libc-alpha'

        Returns:
            Dictionary with message_id and raw message content

        Raises:
            ValueError: If inbox is required but not provided
        """
        message_id = message_id.strip("<>")
        url = self._build_url(message_id, inbox, "raw")

        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()

            return {"message_id": message_id, "raw": response.text}

        except requests.exceptions.RequestException as e:
            raise LKMLAPIError(f"Failed to fetch raw message: {e}") from e

    def _get_patch_series(
        self, message_id: str, inbox: str | None = None
    ) -> list[tuple[str, str, str]]:
        """Fetch all patches in a series from the thread mbox.

        Uses the thread mbox to discover all patches, filtering out
        replies and bot messages.

        Args:
            message_id: Message ID of any patch in the series
            inbox: Optional inbox name

        Returns:
            List of (message_id, subject, cleaned_mbox_content) tuples,
            sorted by patch number
        """
        raw_messages = self._fetch_mbox(message_id, inbox)
        patches = []

        for raw_msg in raw_messages:
            if not raw_msg.strip():
                continue
            msg = email.message_from_string(raw_msg)

            subject = msg.get("subject", "")
            from_field = msg.get("from", "")
            msg_id = msg.get("message-id", "").strip("<>")

            # Skip replies (non-patch messages)
            if re.match(r"^Re:\s*", subject, flags=re.IGNORECASE):
                continue

            # Skip bot messages
            if _is_bot_message(from_field):
                continue

            # Only include messages that look like patches
            if not _is_patch_subject(subject):
                continue

            cleaned = self._clean_message(raw_msg)
            patches.append((msg_id, subject, cleaned))

        # Sort by message ID to preserve patch order
        patches.sort(key=lambda p: p[0])
        return patches

    def get_patch(
        self,
        message_id: str,
        inbox: str | None = None,
        include_bots: bool = False,
        series: bool = False,
    ) -> dict[str, Any]:
        """Fetch patches in git am-ready mbox format.

        Can fetch a single patch or discover and fetch all patches in a series.
        Returns file paths to clean mbox files suitable for piping to 'git am'.

        Args:
            message_id: Message ID of the patch
            inbox: Inbox/list name (required for sourceware-style instances)
            include_bots: If True, include bot messages. Default False.
            series: If True, fetch all patches in the series. Default False.

        Returns:
            Dictionary with message_id, series flag, and list of patch info dicts

        Raises:
            ValueError: If inbox is required but not provided
        """
        message_id = message_id.strip("<>")
        patch_dir = "/tmp/lkml-mcp"
        os.makedirs(patch_dir, exist_ok=True)

        try:
            if series:
                patch_tuples = self._get_patch_series(message_id, inbox)
                patches = []
                for msg_id, subject, content in patch_tuples:
                    path = self._save_patch(msg_id, content, patch_dir)
                    patches.append(
                        {
                            "message_id": msg_id,
                            "subject": subject,
                            "path": path,
                        }
                    )
            else:
                # Single patch mode
                raw_messages = self._fetch_mbox(message_id, inbox)
                patches = []

                for raw_msg in raw_messages:
                    if not raw_msg.strip():
                        continue
                    msg = email.message_from_string(raw_msg)

                    subject = msg.get("subject", "")
                    from_field = msg.get("from", "")
                    msg_id = msg.get("message-id", "").strip("<>")

                    # Skip replies
                    if re.match(r"^Re:\s*", subject, flags=re.IGNORECASE):
                        continue

                    # Skip bots unless requested
                    if not include_bots and _is_bot_message(from_field):
                        continue

                    cleaned = self._clean_message(raw_msg)
                    path = self._save_patch(msg_id, cleaned, patch_dir)
                    patches.append(
                        {
                            "message_id": msg_id,
                            "subject": subject,
                            "path": path,
                        }
                    )
                    # In single mode, only save the first actual patch
                    break

            return {
                "message_id": message_id,
                "series": series,
                "patches": patches,
            }

        except requests.exceptions.RequestException as e:
            raise LKMLAPIError(f"Failed to fetch patch: {e}") from e
        except Exception as e:
            raise LKMLAPIError(f"Failed to process patch: {e}") from e

    def get_thread_summary(
        self,
        message_id: str,
        inbox: str | None = None,
        include_bots: bool = False,
    ) -> dict[str, Any]:
        """Get a structured summary of a thread with reply hierarchy and review tags.

        Args:
            message_id: The message ID of any message in the thread
            inbox: Inbox/list name (required for sourceware-style instances)
            include_bots: If True, include bot messages

        Returns:
            Dictionary with thread summary including reply tree, participants, and tags
        """
        message_id = message_id.strip("<>")

        try:
            raw_messages = self._fetch_mbox(message_id, inbox)
            parsed = []

            for raw_msg in raw_messages:
                if not raw_msg.strip():
                    continue
                msg = email.message_from_string(raw_msg)

                from_field = msg.get("from", "")
                if not include_bots and _is_bot_message(from_field):
                    continue

                body = self._decode_payload(msg)
                msg_id = msg.get("message-id", "").strip("<>")
                subject = msg.get("subject", "")
                in_reply_to = msg.get("in-reply-to", "").strip("<>")
                date = msg.get("date", "")
                name, email_addr = _parse_from_field(from_field)
                tags = _parse_review_tags(body)
                patch_info = _parse_patch_subject(subject)

                parsed.append(
                    {
                        "message_id": msg_id,
                        "subject": subject,
                        "from": from_field,
                        "from_name": name,
                        "from_email": email_addr,
                        "date": date,
                        "in_reply_to": in_reply_to,
                        "tags": tags,
                        "is_patch": patch_info["is_patch"]
                        and not re.match(r"^Re:\s*", subject, flags=re.IGNORECASE),
                    }
                )

            # Build reply tree
            by_id = {m["message_id"]: m for m in parsed}
            children: dict[str, list] = {}
            roots = []

            for m in parsed:
                parent_id = m["in_reply_to"]
                if parent_id and parent_id in by_id:
                    children.setdefault(parent_id, []).append(m)
                else:
                    roots.append(m)

            # DFS to assign depth and build ordered list
            ordered = []
            visited = set()

            def dfs(node, depth):
                if node["message_id"] in visited:
                    return
                visited.add(node["message_id"])
                node["depth"] = depth
                ordered.append(node)
                for child in children.get(node["message_id"], []):
                    dfs(child, depth + 1)

            for root in roots:
                dfs(root, 0)

            # Add any unvisited messages (orphans)
            for m in parsed:
                if m["message_id"] not in visited:
                    m["depth"] = 0
                    ordered.append(m)

            # Aggregate participants
            participant_counts: dict[tuple, int] = {}
            for m in parsed:
                key = (m["from_name"], m["from_email"])
                participant_counts[key] = participant_counts.get(key, 0) + 1

            participants = [
                {"name": name, "email": email_addr, "count": count}
                for (name, email_addr), count in sorted(
                    participant_counts.items(), key=lambda x: -x[1]
                )
            ]

            # Aggregate tags with source message
            all_tags = []
            for m in parsed:
                for tag in m["tags"]:
                    all_tags.append({**tag, "in_message": m["message_id"]})

            # Thread root info
            root = ordered[0] if ordered else {}

            # Build clean message list for output
            messages = [
                {
                    "message_id": m["message_id"],
                    "subject": m["subject"],
                    "from": m["from"],
                    "date": m["date"],
                    "depth": m["depth"],
                    "tags": m["tags"],
                    "is_patch": m["is_patch"],
                }
                for m in ordered
            ]

            return {
                "message_id": message_id,
                "subject": root.get("subject", ""),
                "author": root.get("from", ""),
                "date": root.get("date", ""),
                "total_messages": len(parsed),
                "participants": participants,
                "tags": all_tags,
                "messages": messages,
            }

        except ValueError:
            raise
        except requests.exceptions.RequestException as e:
            raise LKMLAPIError(f"Failed to fetch thread: {e}") from e
        except Exception as e:
            raise LKMLAPIError(f"Failed to build thread summary: {e}") from e

    def compare_patch_versions(
        self,
        old_message_id: str,
        new_message_id: str,
        inbox: str | None = None,
    ) -> dict[str, Any]:
        """Compare two versions of a patch series.

        Args:
            old_message_id: Message ID of the older version's cover letter or first patch
            new_message_id: Message ID of the newer version's cover letter or first patch
            inbox: Inbox/list name (required for sourceware-style instances)

        Returns:
            Dictionary with version comparison showing changes, additions, and removals
        """
        old_message_id = old_message_id.strip("<>")
        new_message_id = new_message_id.strip("<>")

        try:
            old_raw = self._fetch_mbox(old_message_id, inbox)
            new_raw = self._fetch_mbox(new_message_id, inbox)

            def parse_patches(raw_messages):
                patches = []
                version = None
                for raw_msg in raw_messages:
                    if not raw_msg.strip():
                        continue
                    msg = email.message_from_string(raw_msg)
                    subject = msg.get("subject", "")
                    from_field = msg.get("from", "")

                    if re.match(r"^Re:\s*", subject, flags=re.IGNORECASE):
                        continue
                    if _is_bot_message(from_field):
                        continue
                    if not _is_patch_subject(subject):
                        continue

                    body = self._decode_payload(msg)
                    patch_info = _parse_patch_subject(subject)
                    metadata = _extract_patch_metadata(body)

                    if patch_info["version"] and version is None:
                        version = patch_info["version"]

                    patches.append(
                        {
                            "patch_number": patch_info["patch_number"],
                            "subject": subject,
                            "title": re.sub(
                                _PATCH_TAG + r"[^\]]*\]\s*", "", subject
                            ),
                            "files": metadata["files"],
                            "stats": metadata["stats"],
                        }
                    )

                patches.sort(key=lambda p: p["patch_number"] or 0)
                return patches, version

            old_patches, old_version = parse_patches(old_raw)
            new_patches, new_version = parse_patches(new_raw)

            # Build lookup by patch number (exclude cover letters)
            old_by_num = {
                p["patch_number"]: p for p in old_patches if p["patch_number"]
            }
            new_by_num = {
                p["patch_number"]: p for p in new_patches if p["patch_number"]
            }

            all_nums = sorted(set(old_by_num.keys()) | set(new_by_num.keys()))

            changes = []
            patches_added = []
            patches_removed = []

            for num in all_nums:
                old_p = old_by_num.get(num)
                new_p = new_by_num.get(num)

                if old_p and new_p:
                    old_files = set(old_p["files"])
                    new_files = set(new_p["files"])
                    changes.append(
                        {
                            "patch_number": num,
                            "old_subject": old_p["subject"],
                            "new_subject": new_p["subject"],
                            "subject_changed": old_p["title"] != new_p["title"],
                            "old_files": old_p["files"],
                            "new_files": new_p["files"],
                            "files_added": sorted(new_files - old_files),
                            "files_removed": sorted(old_files - new_files),
                            "old_stats": old_p["stats"],
                            "new_stats": new_p["stats"],
                        }
                    )
                elif new_p:
                    patches_added.append(
                        {"patch_number": num, "subject": new_p["subject"]}
                    )
                elif old_p:
                    patches_removed.append(
                        {"patch_number": num, "subject": old_p["subject"]}
                    )

            return {
                "old_version": {
                    "message_id": old_message_id,
                    "version": f"v{old_version}" if old_version else "v1",
                    "patch_count": len(
                        [p for p in old_patches if p["patch_number"]]
                    ),
                },
                "new_version": {
                    "message_id": new_message_id,
                    "version": f"v{new_version}" if new_version else "v1",
                    "patch_count": len(
                        [p for p in new_patches if p["patch_number"]]
                    ),
                },
                "changes": changes,
                "patches_added": patches_added,
                "patches_removed": patches_removed,
            }

        except ValueError:
            raise
        except requests.exceptions.RequestException as e:
            raise LKMLAPIError(f"Failed to fetch patches: {e}") from e
        except Exception as e:
            raise LKMLAPIError(f"Failed to compare versions: {e}") from e

    def get_user_series(
        self, email: str, inbox: str | None = None, max_results: int = 50
    ) -> dict[str, Any]:
        """Find recent patch series by user email.

        Args:
            email: User email address (e.g., 'lzampier@redhat.com')
            inbox: Inbox/list name to search (optional for lore, recommended for sourceware)
            max_results: Maximum number of messages to retrieve (default: 50)

        Returns:
            Dictionary containing list of series with their root message IDs
        """
        search_path = self._resolve_search_path(inbox)

        encoded_query = quote_plus(f"f:{email}")
        base_url = f"{self.BASE_URL}/{search_path}/?q={encoded_query}&x=A"

        try:
            all_entries = self._parse_atom_entries(base_url, max_results)

            filtered_entries = []
            for entry in all_entries:
                title = entry["title"]
                if re.match(r"^Re:\s*", title, flags=re.IGNORECASE):
                    continue

                msg_id = entry["message_id"]

                # Use timestamp prefix for within-version grouping (cover letter + patches)
                # This groups all messages from the same patch series submission together
                prefix_match = re.match(r"^(\d+\.\d+)", msg_id)
                if prefix_match:
                    entry["version_key"] = prefix_match.group(1)
                else:
                    entry["version_key"] = msg_id

                # Use normalized title for cross-version grouping
                # This groups different versions (v1, v2, v3) of the same series together
                series_key = title
                # Normalize the entire patch prefix to group all versions together
                # Remove RFC, version numbers, and patch numbers
                series_key = re.sub(
                    _PATCH_TAG + r"[^\]]*\]",
                    "[PATCH]",
                    series_key,
                )
                entry["series_key"] = series_key

                filtered_entries.append(entry)

            series_list = []
            seen_series = set()  # Tracks series_key (cross-version)
            seen_versions = set()  # Tracks version_key (within-version)

            # First pass: Find cover letters (highest priority)
            for entry in filtered_entries:
                title = entry["title"]
                series_key = entry["series_key"]
                version_key = entry["version_key"]

                cover_match = re.search(_PATCH_TAG + r"[^\]]*\s+0/(\d+)\]", title)
                if cover_match:
                    # Always mark version as seen, even if we skip this cover letter
                    # This prevents patches from skipped versions from being added
                    seen_versions.add(version_key)

                    if series_key not in seen_series:
                        series_list.append(
                            {
                                "message_id": entry["message_id"],
                                "title": title,
                                "updated": entry["updated"],
                                "url": entry["url"],
                                "type": "cover_letter",
                                "total_patches": int(cover_match.group(1)),
                            }
                        )
                        seen_series.add(series_key)

            # Second pass: Find first patches or standalone patches for series without cover letters
            for entry in filtered_entries:
                title = entry["title"]
                series_key = entry["series_key"]
                version_key = entry["version_key"]

                if series_key in seen_series or version_key in seen_versions:
                    continue

                # Check for first patch in a series (e.g., [PATCH 1/3])
                first_patch_match = re.search(_PATCH_TAG + r"[^\]]*\s+1/(\d+)\]", title)
                if first_patch_match:
                    series_list.append(
                        {
                            "message_id": entry["message_id"],
                            "title": title,
                            "updated": entry["updated"],
                            "url": entry["url"],
                            "type": "first_patch",
                            "total_patches": int(first_patch_match.group(1)),
                        }
                    )
                    seen_series.add(series_key)
                    seen_versions.add(version_key)
                    continue

                # Check for standalone patch (e.g., [PATCH] without X/N notation)
                if re.search(_PATCH_TAG + r"[^\]]*\]", title) and not re.search(r"\d+/\d+", title):
                    series_list.append(
                        {
                            "message_id": entry["message_id"],
                            "title": title,
                            "updated": entry["updated"],
                            "url": entry["url"],
                            "type": "single_patch",
                            "total_patches": 1,
                        }
                    )
                    seen_series.add(series_key)
                    seen_versions.add(version_key)

            return {
                "email": email,
                "series": series_list,
            }

        except requests.exceptions.RequestException as e:
            raise LKMLAPIError(f"Failed to search for user messages: {e}") from e
        except ET.ParseError as e:
            raise LKMLAPIError(f"Failed to parse Atom feed: {e}") from e
        except Exception as e:
            raise LKMLAPIError(f"Failed to process user series: {e}") from e

    def search_patches(
        self,
        query: str,
        inbox: str | None = None,
        subsystem: str | None = None,
        author: str | None = None,
        since_date: str | None = None,
        max_results: int = 20,
    ) -> dict[str, Any]:
        """Search for patches by keywords and filters.

        Args:
            query: Search query string
            inbox: Inbox/list name to search (optional for lore, recommended for sourceware)
            subsystem: Optional subsystem filter (e.g., 'net', 'kvm')
            author: Optional author email or name filter
            since_date: Optional date filter in YYYYMMDD format
            max_results: Maximum number of results (default: 20)

        Returns:
            Dictionary containing list of matching patches
        """
        search_path = self._resolve_search_path(inbox)

        search_terms = [query]

        if subsystem:
            search_terms.append(f"s:{subsystem}")
        if author:
            search_terms.append(f"f:{author}")
        if since_date:
            # Format as YYYY-MM-DD for Xapian date filter
            formatted_date = f"{since_date[:4]}-{since_date[4:6]}-{since_date[6:8]}"
            search_terms.append(f"d:{formatted_date}..")

        search_query = " ".join(search_terms)
        encoded_query = quote_plus(search_query)
        base_url = f"{self.BASE_URL}/{search_path}/?q={encoded_query}&x=A"

        try:
            raw_entries = self._parse_atom_entries(base_url, max_results)

            results = []
            for entry in raw_entries:
                title = entry["title"]
                is_patch = _is_patch_subject(title)
                patch_info = {}

                if is_patch:
                    version_match = re.search(_PATCH_TAG + r"[^\]]*v(\d+)", title, flags=re.IGNORECASE)
                    series_match = re.search(_PATCH_TAG + r"[^\]]*\s+(\d+)/(\d+)\]", title, flags=re.IGNORECASE)

                    if version_match:
                        patch_info["version"] = int(version_match.group(1))

                    if series_match:
                        patch_info["patch_number"] = int(series_match.group(1))
                        patch_info["total_patches"] = int(series_match.group(2))
                        patch_info["is_series"] = True
                    else:
                        patch_info["is_series"] = False

                results.append(
                    {
                        "message_id": entry["message_id"],
                        "title": title,
                        "author": entry["author"],
                        "updated": entry["updated"],
                        "url": entry["url"],
                        "is_patch": is_patch,
                        "patch_info": patch_info if is_patch else None,
                    }
                )

            return {
                "query": query,
                "filters": {
                    "subsystem": subsystem,
                    "author": author,
                    "since_date": since_date,
                },
                "total_results": len(results),
                "results": results,
            }

        except requests.exceptions.RequestException as e:
            raise LKMLAPIError(f"Failed to search patches: {e}") from e
        except ET.ParseError as e:
            raise LKMLAPIError(f"Failed to parse search results: {e}") from e
        except Exception as e:
            raise LKMLAPIError(f"Failed to process search results: {e}") from e
