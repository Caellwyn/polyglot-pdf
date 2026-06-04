"""Test Gemini Live API connection to diagnose authentication/connectivity issues."""

import asyncio
import os
from google import genai

async def test_connection():
    print("=" * 60)
    print("Testing Gemini Live API Connection")
    print("=" * 60)
    
    # Check environment
    print("\n1. Environment Check:")
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    api_key = os.getenv("GEMINI_API_KEY")
    print(f"   GOOGLE_CLOUD_PROJECT: {project or '(not set)'}")
    print(f"   GEMINI_API_KEY: {'***' + api_key[-4:] if api_key else '(not set)'}")
    
    # Test Vertex AI connection
    print("\n2. Testing Vertex AI Connection:")
    try:
        client = genai.Client(
            vertexai=True,
            project=project,
            location="us-central1"
        )
        print("   ✓ Client created successfully")
        
        # Try to connect to Gemini Live
        print("\n3. Connecting to Gemini Live API...")
        # Read the model from env (GEMINI_LIVE_MODEL) like the contract test does,
        # falling back to the current 2.5 native-audio default. The old
        # gemini-live-2.5-flash-preview-native-audio-09-2025 alias is retired and
        # 1008s (not found) on bidiGenerateContent -- see backend/config.py.
        model = os.getenv("GEMINI_LIVE_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025")
        config = {
            "response_modalities": ["TEXT"],
        }
        
        print(f"   Model: {model}")
        print("   Attempting connection...")
        
        async with client.aio.live.connect(model=model, config=config) as session:
            print("   ✓ Connection established!")
            
            # Try sending a simple message
            print("\n4. Testing message send:")
            await session.send_client_content(
                turns={"role": "user", "parts": [{"text": "Hello, can you hear me?"}]},
                turn_complete=True
            )
            print("   ✓ Message sent")
            
            # Try receiving response
            print("\n5. Waiting for response...")
            response_received = False
            async for response in session.receive():
                if response.text is not None:
                    print(f"   ✓ Response received: {response.text[:100]}")
                    response_received = True
                    break
            
            if not response_received:
                print("   ✗ No response received")
        
        print("\n" + "=" * 60)
        print("SUCCESS: All tests passed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n   ✗ ERROR: {e}")
        print(f"\n   Error type: {type(e).__name__}")
        import traceback
        print("\n   Full traceback:")
        traceback.print_exc()
        print("\n" + "=" * 60)
        print("FAILED: Connection test failed")
        print("=" * 60)
        print("\nTroubleshooting:")
        print("1. Run: gcloud auth application-default login")
        print("2. Set GOOGLE_CLOUD_PROJECT: export GOOGLE_CLOUD_PROJECT=your-project-id")
        print("3. Enable Vertex AI API in your Google Cloud project")

if __name__ == "__main__":
    asyncio.run(test_connection())
