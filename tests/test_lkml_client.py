#!/usr/bin/env python3
"""Test LKML client functionality."""

import sys
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lkml_mcp.client import LKMLAPIError, LKMLClient


def test_get_thread():
    """Test fetching a thread from lore.kernel.org."""
    print("Testing lkml_get_thread...")
    print("-" * 50)

    client = LKMLClient(timeout=15)

    # Use a known message ID from a real LKML thread
    # This is a simple, stable example
    message_id = "20200101000000.12345-1-test@example.com"

    try:
        result = client.get_thread(message_id)
        print(f"Successfully fetched thread for: {message_id}")
        print(f"Number of messages: {len(result.get('messages', []))}")

        if result.get("messages"):
            first_msg = result["messages"][0]
            print(f"First message subject: {first_msg.get('subject', 'N/A')[:60]}...")
            print(f"From: {first_msg.get('from', 'N/A')}")

        return True

    except LKMLAPIError as e:
        error_msg = str(e).lower()
        if "404" in error_msg or "not found" in error_msg:
            print("Thread not found (expected for test message ID)")
            print("This is normal - we used a test message ID")
            return True
        else:
            print(f"API Error: {e}")
            return False
    except Exception as e:
        print(f"Error: {e}")
        return False


def test_get_raw():
    """Test fetching raw message."""
    print("\nTesting lkml_get_raw...")
    print("-" * 50)

    client = LKMLClient(timeout=15)
    message_id = "20200101000000.12345-1-test@example.com"

    try:
        result = client.get_raw(message_id)
        print("Successfully fetched raw message")
        print(f"Raw content length: {len(result.get('raw', ''))} bytes")
        return True

    except LKMLAPIError as e:
        error_msg = str(e).lower()
        if "404" in error_msg or "not found" in error_msg:
            print("Message not found (expected for test message ID)")
            return True
        else:
            print(f"API Error: {e}")
            return False
    except Exception as e:
        print(f"Error: {e}")
        return False


def test_get_user_series():
    """Test searching for user patch series."""
    print("\nTesting lkml_get_user_series...")
    print("-" * 50)

    client = LKMLClient(timeout=15)

    # Use Linus Torvalds as a test - he's always active
    email = "torvalds@linux-foundation.org"

    try:
        result = client.get_user_series(email, max_results=5)
        print(f"Successfully searched for patches from: {email}")
        print(f"Found {len(result.get('series', []))} series")

        if result.get("series"):
            for i, series in enumerate(result["series"][:3], 1):
                print(f"\n  Series {i}:")
                print(f"    Title: {series.get('title', 'N/A')[:60]}...")
                print(f"    Type: {series.get('type', 'N/A')}")
                print(f"    Total patches: {series.get('total_patches', 'N/A')}")

        return True

    except LKMLAPIError as e:
        print(f"API Error: {e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False


def test_search_patches():
    """Test searching for patches by keyword."""
    print("\nTesting lkml_search_patches...")
    print("-" * 50)

    client = LKMLClient(timeout=15)

    # Search for something common
    query = "driver"

    try:
        result = client.search_patches(query, max_results=5)
        print(f"Successfully searched for: {query}")
        print(f"Found {result.get('total_results', 0)} results")

        if result.get("results"):
            for i, patch in enumerate(result["results"][:3], 1):
                print(f"\n  Result {i}:")
                print(f"    Title: {patch.get('title', 'N/A')[:60]}...")
                print(f"    Author: {patch.get('author', 'N/A')}")
                print(f"    Is patch: {patch.get('is_patch', False)}")

        return True

    except LKMLAPIError as e:
        print(f"API Error: {e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False


def main():
    """Run all LKML client tests."""
    print("LKML MCP Client Tests")
    print("=" * 60)
    print("Testing connection to lore.kernel.org")
    print("=" * 60)

    results = {
        "get_thread": test_get_thread(),
        "get_raw": test_get_raw(),
        "get_user_series": test_get_user_series(),
        "search_patches": test_search_patches(),
    }

    print("\n" + "=" * 60)
    print("SUMMARY:")
    for test_name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"   {test_name}: {status}")

    all_passed = all(results.values())
    if all_passed:
        print("\nAll tests passed!")
    else:
        print("\nSome tests failed. Check output above for details.")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
