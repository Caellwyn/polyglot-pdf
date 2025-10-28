#!/usr/bin/env python3
"""
Test Gemini API using REST API (simpler, fewer dependencies).
"""

import os
import json
import requests

def test_gemini_rest_api():
    """Test Gemini API using direct REST calls."""
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("❌ GEMINI_API_KEY not found in environment")
        return False

    print("✓ API key found")

    # Gemini REST API endpoint
    model = 'gemini-2.0-flash-lite'
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}'

    # Simple test prompt
    payload = {
        "contents": [{
            "parts": [{
                "text": "Say 'Hello from Gemini!' if you can read this."
            }]
        }]
    }

    try:
        print("Making API request...")
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()

        result = response.json()
        text = result['candidates'][0]['content']['parts'][0]['text']

        print(f"✓ API call successful")
        print(f"Response: {text}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ API call failed: {e}")
        if hasattr(e.response, 'text'):
            print(f"Response: {e.response.text}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    print("Testing Gemini API via REST...")
    print("=" * 60)
    success = test_gemini_rest_api()
    print("=" * 60)
    if success:
        print("✓ All tests passed! Gemini REST API is ready.")
    else:
        print("✗ Tests failed. Check API key and connection.")
