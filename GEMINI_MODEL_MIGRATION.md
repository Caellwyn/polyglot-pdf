# Gemini Live Model Migration Notes

## Date: October 18, 2024

## Issue: Model Version Behavioral Change

### Background
The application was experiencing a critical reliability issue where Gemini would only initiate conversation ~50% of the time after connection. This manifested as:
- Inconsistent initial greetings (sometimes 19-22 seconds delay, sometimes never)
- Gemini responding reliably to voice input but not to text messages
- Worked perfectly with the original model, but broken after migration

### Root Cause Discovery
**The issue was NOT our code** - it was a behavioral difference between Gemini Live model versions:

#### Model Comparison
| Model | Text Message Response | Status |
|-------|----------------------|--------|
| `gemini-live-2.5-flash-preview-native-audio` | ✅ Reliably responds | Deprecated (last day: Oct 18, 2024) |
| `gemini-live-2.5-flash-preview-native-audio-09-2025` | ❌ Doesn't reliably respond to text-only | Current (private preview) |
| `gemini-live-2.5-flash` | ❓ Unknown (requires private GA access) | Requires application |

### The Solution: Activity Signal Wrapping

The **09-2025 model requires activity signals** around text messages to treat them like voice input. Without these signals, the model doesn't reliably respond.

#### Implementation Pattern
```python
# Wrap ALL text messages with activity signals
await session.send_activity_start()  # "User is speaking"

await session.send_client_content(
    turns={"role": "user", "parts": [{"text": message}]},
    turn_complete=True
)

await session.send_activity_end()  # "User finished speaking"
```

#### Where Applied
1. **Initial greeting message** (after session establishment)
2. **Fallback resend** (if no response after timeout)
3. **All queued text messages** (recovery prompts, tool responses, etc.)

### Technical Details

#### Why This Works
- `send_activity_start()` signals to Gemini that user activity has begun (like detecting speech)
- The text message is then treated as if it came from voice input
- `send_activity_end()` signals that user activity has ended (like detecting silence)
- This mimics the natural flow of voice conversation

#### Code Changes
- **File**: `backend/adapters/live_ai_gemini.py`
- **Lines**: ~560-665 (text_sender coroutine, initial message, fallback)
- **Delay**: Reduced from 2.0s to 0.5s (activity signals handle timing)

### Testing Results
- ✅ With activity signals: **Reliable response** with 09-2025 model
- ✅ Works with warmup disabled (simpler architecture)
- ✅ Response time: 2-5 seconds (acceptable)
- ✅ All text messages wrapped consistently

### Migration Timeline
- **October 18, 2024**: Last day for `gemini-live-2.5-flash-preview-native-audio`
- **October 19, 2024+**: Must use `gemini-live-2.5-flash-preview-native-audio-09-2025`
- **Current config**: `backend/config.py` line 9 (MODEL_NATIVE setting)

### Lessons Learned
1. **Model behavior can change between versions** - even with same API
2. **Activity signals are critical** for text messages in live audio sessions
3. **Don't debug forever** - sometimes it's not your code!
4. **Simplify first** - removing warmup helped isolate the real issue
5. **Comprehensive logging** helped prove our pipeline was correct

### Future Considerations
- Monitor for further behavioral changes in future model versions
- Consider applying for access to `gemini-live-2.5-flash` (half-cascade model)
- Document any new quirks or required patterns
- Keep activity signal wrapping even if model behavior improves (defensive programming)

### References
- Activity signals documentation: `send_activity_start()`, `send_activity_end()`
- Model configuration: `backend/config.py` (MODEL_NATIVE setting)
- Implementation: `backend/adapters/live_ai_gemini.py`
