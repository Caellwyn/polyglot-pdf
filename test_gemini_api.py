#!/usr/bin/env python3
"""
Test Gemini API connection and basic functionality.
"""

import os
from google import genai
from google.genai import types

def test_gemini_connection():
    """Test basic Gemini API connection."""
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("❌ GEMINI_API_KEY not found in environment")
        return False

    print("✓ API key found")

    # Initialize client
    client = genai.Client(api_key=api_key)
    print("✓ Client initialized")

    # Test with a simple text prompt
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash-lite',
            contents='Say "Hello from Gemini!" if you can read this.'
        )
        print(f"✓ API call successful")
        print(f"Response: {response.text}")
        return True
    except Exception as e:
        print(f"❌ API call failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing Gemini API connection...")
    print("=" * 60)
    success = test_gemini_connection()
    print("=" * 60)
    if success:
        print("✓ All tests passed! Gemini API is ready.")
    else:
        print("✗ Tests failed. Check API key and connection.")
