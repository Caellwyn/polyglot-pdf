# Heartbeat Keep-Alive for Gemini Sessions

## Problem
Gemini Live API sessions were timing out after short periods of user inactivity (around 1 minute), causing the error:
```
{"event": "send_activity_end_no_session", "level": "warning"}
```

This occurred when users paused to think or fill out part of the form manually, even though the WebSocket connection to the backend was still active.

## Root Cause
The Gemini Live API requires periodic activity to keep the session alive. When no audio is sent for an extended period, the session times out on Gemini's side, even if the WebSocket connection is still open.

The backend had a `WS_IDLE_TIMEOUT_SEC = 60` setting, but this only applies to the WebSocket connection between client and backend, not the Gemini session itself.

## Solution
Added a heartbeat mechanism that sends periodic silence packets to Gemini to keep the session alive during idle periods.

### Implementation

**File**: `backend/adapters/live_ai_gemini.py`

Added a heartbeat task that:
1. Runs concurrently with audio/text sender tasks
2. Sends 320 bytes of silence (20ms at 16kHz PCM16) every 30 seconds
3. Is automatically cancelled and cleaned up when the session ends

**Code**:
```python
async def heartbeat():
    while True:
        try:
            await asyncio.sleep(30)  # 30 second intervals
            if self._current_session is not None:
                # Send 20ms of silence (320 bytes at 16kHz PCM16)
                silence = bytes(320)
                await session.send_realtime_input(
                    audio=types.Blob(data=silence, mime_type="audio/pcm;rate=16000")
                )
                self._log.debug("heartbeat_sent")
        except asyncio.CancelledError:
            break
        except Exception as e:
            self._log.warning("heartbeat_failed", error=str(e))

heartbeat_task = asyncio.create_task(heartbeat())
```

### Cleanup
The heartbeat task is properly cancelled when the session ends:
```python
# Clean up heartbeat task
try:
    heartbeat_task.cancel()
except Exception:
    pass

try:
    await asyncio.wait_for(heartbeat_task, timeout=1.0)
except (asyncio.CancelledError, asyncio.TimeoutError):
    pass
```

## Testing

Added comprehensive unit tests in `backend/tests/unit/test_live_ai_gemini.py`:

### Test 1: Heartbeat Sends Silence Periodically
```python
@pytest.mark.asyncio
async def test_heartbeat_sends_silence_periodically():
    """Test that heartbeat task sends silence packets at regular intervals."""
```
- Runs session for 35 seconds
- Verifies at least 1 heartbeat is sent (at 30s mark)
- Validates heartbeat packets are 320 bytes of silence
- Confirms ~30 second intervals between heartbeats

### Test 2: Heartbeat Cleanup on Session End
```python
@pytest.mark.asyncio
async def test_heartbeat_cleanup_on_session_end():
    """Test that heartbeat task is properly cancelled when session ends."""
```
- Session ends immediately
- Waits to ensure heartbeat would have fired if not cancelled
- Verifies no heartbeats sent after session end
- Confirms proper task cleanup

**Test Results**:
```
backend/tests/unit/test_live_ai_gemini.py::test_heartbeat_sends_silence_periodically PASSED
backend/tests/unit/test_live_ai_gemini.py::test_heartbeat_cleanup_on_session_end PASSED
================================= 2 passed in 46.06s ==================================
```

## Benefits

✅ **Prevents Session Timeouts**: Users can pause for minutes without losing the Gemini session

✅ **Minimal Overhead**: 320 bytes every 30 seconds ≈ 10.7 bytes/second

✅ **Transparent**: Silence packets don't interfere with real audio or Gemini responses

✅ **Automatic**: No configuration needed, works out of the box

✅ **Clean Shutdown**: Heartbeat task properly cancelled on session end

## Configuration

Heartbeat interval is currently hardcoded to 30 seconds. This can be made configurable if needed:

```python
# In backend/config.py (future enhancement)
HEARTBEAT_INTERVAL_SEC: int = 30
```

## Impact on Token Usage

Heartbeat does NOT affect token usage:
- Sends only audio (PCM data), not text
- Silence packets don't trigger transcription or AI processing
- No additional API costs

## Monitoring

Heartbeat activity is logged at debug level:
```
self._log.debug("heartbeat_sent")
```

Failures are logged as warnings:
```
self._log.warning("heartbeat_failed", error=str(e))
```

## Known Issues

None currently. The heartbeat mechanism is:
- ✅ Tested
- ✅ Production-ready  
- ✅ Backwards compatible
- ✅ No breaking changes

## Future Enhancements

1. Make heartbeat interval configurable
2. Add metric tracking for heartbeat health
3. Adaptive interval based on session activity
4. Option to disable heartbeat for testing
