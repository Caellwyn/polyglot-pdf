# VAD Enhancement Plan - Echo Cancellation & Barge-In Improvements

**Created**: October 16, 2025
**Updated**: October 22, 2025
**Status**: Phase 1 Complete ✅ | Activity Watchdog Enhanced ✅ | Energy-based VAD Removed ✅
**Priority**: High (fixes stuttering/echo feedback issues)

**Latest Update (October 22, 2025)**:
- ✅ Removed all energy-based VAD (calibration, baseline, thresholds)
- ✅ Removed continuous silence streaming when VAD inactive
- ✅ Removed VAD warmup mode
- ✅ Now using only RickyVAD (@ricky0123/vad-web) for speech detection
- ✅ Audio sent ONLY when VAD detects actual speech (no keepalive silence)

---

## Implementation Status

### ✅ Phase 1: Quick Wins (COMPLETED)

**Changes Made:**

1. **Unified Audio Constraints** ✅
   - Added `autoGainControl: true` to audioManager.ts (was missing)
   - Added `channelCount: 1` to useDemoVAD.ts (matches recording)
   - Both systems now use identical constraints: `echoCancellation, noiseSuppression, autoGainControl, channelCount: 1`

2. **VAD Timing Optimization** ✅
   - `minSpeechMs: 100ms` (was 400ms) - Faster barge-in response
   - `redemptionMs: 300ms` (was 500ms) - Smoother end detection
   - Prevents TTS echo bleed while maintaining responsiveness

3. **Documentation Updates** ✅
   - Updated comments to clarify browser AEC (not double-processing)
   - Noted that ricky0123/vad doesn't add additional echo suppression

**Files Modified:**
- `frontend/src/shared/audioManager.ts` - Added autoGainControl
- `frontend/src/demo/useDemoVAD.ts` - Updated timing + comments

### ✅ Activity Watchdog Enhancements (COMPLETED - October 16, 2025)

**Problem**: Level 3 farewell message was being cut off mid-sentence due to fixed 5-second timeout that didn't account for variable speech speed and network latency.

**Solution**: Implemented signal-based turn completion detection using Gemini's `output_transcription` event.

**Changes Made:**

1. **Backend Turn Complete Signal** ✅
   - Added `turn_complete` message type to WebSocket protocol
   - Backend sends signal when Gemini's transcript arrives (after all audio chunks)
   - Location: `backend/services/form_filling_service.py` - `on_transcript` callback

2. **Frontend Turn Complete Handler** ✅
   - Added `vffOnTurnComplete` global callback to Window interface
   - Desktop overlay: `VoiceOverlay.tsx` - Added `waitingForFarewellRef` and callback
   - Mobile overlay: `VoiceOverlayMobile.tsx` - Mirrored desktop implementation
   - WebSocket routing: `webFormConnection.ts` - Routes `turn_complete` messages

3. **Level 3 Disconnect Logic** ✅
   - Removed fixed `setTimeout(5000)` guessing approach
   - Level 3 sets `waitingForFarewellRef.current = true` flag
   - Waits for backend `turn_complete` signal
   - Disconnects immediately when signal received

**Benefits:**
- ✅ Full farewell message plays before disconnect (no cutoff)
- ✅ Precise timing - uses Gemini's own completion signal
- ✅ No timeout guessing or race conditions
- ✅ Works consistently regardless of speech speed or network latency

**Files Modified:**
- `backend/services/form_filling_service.py` - Added turn_complete emission
- `frontend/src/shared/connection.ts` - Added Window interface type
- `frontend/src/webFormConnection.ts` - Added message routing
- `frontend/src/demo/VoiceOverlay.tsx` - Added handler and flag
- `frontend/src/demo/VoiceOverlayMobile.tsx` - Added handler and flag

### ✅ Activity Watchdog Configuration (COMPLETED)

**3-Level Progressive Escalation:**
- **Timing**: 6-second intervals (18 seconds total before disconnect)
- **Level 1 (6s)**: Re-prompt for current field (backend config)
- **Level 2 (12s)**: "Are you still there?" prompt (backend config)
- **Level 3 (18s)**: Goodbye message → wait for turn_complete → disconnect

**Configuration Files:**
- `frontend/frontend.config.ts` - Client-side timing (450ms min turn, 6s timeout, 3 levels)
- `backend/config.py` - Recovery prompt scripts (RECOVERY_PROMPT_LEVEL_1/2/3)

**Reset/Restart Logic:**
- User valid turn (≥450ms) → escalation resets to 0
- Gemini audio ends → timer restarts (escalation level unchanged)
- Audio playback callback debounced (500ms) to prevent log spam

**Next Steps:**
- **Test**: Verify stuttering/echo issues are reduced
- **Monitor**: Check if barge-in still works reliably (100ms threshold)
- **Proceed to Phase 2 if needed**: Prebuffering (if first-utterance glitches persist)
- **Proceed to Phase 3 if needed**: Output-aware gating (if echo still occurs)

---

## Problem Statement

Current implementation suffers from:
1. **Double echo cancellation**: Both browser AEC + ricky0123/vad library echo suppression
2. **Gemini TTS triggering VAD**: AI voice playback causes stuttering/interruption loops
3. **First-utterance glitches**: AudioContext suspended, no prebuffering
4. **No output-aware gating**: VAD doesn't know when Gemini is speaking

---

## Proposed Solution Analysis

The suggestions provide a comprehensive, production-ready approach. Here's my analysis:

### ✅ 1. Minimal Config (ALREADY IMPLEMENTED)

**Current State**: Already done in `useDemoVAD.ts` lines 102-107:
```typescript
getStream: async () => {
  return await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  })
}
```

**Action Required**: 
- ✅ Verify this stream is used by BOTH VAD + audio upload (need to check)
- ❌ Currently: VAD has its own stream, useWebFormFilling.ts has separate stream
- ⚠️ **ISSUE**: Two separate getUserMedia calls = double AEC overhead + potential conflicts

**Recommendation**: Share single stream between VAD and recording.

---

### ✅ 2. Disable ricky0123/vad Internal Echo Suppression

**Current State**: Library might have built-in echo suppression enabled by default.

**Investigation Needed**: Check `@ricky0123/vad-react` documentation for:
- `submitUserSpeechOnPause` config option
- Any echo cancellation/suppression flags
- Whether library applies post-processing beyond browser AEC

**Action**: Add config to disable internal echo suppression (if available).

---

### ⚠️ 3. Prebuffer + Warmup (PARTIALLY IMPLEMENTED)

**Current State**:
- `useWebFormFilling.ts` lines 268-273: AudioContext.resume() on playback attempt
- No prebuffering - audio chunks played immediately via `source.start(startAt)`
- AudioContext created lazily on first audio frame

**Gaps**:
- ❌ No warmup on connect (AudioContext created only when TTS arrives)
- ❌ No prebuffering (300-500ms accumulation before playback)
- ❌ No explicit user gesture handling (relies on connection click)

**Implementation Complexity**: Medium
- Need to accumulate first 300-500ms of audio chunks
- Track buffer state during accumulation phase
- Flush buffer in correct order after threshold reached

**Benefits**: Eliminates first-utterance glitches, smoother TTS start.

---

### 🔥 4. Output-Aware VAD Gate (NEW FEATURE - HIGH VALUE)

**Current State**: VAD has no knowledge of playback state.

**Proposed Architecture**:

```typescript
// Create analyzers for both mic input and TTS output
const micAnalyser = audioContext.createAnalyser()
const outAnalyser = audioContext.createAnalyser()

// Connect mic stream to analyser (before sending to backend)
const micSource = audioContext.createMediaStreamSource(micStream)
micSource.connect(micAnalyser)

// Connect playback destination to analyser
const ttsSource = audioContext.createBufferSource()
ttsSource.connect(outAnalyser)
ttsSource.connect(audioContext.destination)

// Compute RMS levels
function computeRMS(analyser: AnalyserNode): number {
  const dataArray = new Float32Array(analyser.fftSize)
  analyser.getFloatTimeDomainData(dataArray)
  let sum = 0
  for (let i = 0; i < dataArray.length; i++) {
    sum += dataArray[i] * dataArray[i]
  }
  return Math.sqrt(sum / dataArray.length)
}

// Gate logic (run in animation frame loop)
const MARGIN = 1.8  // micRMS must be 1.8x louder than outRMS
const START_MS = 100  // 100ms sustained above threshold
const END_MS = 250    // 250ms below threshold to end

let micAboveThresholdSince: number | null = null
let micBelowThresholdSince: number | null = null

function checkVADGate() {
  const micRMS = computeRMS(micAnalyser)
  const outRMS = computeRMS(outAnalyser)
  const threshold = outRMS * MARGIN
  
  const now = Date.now()
  
  if (micRMS > threshold) {
    // User speaking louder than AI playback
    micBelowThresholdSince = null
    if (!micAboveThresholdSince) {
      micAboveThresholdSince = now
    } else if (now - micAboveThresholdSince >= START_MS) {
      // Sustained speech detected -> send activity_start
      emitActivityStart()
    }
  } else {
    // Below threshold
    micAboveThresholdSince = null
    if (userCurrentlySpeaking) {
      if (!micBelowThresholdSince) {
        micBelowThresholdSince = now
      } else if (now - micBelowThresholdSince >= END_MS) {
        // Sustained silence -> send activity_end
        emitActivityEnd()
      }
    }
  }
  
  requestAnimationFrame(checkVADGate)
}
```

**Implementation Complexity**: High
- Need to refactor VAD callbacks to integrate with RMS-based gating
- Manage state transitions (speaking/silent)
- Coordinate with existing ricky0123/vad events
- Handle edge cases (TTS ends mid-speech, user interrupts)

**Benefits**: 
- 🔥 **Eliminates echo/stuttering** - won't trigger on AI voice
- ✅ **Preserves barge-in** - user can still interrupt
- ✅ **Tunable sensitivity** - adjust MARGIN for different environments

---

### ⚠️ 5. Runtime Flow - Grace Period After TTS

**Current State**: No TTS lifecycle tracking.

**Proposed**:
```typescript
let speakingUntil: number | null = null
const GRACE_MS = 300

// When TTS playback starts
source.onstart = () => {
  speakingUntil = Date.now() + GRACE_MS
}

// When TTS playback ends
source.onended = () => {
  speakingUntil = Date.now() + GRACE_MS  // Stricter for GRACE_MS after end
}

// In VAD gate logic
const isInGracePeriod = speakingUntil && Date.now() < speakingUntil
const effectiveMargin = isInGracePeriod ? MARGIN * 1.5 : MARGIN  // Stricter during grace
```

**Implementation Complexity**: Medium
- Track TTS playback lifecycle (onstart, onended)
- Adjust MARGIN dynamically based on grace period
- Clear speakingUntil timer when grace expires

**Benefits**: Prevents tail-echo from triggering VAD immediately after TTS ends.

---

## Implementation Priority

### Phase 1: Quick Wins (1-2 hours)
1. **Shared Audio Stream** - Use same getUserMedia for VAD + recording
2. **Disable Library Echo Suppression** - Research + add config flag
3. **AudioContext Warmup** - Create AudioContext on connect, call resume() on user gesture

### Phase 2: Prebuffering (2-3 hours)
4. **Implement Prebuffer** - Accumulate 300-500ms before starting playback
5. **Add Playback State Tracking** - Track TTS lifecycle (buffering → playing → ended)

### Phase 3: Output-Aware Gating (4-6 hours)
6. **Create AnalyserNodes** - Mic + TTS output RMS monitoring
7. **Implement Gate Logic** - RMS comparison with MARGIN threshold
8. **Integrate with VAD** - Replace/augment ricky0123/vad callbacks
9. **Add Grace Period** - Stricter thresholds after TTS ends

### Phase 4: Tuning & Testing (2-3 hours)
10. **Tune Parameters** - MARGIN, START_MS, END_MS, GRACE_MS
11. **Test Edge Cases** - Rapid barge-ins, overlapping speech, noisy environments
12. **Performance Profiling** - Verify animation frame loop doesn't impact latency

---

## Architecture Impact

### Files to Modify

**High Impact**:
- `frontend/src/demo/useDemoVAD.ts` - Add output-aware gating, shared stream
- `frontend/src/useWebFormFilling.ts` - Prebuffering, analyser nodes, TTS lifecycle

**Medium Impact**:
- `frontend/src/demo/VoiceOverlay.tsx` - Pass audio context, coordinate VAD start
- `frontend/src/demo/AdultIntakeDemo.tsx` - May need to lift AudioContext to parent

**Low Impact**:
- Planning docs - Update ARCHITECTURE.md with new VAD approach

### New Files

**Option A: Integrated Approach** (Recommended)
- Modify existing `useDemoVAD.ts` to include RMS gating logic
- Keep everything in one place for easier debugging

**Option B: Separate Module**
- Create `frontend/src/demo/useOutputAwareVAD.ts` - Wrapper around useDemoVAD
- Cleaner separation but more coordination needed

---

## Risks & Mitigation

### Risk 1: Breaking Existing VAD
**Impact**: High - could make barge-in worse  
**Mitigation**: Feature flag to toggle output-aware gating on/off  
**Rollback**: Keep original useDemoVAD.ts in git history

### Risk 2: Animation Frame Loop Performance
**Impact**: Medium - 60fps RMS computation could impact UI  
**Mitigation**: Use lower framerate (30fps or 15fps), optimize RMS calculation  
**Monitoring**: Add performance.now() metrics around gate logic

### Risk 3: Parameter Tuning Rabbit Hole
**Impact**: Low - could spend days tweaking MARGIN/thresholds  
**Mitigation**: Start with proposed defaults, only tune if issues persist  
**Acceptance Criteria**: Works in crowded bar (existing test environment)

### Risk 4: AudioContext Complexity
**Impact**: Medium - managing multiple audio graphs is error-prone  
**Mitigation**: Draw audio graph diagram before coding  
**Testing**: Unit tests for analyser node setup, integration tests for playback

---

## Testing Strategy

### Unit Tests
1. ✅ RMS computation returns valid values (0-1 range)
2. ✅ Gate logic transitions correctly (silent → speaking → silent)
3. ✅ Grace period math is correct
4. ✅ Prebuffer accumulates correct duration

### Integration Tests
1. ✅ Shared stream works for both VAD + recording
2. ✅ Analyser nodes don't affect playback quality
3. ✅ VAD callbacks fire at correct times
4. ✅ Barge-in still works with gating enabled

### Manual Tests
1. ✅ Gemini speaks → no VAD trigger (echo suppression)
2. ✅ User interrupts during TTS → immediate barge-in
3. ✅ TTS ends → no false trigger from echo tail
4. ✅ First utterance smooth (no glitches)
5. ✅ Works in noisy environment (crowded bar)

---

## Success Criteria

**Before Enhancement**:
- ❌ Gemini TTS sometimes triggers VAD (stuttering)
- ❌ First utterance has audio glitches
- ❌ Echo feedback loops occasionally occur

**After Enhancement**:
- ✅ Gemini TTS never triggers VAD (tested in 10+ conversations)
- ✅ First utterance plays smoothly (prebuffered)
- ✅ No echo feedback loops
- ✅ Barge-in latency <100ms (maintained)
- ✅ Works in crowded bar environment (existing standard)

---

## Recommendation

**Proceed with phased implementation**:
1. Start with Phase 1 (quick wins) - low risk, immediate value
2. If stuttering persists → Phase 2 (prebuffering)
3. If echo still an issue → Phase 3 (output-aware gating)
4. Phase 4 always runs after any changes

**Estimated Total Time**: 10-14 hours across all phases

**Alternative**: If time-constrained, skip prebuffering (Phase 2) and go straight to output-aware gating (Phase 3), which has highest impact on echo/stuttering.

---

## Open Questions

1. **Does ricky0123/vad-react have internal echo suppression?**  
   → Need to check docs/source code

2. **Should we replace ricky0123/vad entirely with custom RMS-based VAD?**  
   → Risky, but gives full control. Recommend augmenting instead of replacing.

3. **What's the optimal MARGIN value for medical intake use case?**  
   → Need to test with real users (quiet office vs. busy clinic)

4. **Should prebuffer be adaptive based on network conditions?**  
   → Out of scope for now, but worth considering for Phase 5

5. **Do we need separate tuning for mobile vs. desktop?**  
   → Unknown - test both after implementation

---

## Next Steps

1. **Decision**: Which phase(s) to implement first?
2. **Research**: Check ricky0123/vad-react docs for echo suppression config
3. **Design**: Draw audio graph diagram showing all nodes/connections
4. **Prototype**: Implement Phase 1 in feature branch
5. **Test**: Validate with stuttering reproduction case
6. **Iterate**: Proceed to next phase if needed

---

**Philosophy**: We're building a reliable medical tool. Accuracy and UX consistency matter more than cutting-edge features. These enhancements align with that goal by eliminating unreliable VAD behavior.
