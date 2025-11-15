# Half-Cascade TTS Implementation

## Overview

This directory contains the Text-to-Speech (TTS) implementation for the half-cascade architecture migration (Phases 1D and 2C).

## Components

### 1. Flash TTS Service (`flash_tts_service.py`)

The core TTS service using Gemini 2.5 Flash-TTS model.

**Features:**
- 20+ language support with locale-specific configurations
- Audio streaming in 50ms chunks
- Sub-200ms language switching
- Voice consistency per language
- Graceful degradation for unsupported languages

**Usage:**

```python
from backend.services.flash_tts_service import FlashTTSService

# Initialize service
tts = FlashTTSService(use_vertex=True)

# Single text synthesis
async for audio_chunk in tts.synthesize_speech("Hello world", "en-US"):
    # Stream audio chunk to client
    await websocket.send(audio_chunk)

# Multi-segment synthesis with language switching
segments = [
    {"text": "Hello", "language": "en-US"},
    {"text": "Hola", "language": "es-ES"},
    {"text": "你好", "language": "zh-CN"}
]

async for audio_chunk in tts.synthesize_segments(segments):
    await websocket.send(audio_chunk)
```

### 2. TTS Segment Queue (`tts_segment_queue.py`)

Advanced queue manager for seamless multi-language audio streaming.

**Features:**
- Pre-buffering to avoid audio gaps
- Language pre-loading for smooth transitions
- Memory-efficient sliding window buffer
- Concurrent segment synthesis
- Language switch tracking

**Usage:**

```python
from backend.services.tts_segment_queue import SegmentQueue, StreamingTTSQueue

# Option 1: Full queue with buffering (production)
queue = SegmentQueue(tts_service, buffer_chunks=3)

# Add segments to queue
queue.add_segments([
    {"text": "Hello", "language": "en-US"},
    {"text": "Hola", "language": "es-ES"}
])

# Stream audio with buffering
async for audio_chunk in queue.stream_audio():
    await websocket.send(audio_chunk)

# Get statistics
stats = queue.get_stats()
print(f"Language switches: {stats['language_switches']}")
print(f"Buffer underruns: {stats['buffer_underruns']}")

# Option 2: Streaming queue (low latency)
streaming_queue = StreamingTTSQueue(tts_service)

async for audio_chunk in streaming_queue.stream_segments(segments):
    await websocket.send(audio_chunk)
```

## Supported Languages

The service supports 20+ languages with optimized voice configurations:

- **English**: en-US, en-GB
- **Spanish**: es-ES, es-MX
- **Chinese**: zh-CN (Mandarin Simplified), zh-TW (Traditional)
- **Korean**: ko-KR
- **Arabic**: ar-SA (RTL)
- **European**: fr-FR, de-DE, it-IT, pt-BR, pt-PT, ru-RU, pl-PL, nl-NL, sv-SE, uk-UA, tr-TR
- **Asian**: ja-JP, hi-IN, vi-VN, tl-PH (Tagalog), bn-BD (Bengali), ur-PK (Urdu), fa-IR (Farsi/RTL)
- **African**: af-ZA (Afrikaans)
- **Indigenous American**: qu-PE (Quechua)

## Language Configuration

Each language has a `VoiceConfig` with the following settings:

```python
@dataclass
class VoiceConfig:
    rate: float = 1.0        # Speech rate (0.5 - 2.0)
    pitch: float = 0.0       # Voice pitch (-20.0 to 20.0)
    voice: str = "default"   # Voice name/ID
    rtl: bool = False        # Right-to-left flag
```

Example configurations:
- Chinese (zh-CN, zh-TW): rate=0.95 (slightly slower for clarity)
- Arabic (ar-SA): rtl=True
- Farsi (fa-IR): rtl=True

## Fallback Behavior

1. **Exact match**: If language code exists (e.g., "es-ES"), use it directly
2. **Base language fallback**: If variant not found (e.g., "es-AR"), find first matching base language ("es-ES" or "es-MX")
3. **Default fallback**: If language unsupported, fallback to English (en-US)

All fallbacks are logged for monitoring and debugging.

## Performance Characteristics

- **Language switching**: <200ms (with pre-loading)
- **Audio chunk size**: ~50ms per chunk
- **Buffer size**: 3 chunks (~150ms) default
- **Concurrent synthesis**: 2 segments max (configurable)
- **Memory usage**: O(buffer_size) with sliding window

## Integration with Half-Cascade Pipeline

```python
# Phase 1D & 2C Integration Example

from backend.services.flash_tts_service import FlashTTSService
from backend.services.tts_segment_queue import SegmentQueue

# Initialize TTS service
tts_service = FlashTTSService(use_vertex=True)

# Create segment queue
segment_queue = SegmentQueue(tts_service)

# ASR output from Gemini 2.5 Flash-Lite (structured JSON)
asr_response = {
    "user_transcript": "Hello, my name is Maria",
    "detected_language": "en-US",
    "segments": [
        {"text": "Hello, my name is Maria", "language": "en-US"},
        {"text": "¿Cuál es tu nombre?", "language": "es-ES"}
    ],
    "tool_calls": [...]
}

# Add segments to TTS queue
segment_queue.add_segments(asr_response["segments"])

# Stream audio to client
async for audio_chunk in segment_queue.stream_audio():
    await websocket.send_bytes(audio_chunk)

# Check statistics
stats = segment_queue.get_stats()
logger.info("TTS completed", **stats)
```

## Testing

### Unit Tests

```bash
# Run TTS service tests
pytest backend/tests/unit/test_flash_tts_service.py -v

# Run segment queue tests
pytest backend/tests/unit/test_tts_segment_queue.py -v
```

### Test Coverage

- ✅ Language configuration validation
- ✅ Language resolution and fallback
- ✅ Speech synthesis streaming
- ✅ Multi-segment synthesis
- ✅ Language switching tracking
- ✅ Queue management
- ✅ Buffer management
- ✅ Pre-loading optimization
- ✅ Error handling

## Dependencies

- `google-genai`: Gemini API client
- `structlog`: Structured logging
- `dataclasses`: Configuration objects (Python stdlib)
- `asyncio`: Async streaming (Python stdlib)

## Configuration

Set in `backend/config.py`:

```python
# Flash TTS model
MODEL_FLASH_TTS = "gemini-2.5-flash-preview-tts"

# Use Vertex AI (recommended for production)
VERTEXAI = True

# Or use API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
```

## Monitoring

The TTS services emit structured logs for monitoring:

- `flash_tts_initialized`: Service startup
- `language_switch`: Language change detected
- `synthesis_complete`: Segment synthesis finished
- `synthesis_error`: Error during synthesis
- `language_fallback_to_variant`: Language variant fallback
- `language_not_supported_fallback_to_english`: Unsupported language fallback

Queue-specific logs:
- `segment_added_to_queue`: Segment queued
- `buffer_underrun`: Buffer exhausted (performance issue)
- `stream_complete`: Streaming finished with stats

## Next Steps (Phase 3+)

1. **Phase 2A**: Integrate with Flash-Lite ASR for structured output
2. **Phase 2D**: Update WebSocket protocol for new message types
3. **Phase 3A**: Build complete streaming pipeline (ASR → Processing → TTS)
4. **Phase 3B**: Tool integration with form updates
5. **Phase 4A**: Frontend connection manager updates

## Authors

- Phase 1D & 2C implementation: November 15, 2025
- Half-Cascade Architecture: Migration Plan v4.0

## References

- [Half-Cascade Implementation Plan](../../planning_documents/HALF_CASCADE_IMPLEMENTATION.md)
- [Gemini Live API Documentation](../../planning_documents/code_examples/0_gemini_live_documentation.md)
- [Supported Languages](../../planning_documents/code_examples/supported_languages.py)
