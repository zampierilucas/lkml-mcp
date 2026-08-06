"""Test single-patch selection in get_patch."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lkml_mcp.client import LKMLClient


def _message(msg_id, subject, marker, sender="Dev <dev@example.com>"):
    return f"""From {msg_id} Mon Sep 17 00:00:00 2001
From: {sender}
Subject: {subject}
Message-ID: <{msg_id}>
Date: Mon, 1 Jan 2026 00:00:00 +0000

commit message
---
 a.c | 1 +
 1 file changed, 1 insertion(+)

diff --git a/a.c b/a.c
index 111..222 100644
--- a/a.c
+++ b/a.c
@@ -1 +1,2 @@
 int main(void) {{ return 0; }}
+// {marker}
"""


COVER = _message("cover@example.com", "[PATCH 0/2] a series", "COVER")
PATCH_1 = _message("p1@example.com", "[PATCH 1/2] first", "FIRST")
PATCH_2 = _message("p2@example.com", "[PATCH 2/2] second", "SECOND")
REPLY = _message("r1@example.com", "Re: [PATCH 2/2] second", "REPLY")
BOT = _message("bot@example.com", "[PATCH 1/2] first", "BOT", sender="kernel test robot <lkp@intel.com>")


@pytest.fixture
def client(monkeypatch):
    c = LKMLClient(base_url="https://lore.kernel.org")
    return c


def _thread(client, messages):
    client._fetch_mbox = lambda message_id, inbox: list(messages)


@pytest.mark.parametrize(
    "requested,expected_id,marker",
    [
        ("p2@example.com", "p2@example.com", "SECOND"),
        ("p1@example.com", "p1@example.com", "FIRST"),
        ("cover@example.com", "cover@example.com", "COVER"),
    ],
)
def test_returns_the_requested_message(client, requested, expected_id, marker):
    _thread(client, [COVER, PATCH_1, PATCH_2])
    patch = client.get_patch(requested, series=False)["patches"][0]

    assert patch["message_id"] == expected_id
    assert marker in Path(patch["path"]).read_text()


def test_falls_back_to_first_patch_when_request_is_absent(client):
    _thread(client, [COVER, PATCH_1, PATCH_2])
    patch = client.get_patch("nowhere@example.com", series=False)["patches"][0]

    assert patch["message_id"] == "cover@example.com"


def test_fallback_skips_replies_and_bots(client):
    _thread(client, [REPLY, BOT, PATCH_1])
    patch = client.get_patch("nowhere@example.com", series=False)["patches"][0]

    assert patch["message_id"] == "p1@example.com"


def test_requested_message_wins_over_reply_filter(client):
    """An explicit request is honoured even when the message looks like a reply."""
    _thread(client, [COVER, REPLY])
    patch = client.get_patch("r1@example.com", series=False)["patches"][0]

    assert patch["message_id"] == "r1@example.com"


def test_empty_thread_returns_no_patches(client):
    _thread(client, [])
    assert client.get_patch("p1@example.com", series=False)["patches"] == []
