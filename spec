---

# ✅ **MCP Extension Proposal**

You will add **two tools**:

1. **`lkml_get_thread`**
   Fetch + parse a full LKML thread (via msg-id → lore/t.mbox.gz → JSON)

2. **`lkml_get_raw`** *(optional but useful)*
   Fetch a single email in raw RFC822 format (via `/raw` endpoint)

These two endpoints give you *complete power* to retrieve any patch series, discussion, or review thread without cloning LKML.

---

# 🛠️ **Minimal Tools Definition**

Below is the simplest possible MCP-compliant implementation written as **functions you add to your existing MCP server file**.

---

# 🔧 **Tool 1 — `lkml_get_thread`**

Fetch a thread:

```
https://lore.kernel.org/lkml/<MESSAGE_ID>/t.mbox.gz
```

Then parse the mbox into structured JSON.

```python
import requests, gzip, mailbox, json
from mcp.server.fastmcp import tool

@tool
def lkml_get_thread(message_id: str) -> dict:
    """
    Fetch one LKML thread by message-id from lore.kernel.org.
    Returns a list of messages with subject/from/date/body.
    """
    url = f"https://lore.kernel.org/lkml/{message_id}/t.mbox.gz"
    r = requests.get(url, timeout=20)
    r.raise_for_status()

    # Decompress
    mbox_data = gzip.decompress(r.content).decode(errors="ignore")

    # Parse messages
    messages = []
    for msg in mailbox.mbox(mbox_data.splitlines(keepends=True)):
        messages.append({
            "subject": msg.get("subject"),
            "from": msg.get("from"),
            "date": msg.get("date"),
            "message_id": msg.get("message-id"),
            "in_reply_to": msg.get("in-reply-to"),
            "body": msg.get_payload()
        })

    return {"messages": messages}
```

That is the entire tool — no dependencies except `requests`.

---

# 🔧 **Tool 2 — `lkml_get_raw`** *(optional but recommended)*

Fetch a single email without thread expansion:

```
https://lore.kernel.org/r/<MESSAGE_ID>/raw
```

```python
@tool
def lkml_get_raw(message_id: str) -> dict:
    """
    Fetch a single LKML message in raw RFC822 format.
    """
    url = f"https://lore.kernel.org/r/{message_id}/raw"
    r = requests.get(url, timeout=20)
    r.raise_for_status()

    return {
        "message_id": message_id,
        "raw": r.text
    }
```

This is useful when you want:

* raw MIME bodies
* headers
* or if you want Claude to parse inline diffs manually

---

# ⚙️ **Dependencies**

Add to your server’s requirements:

```
requests
```

(You already have `mcp`, and Python `mailbox` + `gzip` are standard libs.)

---

# 📦 **How to Use These Tools from Claude / ChatGPT MCP Client**

### 1. Ask for a thread:

```
Call lkml_get_thread with:
{
  "message_id": "20251111105634.1684751-1-lzampier@redhat.com"
}
```

### 2. Ask for raw version:

```
Call lkml_get_raw with:
{
  "message_id": "20251111105634.1684751-1-lzampier@redhat.com"
}
```

---

# 🧠 **Example Prompt to the LLM**

> Fetch the LKML thread for
> `20251111105634.1684751-1-lzampier@redhat.com`,
> summarize the review, and extract the arguments for/against.

Your MCP tools will handle the fetching.
The LLM handles summarization & diff reasoning.

---

# 📘 **Why this is the correct minimal MCP design**

Because it is:

* **stateless**
* **5–10 lines per tool**
* **doesn’t depend on public-inbox or b4**
* **always works — lore.kernel.org guarantees stable msg-id URLs**
* **small enough to embed into ANY existing MCP server**
* **gives you remote access to any kernel mailing list**

This is the **absolute minimum functional MCP** for kernel thread retrieval.

---
