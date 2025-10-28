#!/usr/bin/env python3
"""
Test different Gemini model names to find the right one.
"""

import os
import json
import requests

def test_model(model_name):
    """Test a specific Gemini model."""
    api_key = os.environ.get('GEMINI_API_KEY')
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}'

    payload = {
        "contents": [{
            "parts": [{
                "text": "Say 'OK' if you can read this."
            }]
        }]
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 200:
            result = response.json()
            text = result['candidates'][0]['content']['parts'][0]['text']
            print(f"✓ {model_name}: {text.strip()}")
            return True
        else:
            print(f"✗ {model_name}: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ {model_name}: {str(e)[:50]}")
        return False

if __name__ == "__main__":
    print("Testing Gemini model names...")
    print("=" * 60)

    models_to_try = [
        'gemini-2.0-flash-lite',
        'gemini-2.5-flash-lite',
        'gemini-2.0-flash',
        'gemini-1.5-flash',
        'gemini-1.5-pro',
        'gemini-pro',
        'gemini-flash',
    ]

    for model in models_to_try:
        test_model(model)

    print("=" * 60)
