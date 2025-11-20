"""Client for LKML thread retrieval via lore.kernel.org."""

import email
import gzip
import os
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict

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


class LKMLClient:
    """Client for fetching LKML threads from lore.kernel.org or compatible archives."""

    def __init__(self, base_url: str = "https://lore.kernel.org", timeout: int = 20):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "lkml-mcp/0.1.0"})
        self.BASE_URL = base_url

    def get_thread(self, message_id: str, include_bots: bool = False) -> Dict[str, Any]:
        """Fetch one LKML thread by message-id from lore.kernel.org.

        Args:
            message_id: The message ID (e.g., '20251111105634.1684751-1-lzampier@redhat.com')
            include_bots: If True, include bot messages. If False (default), filter them out.

        Returns:
            Dictionary containing list of messages with subject/from/date/body
        """
        message_id = message_id.strip("<>")
        url = f"{self.BASE_URL}/r/{message_id}/t.mbox.gz"

        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()

            mbox_data = gzip.decompress(response.content)
            messages = []
            mbox_text = mbox_data.decode("utf-8", errors="ignore")

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

            diff_dir = "/tmp/lkml-mcp"
            os.makedirs(diff_dir, exist_ok=True)

            for raw_msg in raw_messages:
                if not raw_msg.strip():
                    continue
                msg = email.message_from_string(raw_msg)

                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            payload = part.get_payload(decode=True)
                            if payload:
                                body += payload.decode(errors="ignore")
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body = payload.decode(errors="ignore")

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

        except requests.exceptions.RequestException as e:
            raise LKMLAPIError(f"Failed to fetch thread: {e}") from e
        except Exception as e:
            raise LKMLAPIError(f"Failed to parse mbox data: {e}") from e

    def get_raw(self, message_id: str) -> Dict[str, Any]:
        """Fetch a single LKML message in raw RFC822 format.

        Args:
            message_id: The message ID (e.g., '20251111105634.1684751-1-lzampier@redhat.com')

        Returns:
            Dictionary with message_id and raw message content
        """
        message_id = message_id.strip("<>")
        url = f"{self.BASE_URL}/r/{message_id}/raw"

        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()

            return {"message_id": message_id, "raw": response.text}

        except requests.exceptions.RequestException as e:
            raise LKMLAPIError(f"Failed to fetch raw message: {e}") from e

    def get_user_series(self, email: str, max_results: int = 50) -> Dict[str, Any]:
        """Find recent patch series by user email.

        Args:
            email: User email address (e.g., 'lzampier@redhat.com')
            max_results: Maximum number of messages to retrieve (default: 50)

        Returns:
            Dictionary containing list of series with their root message IDs
        """
        url = f"{self.BASE_URL}/all/?q=f:{email}&x=A"

        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()

            root = ET.fromstring(response.content)
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "thr": "http://purl.org/syndication/thread/1.0",
            }

            all_entries = []
            for entry in root.findall("atom:entry", ns)[:max_results]:
                title_elem = entry.find("atom:title", ns)
                link_elem = entry.find("atom:link", ns)
                updated_elem = entry.find("atom:updated", ns)

                href = link_elem.get("href") if link_elem is not None else ""
                msg_id = ""
                if href:
                    match = re.search(r"/([^/]+)/?$", href.rstrip("/"))
                    if match:
                        msg_id = match.group(1)

                title = title_elem.text if title_elem is not None else ""
                updated = updated_elem.text if updated_elem is not None else ""

                all_entries.append(
                    {
                        "message_id": msg_id,
                        "title": title,
                        "updated": updated,
                        "url": href,
                    }
                )

            filtered_entries = []
            for entry in all_entries:
                title = entry["title"]
                if re.match(r"^Re:\s*", title, flags=re.IGNORECASE):
                    continue

                msg_id = entry["message_id"]
                prefix_match = re.match(r"^(\d+\.\d+)-\d+-", msg_id)
                if prefix_match:
                    series_key = prefix_match.group(1)
                else:
                    series_key = title
                    series_key = re.sub(r"(\[(?:RFC\s+)?PATCH)\s+v\d+", r"\1", series_key)
                    series_key = re.sub(
                        r"\[(?:RFC\s+)?PATCH[^\]]*\s+\d+/\d+\]",
                        "[PATCH X/N]",
                        series_key,
                    )

                entry["series_key"] = series_key
                filtered_entries.append(entry)

            series_list = []
            seen_series = set()
            series_with_cover = set()

            for entry in filtered_entries:
                title = entry["title"]
                msg_id = entry["message_id"]
                series_key = entry["series_key"]

                if series_key in seen_series:
                    continue

                cover_pattern = r"\[(?:RFC\s+)?PATCH[^\]]*\s+0/(\d+)\]"
                cover_match = re.search(cover_pattern, title)

                if cover_match:
                    total_patches = int(cover_match.group(1))
                    series_list.append(
                        {
                            "message_id": msg_id,
                            "title": title,
                            "updated": entry["updated"],
                            "url": entry["url"],
                            "type": "cover_letter",
                            "total_patches": total_patches,
                        }
                    )
                    seen_series.add(series_key)
                    series_with_cover.add(series_key)

            for entry in filtered_entries:
                title = entry["title"]
                msg_id = entry["message_id"]
                series_key = entry["series_key"]

                if series_key in seen_series:
                    continue

                first_patch_pattern = r"\[(?:RFC\s+)?PATCH[^\]]*\s+1/(\d+)\]"
                first_patch_match = re.search(first_patch_pattern, title)

                if first_patch_match and series_key not in series_with_cover:
                    total_patches = int(first_patch_match.group(1))
                    series_list.append(
                        {
                            "message_id": msg_id,
                            "title": title,
                            "updated": entry["updated"],
                            "url": entry["url"],
                            "type": "first_patch",
                            "total_patches": total_patches,
                        }
                    )
                    seen_series.add(series_key)
                    continue

                patch_pattern = r"\[(?:RFC\s+)?PATCH[^\]]*\s+(\d+)/(\d+)\]"
                if re.search(patch_pattern, title):
                    seen_series.add(series_key)
                    continue

                single_patch_pattern = r"\[(?:RFC\s+)?PATCH[^\]]*\](?!\s+\d+/\d+)"
                if re.search(single_patch_pattern, title):
                    series_list.append(
                        {
                            "message_id": msg_id,
                            "title": title,
                            "updated": entry["updated"],
                            "url": entry["url"],
                            "type": "single_patch",
                            "total_patches": 1,
                        }
                    )
                    seen_series.add(series_key)

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
        subsystem: str | None = None,
        author: str | None = None,
        since_date: str | None = None,
        max_results: int = 20,
    ) -> Dict[str, Any]:
        """Search for patches by keywords and filters.

        Args:
            query: Search query string
            subsystem: Optional subsystem filter (e.g., 'net', 'kvm')
            author: Optional author email or name filter
            since_date: Optional date filter in YYYYMMDD format
            max_results: Maximum number of results (default: 20)

        Returns:
            Dictionary containing list of matching patches
        """
        search_terms = [query]

        if subsystem:
            search_terms.append(f"s:{subsystem}")
        if author:
            search_terms.append(f"f:{author}")
        if since_date:
            search_terms.append(f"dt:{since_date}..")

        search_query = " ".join(search_terms)
        url = f"{self.BASE_URL}/all/?q={search_query}&x=A"

        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()

            root = ET.fromstring(response.content)
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "thr": "http://purl.org/syndication/thread/1.0",
            }

            results = []
            for entry in root.findall("atom:entry", ns)[:max_results]:
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

                title = title_elem.text if title_elem is not None else ""
                updated = updated_elem.text if updated_elem is not None else ""
                author_name = author_elem.text if author_elem is not None else ""

                is_patch = "[PATCH" in title
                patch_info = {}

                if is_patch:
                    version_match = re.search(r"\[PATCH[^\]]*v(\d+)", title)
                    series_match = re.search(r"\[PATCH[^\]]*\s+(\d+)/(\d+)\]", title)

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
                        "message_id": msg_id,
                        "title": title,
                        "author": author_name,
                        "updated": updated,
                        "url": href,
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
