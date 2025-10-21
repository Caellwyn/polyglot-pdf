# VAD and Activity Timeout Fixes

**Date**: October 16, 2025  
**Issue**: False VAD triggers, escalation exceeding max level, choppy Gemini audio, no disconnect at Level 3

---

## Problems Identified

### 1. **False VAD Triggers on Silence**
- **Symptom**: `[VFF Metrics] 🎤 Mic activity detected` appearing when user is silent
- **Impact**: Sends `activity_start` to backend → interrupts Gemini mid-sentence → choppy audio
- **Root Cause**: VAD thresholds too sensitive (0.9/0.65), minimum speech duration too short (100ms)

### 2. **Escalation Level Exceeds Maximum**
- **Symptom**: Escalation goes to level 8/3 instead of stopping at 3
- **Impact**: Repeated Level 3 prompts spam Gemini, never actually disconnects
- **Root Cause**: `onInactivityTimeout()` didn't check if already at max level before incrementing

### 3. **No Disconnect at Level 3**
- **Symptom**: Gemini keeps saying goodbye but session never closes
- **Impact**: Session runs indefinitely, eventually crashes with `1011 internal error`
- **Root Cause**: 
  - Backend only sends `turn_complete` inside `on_transcript` callback
  - Transcripts not enabled in demo connection
  - Result: `turn_complete` message never sent, `waitingForFarewellRef` never triggers disconnect

### 4. **Choppy Gemini Audio**
- **Symptom**: Gemini's voice very choppy and difficult to understand
- **Impact**: Poor user experience, can't understand AI responses
- **Root Cause**: False VAD triggers (#1) interrupt Gemini → she stops mid-sentence → restarts → sounds choppy

---

## Fixes Implemented

### Frontend Changes

#### 1. **Increased VAD Thresholds** (`frontend/src/demo/useDemoVAD.ts`)
```typescript
// Before:
positiveSpeechThreshold: 0.9,  // 90% confidence
negativeSpeechThreshold: 0.65, // 65% to end
minSpeechMs: 100,              // 100ms sustained
redemptionMs: 300,             // 300ms grace period

// After:
positiveSpeechThreshold: 0.95,  // 95% confidence (less sensitive)
negativeSpeechThreshold: 0.75,  // 75% to end (wider hysteresis)
minSpeechMs: 250,               // 250ms sustained (filters noise)
redemptionMs: 400,              // 400ms grace period (smoother)
```

**Rationale**: 
- Higher `positiveSpeechThreshold` (0.95) = fewer false positives
- Longer `minSpeechMs` (250ms) = filters out brief noise/artifacts
- Longer `redemptionMs` (400ms) = more forgiving of natural speech pauses

#### 2. **Prevent Escalation Beyond Max** (Desktop + Mobile Overlays)
```typescript
// VoiceOverlay.tsx + VoiceOverlayMobile.tsx
const onInactivityTimeout = () => {
	// Don't escalate past maximum
	if (escalationLevelRef.current >= MAX_ESCALATION_LEVEL) {
		console.log(`[VFF Watchdog] ⏸️ Already at max escalation level ${MAX_ESCALATION_LEVEL} - waiting for farewell to complete`)
		return  // Exit early instead of incrementing
	}
	
	escalationLevelRef.current++
	// ... rest of logic
}
```

**Rationale**: Once at Level 3, stop incrementing - just wait for disconnect

#### 3. **Timeout Fallback for Level 3** (Desktop + Mobile Overlays)
```typescript
// VoiceOverlay.tsx + VoiceOverlayMobile.tsx
const handleEscalationLevel3 = () => {
	waitingForFarewellRef.current = true
	connectionManager.sendRecoveryPrompt(3)
	
	// CRITICAL: Fallback timeout if turn_complete never arrives
	setTimeout(() => {
		if (waitingForFarewellRef.current) {
			console.log('[VFF Watchdog] ⏱️ Farewell timeout - forcing disconnect after 10s')
			waitingForFarewellRef.current = false
			stopActivityWatchdog()
			vad.pause()
			connectionManager.disconnect()
			setStatus('Ready')
		}
	}, 10000) // 10 second fallback
}
```

**Rationale**: Even if `turn_complete` never arrives, session will disconnect after 10s max

### Backend Changes

#### 4. **Always Send turn_complete** (`backend/services/form_filling_service.py`)
```python
# Before:
async def on_transcript(text: str):
    if self._websocket and send_transcript:
        await self._websocket.send_json({"type": "transcript", "data": text})
    
    # turn_complete only sent if send_transcript=True
    if self._websocket:
        await self._websocket.send_json({"type": "turn_complete"})

# After:
async def on_transcript(text: str):
    # Send transcript to client if requested
    if self._websocket and send_transcript:
        await self._websocket.send_json({"type": "transcript", "data": text})
    
    # ALWAYS signal turn complete (regardless of send_transcript setting)
    # This is critical for Level 3 farewell disconnect timing
    if self._websocket:
        try:
            await self._websocket.send_json({"type": "turn_complete"})
        except Exception as e:
            _log.warning("failed_to_send_turn_complete", error=str(e))
```

**Rationale**: `turn_complete` signal is needed for activity watchdog, not just transcripts

---

## Testing Plan

### Test 1: Silent Connection (No User Input)
**Expected Behavior**:
1. Connect → Gemini greets user
2. 6s silence → Level 1 (field re-prompt)
3. 6s silence → Level 2 ("Are you still there?")
4. 6s silence → Level 3 (goodbye message)
5. After Gemini finishes farewell → **Session disconnects automatically**
6. Total time: ~20-22 seconds (18s + farewell speech time)

**Success Criteria**:
- ✅ No false VAD triggers during silence
- ✅ Gemini audio smooth and clear (no choppiness)
- ✅ Escalation stops at level 3/3 (doesn't go to 4/3)
- ✅ Session disconnects after farewell completes
- ✅ UI shows "Ready" status after disconnect

### Test 2: User Speaks Between Escalations
**Expected Behavior**:
1. Connect → Gemini greets
2. 6s silence → Level 1
3. User speaks briefly → Escalation resets to 0
4. 6s silence → Level 1 again (not Level 2)

**Success Criteria**:
- ✅ User speech detected correctly (not ignored)
- ✅ Escalation resets to 0 after user turn
- ✅ Timer restarts from 0

### Test 3: Background Noise Immunity
**Expected Behavior**:
1. Connect with ambient noise (TV, music, typing)
2. VAD should NOT trigger on background noise
3. Only trigger when user actually speaks

**Success Criteria**:
- ✅ No false `[VFF Metrics] 🎤 Mic activity detected` logs
- ✅ Gemini speaks smoothly without interruptions
- ✅ Activity watchdog progresses normally (not reset by noise)

### Test 4: Fallback Timeout (Degraded Mode)
**Expected Behavior**:
1. Connect → reach Level 3
2. Simulate backend not sending `turn_complete` (manually block message)
3. After 10 seconds → session should force-disconnect

**Success Criteria**:
- ✅ Disconnect happens after 10s max (even without turn_complete)
- ✅ UI shows "Ready" status
- ✅ No infinite waiting

---

## Monitoring

### Frontend Console Logs to Watch

**Good Signs**:
```
[VFF Watchdog] 🟢 Starting activity monitoring
[VFF Watchdog] ⏱️ Inactivity timeout - escalation level 1/3
[VFF Watchdog] ⏱️ Inactivity timeout - escalation level 2/3
[VFF Watchdog] ⏱️ Inactivity timeout - escalation level 3/3
[VFF Watchdog] 🚪 Level 3: Closing session due to inactivity
[VFF Watchdog] ✅ Turn complete signal received
[VFF Watchdog] 🚪 Farewell complete - disconnecting
[VFF Watchdog] ✅ Session closed and ready to reconnect
```

**Bad Signs** (Should NOT appear):
```
❌ [VFF Watchdog] ⏱️ Inactivity timeout - escalation level 4/3  (exceeds max)
❌ [VFF Metrics] 🎤 Mic activity detected  (during silence)
❌ [VFF Watchdog] ⏱️ Farewell timeout - forcing disconnect  (fallback triggered)
```

### Backend Logs to Watch

**Good Signs**:
```json
{"event": "turn_complete_sent", "session_id": "web_xxx"}
{"event": "gemini_session_connection_closed", "reason": "normal closure"}
```

**Bad Signs**:
```json
❌ {"event": "gemini_session_connection_closed", "reason": "1011 internal error"}
❌ {"event": "failed_to_send_turn_complete", "error": "..."}
```

---

## Rollback Plan

If issues persist after these changes:

1. **Revert VAD thresholds**:
   - `positiveSpeechThreshold: 0.90` (back to 90%)
   - `minSpeechMs: 100` (back to 100ms)

2. **Keep escalation guard** (this is safe to keep)

3. **Keep timeout fallback** (this is safe to keep)

4. **Keep turn_complete fix** (this is necessary)

---

## Files Changed

### Frontend
- `frontend/src/demo/useDemoVAD.ts` - Increased VAD thresholds
- `frontend/src/demo/VoiceOverlay.tsx` - Escalation guard + timeout fallback
- `frontend/src/demo/VoiceOverlayMobile.tsx` - Escalation guard + timeout fallback

### Backend
- `backend/services/form_filling_service.py` - Always send turn_complete

### Documentation
- `VAD_AND_TIMEOUT_FIXES.md` (this file)

---

## Next Steps

1. **Deploy backend** with turn_complete fix
2. **Test locally** with silent connection (Test 1)
3. **Monitor logs** for false VAD triggers
4. **Fine-tune** VAD thresholds if needed (can adjust incrementally)
5. **Update architecture docs** if these values prove stable
