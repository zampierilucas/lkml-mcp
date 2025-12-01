"""Tests for multi-inbox support."""

import pytest

from lkml_mcp.client import LKMLAPIError, LKMLClient


def test_lore_kernel_org_detection():
    """Test that lore.kernel.org is detected as supporting universal redirect."""
    client = LKMLClient(base_url="https://lore.kernel.org")
    assert client._supports_universal_redirect is True


def test_sourceware_detection():
    """Test that inbox.sourceware.org is detected as not supporting universal redirect."""
    client = LKMLClient(base_url="https://inbox.sourceware.org")
    assert client._supports_universal_redirect is False


def test_url_builder_lore_without_inbox():
    """Test URL building for lore.kernel.org without inbox parameter."""
    client = LKMLClient(base_url="https://lore.kernel.org")
    url = client._build_url("test-message-id@example.com", None, "t.mbox.gz")
    assert url == "https://lore.kernel.org/r/test-message-id@example.com/t.mbox.gz"


def test_url_builder_lore_with_inbox():
    """Test URL building for lore.kernel.org with inbox parameter (should be ignored)."""
    client = LKMLClient(base_url="https://lore.kernel.org")
    url = client._build_url("test-message-id@example.com", "lkml", "t.mbox.gz")
    # Should still use /r/ even if inbox is provided
    assert url == "https://lore.kernel.org/r/test-message-id@example.com/t.mbox.gz"


def test_url_builder_sourceware_with_inbox():
    """Test URL building for sourceware with inbox parameter."""
    client = LKMLClient(base_url="https://inbox.sourceware.org")
    url = client._build_url("test-message-id@example.com", "gcc-patches", "t.mbox.gz")
    assert url == "https://inbox.sourceware.org/gcc-patches/test-message-id@example.com/t.mbox.gz"


def test_url_builder_sourceware_without_inbox_raises():
    """Test that sourceware raises error when inbox is not provided."""
    client = LKMLClient(base_url="https://inbox.sourceware.org")
    with pytest.raises(ValueError, match="inbox parameter is required"):
        client._build_url("test-message-id@example.com", None, "t.mbox.gz")


def test_get_thread_sourceware_without_inbox_raises():
    """Test that get_thread raises error for sourceware without inbox."""
    client = LKMLClient(base_url="https://inbox.sourceware.org")
    with pytest.raises(ValueError, match="inbox parameter is required"):
        client.get_thread("test-message-id@example.com")


def test_get_raw_sourceware_without_inbox_raises():
    """Test that get_raw raises error for sourceware without inbox."""
    client = LKMLClient(base_url="https://inbox.sourceware.org")
    with pytest.raises(ValueError, match="inbox parameter is required"):
        client.get_raw("test-message-id@example.com")


def test_get_user_series_sourceware_without_inbox_raises():
    """Test that get_user_series raises error for sourceware without inbox."""
    client = LKMLClient(base_url="https://inbox.sourceware.org")
    with pytest.raises(ValueError, match="inbox parameter is required"):
        client.get_user_series("test@example.com")


def test_search_patches_sourceware_without_inbox_raises():
    """Test that search_patches raises error for sourceware without inbox."""
    client = LKMLClient(base_url="https://inbox.sourceware.org")
    with pytest.raises(ValueError, match="inbox parameter is required"):
        client.search_patches("test query")


def test_unknown_instance_detection():
    """Test that unknown instances default to requiring inbox parameter."""
    client = LKMLClient(base_url="https://unknown-instance.example.com")
    # Should default to False (require inbox) for safety
    assert client._supports_universal_redirect is False


def test_url_builder_different_suffixes():
    """Test URL building with different suffixes."""
    client = LKMLClient(base_url="https://lore.kernel.org")

    url_mbox = client._build_url("msg@example.com", None, "t.mbox.gz")
    assert url_mbox.endswith("/t.mbox.gz")

    url_raw = client._build_url("msg@example.com", None, "raw")
    assert url_raw.endswith("/raw")

    url_atom = client._build_url("msg@example.com", None, "t.atom")
    assert url_atom.endswith("/t.atom")
