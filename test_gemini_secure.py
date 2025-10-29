#!/usr/bin/env python3
"""
Test Gemini API - SECURE VERSION
Reads API key ONLY from environment variable, never hardcoded.
"""

import os
import json
import requests

def test_gemini():
    """Test basic Gemini API call."""
    api_key = os.environ.get('GEMINI_API_KEY')

    if not api_key:
        print("❌ GEMINI_API_KEY not set in environment")
        print("   Set it with: export GEMINI_API_KEY='your_key_here'")
        return False

    model = 'gemini-2.5-flash-lite'
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'

    headers = {
        'Content-Type': 'application/json',
        'x-goog-api-key': api_key  # API key in header, not query param
    }

    payload = {
        "contents": [{
            "parts": [{"text": "Say 'Hello from Gemini!' if you can read this."}]
        }]
    }

    try:
        print(f"Testing {model}...")
        response = requests.post(
            url,  # No ?key= query param
            headers=headers,
            json=payload,
            timeout=30
        )

        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            text = result['candidates'][0]['content']['parts'][0]['text']
            print(f"✓ Success! Response: {text}")
            return True
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

def test_structured_output():
    """Test JSON structured output."""
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        return False

    model = 'gemini-2.5-flash-lite'
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'

    headers = {
        'Content-Type': 'application/json',
        'x-goog-api-key': api_key
    }

    payload = {
        "contents": [{
            "parts": [{"text": "List 2 colors with hex codes."}]
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "hex": {"type": "string"}
                    },
                    "required": ["name", "hex"]
                }
            }
        }
    }

    try:
        print(f"\nTesting structured output...")
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30
        )

        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            text = result['candidates'][0]['content']['parts'][0]['text']
            parsed = json.loads(text)
            print(f"✓ Structured output works!")
            print(f"Result: {json.dumps(parsed, indent=2)}")
            return True
        else:
            print(f"❌ Error: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Gemini API (Secure - Environment Variable Only)")
    print("=" * 60)

    success1 = test_gemini()
    success2 = test_structured_output()

    print("=" * 60)
    if success1 and success2:
        print("✓ ALL TESTS PASSED!")
    else:
        print("✗ Some tests failed")
