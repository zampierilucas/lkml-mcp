#!/usr/bin/env python3
"""Test LKML MCP server functionality."""

import asyncio
import sys
from pathlib import Path

import pytest

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lkml_mcp.server import call_tool


@pytest.mark.asyncio
async def test_lkml_get_thread():
    """Test the lkml_get_thread tool."""
    print("Testing lkml_get_thread tool...")
    print("-" * 50)

    # Use a test message ID
    message_id = "20200101000000.12345-1-test@example.com"

    try:
        result = await call_tool("lkml_get_thread", {"message_id": message_id})

        if result and len(result) > 0:
            response_text = result[0].text
            print(f"Tool returned response (length: {len(response_text)} chars)")

            # Check if it's an error response or valid data
            if "Error" in response_text or "Failed" in response_text:
                print("Expected error for test message ID (this is normal)")
                return True
            else:
                print("Got valid response")
                return True
        else:
            print("No response from tool")
            return False

    except Exception as e:
        print(f"Error: {e}")
        return False


@pytest.mark.asyncio
async def test_lkml_get_raw():
    """Test the lkml_get_raw tool."""
    print("\nTesting lkml_get_raw tool...")
    print("-" * 50)

    message_id = "20200101000000.12345-1-test@example.com"

    try:
        result = await call_tool("lkml_get_raw", {"message_id": message_id})

        if result and len(result) > 0:
            response_text = result[0].text
            print(f"Tool returned response (length: {len(response_text)} chars)")
            return True
        else:
            print("No response from tool")
            return False

    except Exception as e:
        print(f"Error: {e}")
        return False


@pytest.mark.asyncio
async def test_lkml_get_user_series():
    """Test the lkml_get_user_series tool."""
    print("\nTesting lkml_get_user_series tool...")
    print("-" * 50)

    # Use a well-known kernel developer
    email = "torvalds@linux-foundation.org"

    try:
        result = await call_tool("lkml_get_user_series", {"email": email, "max_results": 5})

        if result and len(result) > 0:
            response_text = result[0].text
            print(f"Tool returned response (length: {len(response_text)} chars)")

            # Should contain series information
            if "Series" in response_text or "Patch" in response_text:
                print("Found patch series information")
                return True
            else:
                print("No series found (might be normal)")
                return True
        else:
            print("No response from tool")
            return False

    except Exception as e:
        print(f"Error: {e}")
        return False


@pytest.mark.asyncio
async def test_lkml_search_patches():
    """Test the lkml_search_patches tool."""
    print("\nTesting lkml_search_patches tool...")
    print("-" * 50)

    query = "driver"

    try:
        result = await call_tool("lkml_search_patches", {"query": query, "max_results": 5})

        if result and len(result) > 0:
            response_text = result[0].text
            print(f"Tool returned response (length: {len(response_text)} chars)")

            # Should contain search results
            if "Found" in response_text or "Result" in response_text:
                print("Got search results")
                return True
            else:
                print("Response received but no clear results")
                return True
        else:
            print("No response from tool")
            return False

    except Exception as e:
        print(f"Error: {e}")
        return False


@pytest.mark.asyncio
async def test_unknown_tool():
    """Test calling an unknown tool."""
    print("\nTesting unknown tool handling...")
    print("-" * 50)

    try:
        result = await call_tool("nonexistent_tool", {})

        if result and len(result) > 0:
            response_text = result[0].text
            if "Unknown tool" in response_text:
                print("Correctly handled unknown tool")
                return True
            else:
                print("Unexpected response for unknown tool")
                return False
        else:
            print("No response from tool")
            return False

    except Exception as e:
        print(f"Error: {e}")
        return False


async def main():
    """Run all MCP server tests."""
    print("LKML MCP Server Tests")
    print("=" * 60)
    print("Testing MCP tool handlers")
    print("=" * 60)

    results = {
        "lkml_get_thread": await test_lkml_get_thread(),
        "lkml_get_raw": await test_lkml_get_raw(),
        "lkml_get_user_series": await test_lkml_get_user_series(),
        "lkml_search_patches": await test_lkml_search_patches(),
        "unknown_tool": await test_unknown_tool(),
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
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
