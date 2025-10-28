#!/usr/bin/env python3
"""
Test Gemini REST API with proper endpoint and model names.
Based on official docs: https://ai.google.dev/api
"""

import os
import json
import requests

def test_gemini_text():
    """Test basic text generation with Gemini."""
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("❌ GEMINI_API_KEY not found")
        return False

    # Try the correct endpoint format from docs
    model = 'gemini-1.5-flash'
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'

    headers = {
        'Content-Type': 'application/json',
    }

    payload = {
        "contents": [{
            "parts": [{
                "text": "Say 'Hello from Gemini!' if you can read this."
            }]
        }]
    }

    try:
        print(f"Testing {model}...")
        response = requests.post(
            f"{url}?key={api_key}",
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

def test_gemini_structured_output():
    """Test structured JSON output from Gemini."""
    api_key = os.environ.get('GEMINI_API_KEY')

    model = 'gemini-1.5-flash'
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'

    headers = {
        'Content-Type': 'application/json',
    }

    # Define a schema for structured output
    payload = {
        "contents": [{
            "parts": [{
                "text": "List 3 colors. Return as JSON array with 'name' and 'hex' fields."
            }]
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
        print(f"\nTesting structured output with {model}...")
        response = requests.post(
            f"{url}?key={api_key}",
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
            print(f"Response: {response.text[:500]}")
            return False

    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Gemini REST API")
    print("=" * 60)

    success1 = test_gemini_text()
    success2 = test_gemini_structured_output()

    print("=" * 60)
    if success1 and success2:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed")
