"""Test patch subject tag detection and parsing."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lkml_mcp.client import _is_patch_subject, _parse_patch_subject

TAGGED = [
    "[PATCH] HID: fix foo",
    "[PATCH v5 2/3] Fix foo",
    "[RFC PATCH 0/1] HID: Add support for multiple batteries per device",
    "[RFC PATCH v2 1/3] mm: rework",
    "[RESEND PATCH] net: fix bar",
    "[PATCH net-next 1/3] net: fix baz",
    "[patch] lowercase tag",
]

UNTAGGED = [
    "[GIT PULL] riscv updates",
    "[ANNOUNCE] release 6.12",
    "[PATCHWORK] not a real tag",
    "Question about the scheduler",
    "PATCH without brackets",
]


@pytest.mark.parametrize("subject", TAGGED)
def test_tagged_subjects(subject):
    assert _is_patch_subject(subject)


@pytest.mark.parametrize("subject", UNTAGGED)
def test_untagged_subjects(subject):
    assert not _is_patch_subject(subject)


@pytest.mark.parametrize(
    "subject,version,number,total",
    [
        ("[PATCH v5 2/3] Fix foo", 5, 2, 3),
        ("[RFC PATCH 0/1] Add batteries", None, 0, 1),
        ("[RFC PATCH v2 1/3] mm: rework", 2, 1, 3),
        ("[RESEND PATCH v4] net: fix bar", 4, None, None),
        ("[PATCH] standalone", None, None, None),
    ],
)
def test_parse_patch_subject(subject, version, number, total):
    info = _parse_patch_subject(subject)
    assert info["is_patch"]
    assert info["version"] == version
    assert info["patch_number"] == number
    assert info["total"] == total
