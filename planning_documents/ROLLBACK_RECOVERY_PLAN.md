# Rollback Recovery - Phased Implementation Plan

**Created**: October 20, 2025  
**Purpose**: Restore features after rolling back to stable commit from 2 days ago  
**Philosophy**: One feature at a time, test thoroughly, commit after each success  
**Baseline Status**: ✅ Rolled back to known-good state

---

## Implementation Guidelines for Code Assistant

**Critical Rules**:

1. **One step at a time** - Complete entire step before moving to next
2. **Test thoroughly** - Don't proceed if exit criteria not met
3. **Commit after each step** - Granular commits enable surgical rollbacks
4. **Document failures** - If step fails, note why before rolling back
5. **Ask before proceeding** - Get approval before moving to next phase
6. **No shortcuts** - Don't skip testing "to save time"

**Commit Message Format**:
```
[Phase X Step Y] Feature Name

- Change 1
- Change 2
- Change 3

Tested: [brief test description]
Exit criteria: [✅/❌]
```

**Emergency Rollback Procedure**:

If at any point things break badly:

1. **Stop immediately** - Don't try to fix forward
2. **Commit current work** (even if broken) to a WIP branch
3. **Checkout last working commit** from this implementation sequence
4. **Verify baseline** still works
5. **Review what broke** - identify the specific change
6. **Create new branch** from last working commit
7. **Re-attempt only the broken feature** with more care
8. **Update this document** with lessons learned

**Remember**: It's always faster to rollback and retry than to debug forward from a broken state.

---

## Phase 1: Protocol Changes (User-First Interaction)

### Step 1: Remove Initial Gemini Greeting

**Goal**: Make conversation user-initiated instead of AI-initiated

**Changes Required**:
- Backend: Comment out or remove initial message sent after connection
- Backend: Ensure system instruction doesn't assume Gemini speaks first
- Frontend: No changes needed (already handles silent connection)

**Exit Criteria**:
- ✅ Connect button works
- ✅ WebSocket establishes successfully
- ✅ No audio plays immediately after connection
- ✅ When user speaks first, Gemini responds appropriately
- ✅ Gemini's first response acknowledges what user said

**Testing**:
1. Click Connect → should be silent
2. Wait 5 seconds → still silent
3. Say "Hi, I need help filling out this form" → Gemini should respond
4. Verify Gemini understood and responded appropriately

**Rollback Condition**: If Gemini doesn't respond to user's first utterance, revert this step

---

### Step 2: Language Matching Protocol

**Goal**: Gemini speaks in whatever language the user speaks in

**Changes Required**:
- Backend system instruction: Add rule that Gemini should match user's spoken language
- Backend system instruction: Clarify that form fills in English regardless of conversation language
- No hardcoded language assumptions in backend

**Exit Criteria**:
- ✅ User speaks English → Gemini responds in English
- ✅ User speaks Spanish → Gemini responds in Spanish
- ✅ Regardless of conversation language, form fields populate with English values
- ✅ No hardcoded "speak English" instructions in backend

**Testing**:
1. Connect, speak English → Gemini responds in English
2. Disconnect, refresh, connect, speak Spanish → Gemini responds in Spanish
3. In Spanish conversation, say "Mi nombre es Juan" → firstName field shows "Juan" (not translated)
4. Verify form values are always in expected format regardless of conversation language

**Rollback Condition**: If Gemini stops responding or only speaks one language, revert this step

---

## Phase 2: Audio Architecture (Shared Stream)

### Step 3: Implement Shared Audio Stream

**Goal**: Single `getUserMedia()` call shared between VAD and audio recording

**Changes Required**:
- Frontend: Create shared MediaStream on component mount
- Frontend: Pass shared stream to both RickyVAD hook and audioManager
- Frontend: Ensure proper cleanup (stop tracks on unmount)

**Exit Criteria**:
- ✅ Only ONE call to `getUserMedia()` in browser console
- ✅ Console log confirms: "Reusing existing microphone stream (shared with VAD)"
- ✅ VAD still detects speech properly
- ✅ Audio recording still works
- ✅ No microphone permission errors
- ✅ Microphone indicator disappears when disconnecting

**Testing**:
1. Open browser DevTools console
2. Click Connect
3. Count `getUserMedia` calls in console (should be 1)
4. Speak → VAD light should activate
5. Verify audio recording works (Gemini responds)
6. Disconnect → mic indicator should turn off
7. Reconnect → should reuse or create new stream cleanly

**Rollback Condition**: If VAD stops working or echo issues appear, revert this step

---

### Step 4: Enable Browser Audio Processing

**Goal**: Use browser's built-in echo cancellation, noise suppression, and auto gain

**Changes Required**:
- Frontend: Update `getUserMedia()` constraints to enable:
  - `echoCancellation: true`
  - `noiseSuppression: true`
  - `autoGainControl: true`
  - `channelCount: 1` (mono)

**Exit Criteria**:
- ✅ Audio stream created with all processing enabled
- ✅ No self-interruption (Gemini's voice doesn't trigger VAD)
- ✅ Background noise reduced
- ✅ Volume normalized across different microphones

**Testing**:
1. Connect and have Gemini speak
2. Verify VAD light does NOT activate during Gemini's speech
3. Interrupt Gemini while speaking → barge-in should work
4. Test in noisy environment → verify background noise doesn't trigger false positives
5. Test with quiet voice → verify AGC normalizes volume

**Rollback Condition**: If echo/self-interruption returns, revert this step

---

## Phase 3: VAD Optimization

### Step 5: Remove Custom Energy-Based VAD

**Goal**: Use only RickyVAD (Silero model), eliminate custom energy detection

**Changes Required**:
- Frontend: Remove any custom energy-based VAD logic from audioManager
- Frontend: Use only RickyVAD callbacks for speech detection
- Frontend: Remove energy threshold configuration

**Exit Criteria**:
- ✅ No energy calculation code in audioManager
- ✅ Only RickyVAD controls speech start/end events
- ✅ Barge-in still works when interrupting Gemini
- ✅ No false positives from ambient noise

**Testing**:
1. Connect in quiet room → no false VAD triggers
2. Cough once → should NOT trigger speech
3. Speak for 2 seconds → should trigger speech
4. Test in noisy environment (music, TV) → minimal false triggers

**Rollback Condition**: If VAD becomes unreliable or too sensitive, revert this step

---

### Step 6: Configure RickyVAD Parameters

**Goal**: Set optimal VAD parameters for medical form use case

**Changes Required**:
- Frontend: Set RickyVAD config:
  - `minSpeechMs: 300` (300ms sustained speech to trigger)
  - `positiveSpeechThreshold: 0.9` (90% confidence to start)
  - `negativeSpeechThreshold: 0.7` (70% confidence to end)
  - `redemptionMs: 400` (400ms grace period)

**Exit Criteria**:
- ✅ Brief noises (<300ms) don't trigger speech
- ✅ Actual speech (>300ms) triggers reliably
- ✅ Natural speech pauses don't end detection prematurely
- ✅ No excessive "flapping" (rapid on/off)

**Testing**:
1. Quick throat clear (~200ms) → should NOT trigger
2. Say "Hello" (~500ms) → should trigger
3. Say sentence with pause "My name... is John" → should stay triggered through pause
4. Stop speaking → should end cleanly after 400ms

**Rollback Condition**: If speech detection becomes too slow or misses real speech, revert parameters

---

### Step 7: Implement Audio Pre-Buffer

**Goal**: Prevent clipping of first syllable by buffering 500ms of audio before VAD confirms speech

**Changes Required**:
- Frontend audioManager: Create circular buffer storing last 500ms of audio chunks
- Frontend audioManager: On VAD activate, flush pre-buffer before sending live audio
- Frontend audioManager: Continuously maintain buffer even when VAD inactive

**Note on Buffer Size**: You specified 500ms. This is larger than strictly necessary (minSpeechMs: 300ms + ~100ms margin = 400ms), but the extra margin provides additional safety against clipping. If 500ms causes any issues, consider reducing to 400ms.

**Exit Criteria**:
- ✅ First syllable of speech not clipped (users don't hear "ello" when saying "Hello")
- ✅ Pre-buffer size = 500ms
- ✅ No audio quality degradation
- ✅ No increased latency for user

**Testing**:
1. Connect and speak immediately: "Hello my name is..." → verify "He-" is captured
2. Wait 5 seconds, then speak → verify first syllable still captured
3. Interrupt Gemini mid-sentence → verify barge-in is instant and first syllable captured
4. Test with various first words: "Actually...", "Wait...", "Sorry..." → all should be complete

**Rollback Condition**: If audio becomes garbled or latency increases significantly, revert this step

---

## Phase 4: Backend Enhancements

### Step 8: Empty Tool Call Validation

**Goal**: Reject tool calls with empty updates and provide instructive error to Gemini

**Changes Required**:
- Backend: Add validation in `on_tool_call` handler
- Backend: Check if `updates` dict is empty after normalization
- Backend: Return error response: "You must provide at least one field to update..."
- Backend: Log event as `empty_tool_call_rejected` for monitoring

**Exit Criteria**:
- ✅ Tool call with `{updates: []}` or `{}` is rejected
- ✅ Gemini receives clear error message
- ✅ Gemini asks user for field value instead of retrying empty call
- ✅ Non-empty tool calls still work normally
- ✅ Log event appears in backend logs when empty call rejected

**Testing**:
1. Normal flow: Say "My name is John" → field updates (control test)
2. Monitor backend logs for any `empty_tool_call_rejected` events during normal use
3. If possible, manually trigger empty tool call in backend test → verify rejection
4. Verify error message is instructive, not just "Invalid"

**Rollback Condition**: If valid tool calls start getting rejected, revert this step

---

### Step 9: Stale Connection Timeout

**Goal**: Automatically disconnect sessions that are inactive for extended periods to prevent token waste

**Changes Required**:
- Frontend: Implement activity watchdog that monitors for user speech or Gemini audio
- Frontend: After configurable timeout (e.g., 3 minutes) of inactivity, disconnect gracefully
- Frontend: Before disconnecting, optionally send warning message to backend
- Backend: Clean up session resources on disconnect

**Exit Criteria**:
- ✅ Active conversations continue indefinitely
- ✅ Inactive session (no audio either direction) disconnects after timeout
- ✅ Timeout is configurable (default 3 minutes)
- ✅ User receives visual indication before auto-disconnect (optional)
- ✅ Form data preserved in sessionStorage despite disconnect
- ✅ User can reconnect and resume

**Testing**:
1. Connect, fill one field, then stay silent for 4 minutes → should auto-disconnect
2. Connect, have ongoing conversation → should NOT disconnect
3. Connect, pause for 2 minutes, speak → timer should reset, no disconnect
4. After auto-disconnect, verify form data still in sessionStorage
5. After auto-disconnect, click Connect → should reconnect successfully

**Rollback Condition**: If active conversations get disconnected prematurely, revert this step

---

## Phase 5: Deployment (High Risk - Do Last)

### Step 10: Firebase Hosting Setup

**Goal**: Deploy demo to Firebase Hosting with proper security headers for SharedArrayBuffer

**Changes Required**:
- Project root: Create `firebase.json` with hosting config
- `firebase.json`: Add headers for COOP and COEP
- `firebase.json`: Configure public directory and rewrites
- Deploy script: Update to use `firebase deploy` instead of GCS

**Exit Criteria**:
- ✅ `firebase init hosting` completes without errors
- ✅ `firebase deploy` succeeds
- ✅ Deployed site loads in browser
- ✅ No console errors about missing security headers
- ✅ SharedArrayBuffer available in browser
- ✅ VAD works on deployed site

**Testing**:
1. Run `firebase deploy`
2. Open deployed URL in browser
3. Open DevTools console → check for SharedArrayBuffer availability
4. Click Connect → verify VAD works
5. Speak → verify speech detection works
6. Fill entire form → verify no regressions

**Rollback Condition**: If deployed site doesn't work, keep GCS deployment as primary and debug Firebase separately

---

### Step 11: Firebase CORS and Headers Verification

**Goal**: Ensure all required headers are set correctly for production

**Changes Required**:
- `firebase.json`: Add CORS headers for WebSocket backend
- `firebase.json`: Verify COOP: `same-origin`, COEP: `require-corp`
- Test cross-origin requests to backend

**Exit Criteria**:
- ✅ WebSocket connection to backend succeeds
- ✅ No CORS errors in browser console
- ✅ Security headers present in response (verify with DevTools Network tab)
- ✅ SharedArrayBuffer accessible
- ✅ No mixed content warnings

**Testing**:
1. Open deployed site in browser
2. DevTools → Network tab → filter for document
3. Check response headers for COOP and COEP
4. Click Connect → verify WebSocket establishes (no CORS errors)
5. Verify backend URL is correct (WSS, not WS for production)

**Rollback Condition**: If CORS issues prevent connection, fix headers or rollback to GCS

---

## Phase 6: Future Enhancements (Post-Stability)

### Step 12: Fill Language in Form Schema

**Goal**: Move language configuration from backend to frontend schema

**Status**: DEFERRED - Not urgent, implement after deployment is stable

**Changes Required**:
- Frontend: Add `fill_language` field to form schema
- Frontend: Pass language in handshake message
- Backend: Remove hardcoded language assumptions
- Backend: Use language from schema in system instructions

**Exit Criteria**:
- ✅ Form schema can specify any fill language
- ✅ Backend adapts system instruction based on schema language
- ✅ Same backend can serve forms in multiple languages
- ✅ No breaking changes to existing forms (default to English if not specified)

**Testing**:
- Create test schema with `fill_language: "es"` → verify Spanish form fills correctly
- Create test schema with `fill_language: "en"` → verify English form fills correctly
- Test existing forms without language field → should default to English

---

## Success Criteria (Overall)

**Development Environment**:
- ✅ All features from list work in dev
- ✅ No regressions from baseline (2 days ago)
- ✅ Each feature has passing tests
- ✅ Git history has clear commits per feature

**Production Deployment**:
- ✅ Firebase hosting works
- ✅ VAD functions on deployed site
- ✅ No security header errors
- ✅ WebSocket connects successfully
- ✅ Form filling works end-to-end

**Code Quality**:
- ✅ Each phase documented in planning docs
- ✅ Testing procedures documented
- ✅ Rollback paths clear
- ✅ No debugging code left in production

## Notes

- This plan assumes starting from a working commit from 2 days ago
- Each step is designed to be independently testable
- Phases 1-4 are relatively safe (backend/frontend logic)
- Phase 5 (deployment) is highest risk - do last
- Phase 6 (fill_language) is optional future work
- If any step fails, rollback just that step, not entire phase

**Total estimated time**: 6-8 hours for careful implementation and testing (not including deployment debugging)

---

**END OF PLAN**
