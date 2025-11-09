# Hallucination Reduction Implementation Plan

**Branch**: `feature/hallucination-reduction`
**Created**: October 30, 2025
**Status**: In Progress

---

## Objective

Reduce AI hallucinations and improve form-filling accuracy by:
1. Implementing audio preprocessing filters (noise gate + high-pass)
2. Making Push-to-Talk (PTT) the default interaction mode
3. Enforcing single-field updates with mandatory confirmation
4. Activating Gemini's proactive audio feature
5. Strengthening system instructions for confirmation workflow

---

## Problem Statement

### Current Hallucination Patterns

1. **Missing Confirmations**: Gemini skips confirmation, especially with multi-field updates
2. **Phantom Field Filling**: Gemini fills fields without user input (e.g., filling "Last Name: Doe" after language switch)
3. **Incorrect Values**: Gemini fills fields with wrong values and doesn't read them back
4. **Background Noise Issues**: Gemini responds to irrelevant audio (background conversation, choppy audio)

### Target Use Case

Non-English speakers who cannot read field values - **verbal confirmation in user's spoken language is critical**.

---

## Implementation Tasks

### 1. Audio Processing Improvements ✅ Before VAD

**Goal**: Filter background noise and low-frequency rumble before VAD processing

**Location**: `frontend/src/shared/audioManager.ts` (audio worklet)

**Changes**:
- Add **noise gate** with -40dB threshold (gentle - allows quiet speakers)
- Add **high-pass filter** at 80Hz cutoff with Q-factor 0.7
- Apply both filters BEFORE VAD processing in the audio worklet chain

**Rationale**: Clean audio input improves VAD accuracy and reduces Gemini responding to background noise

---

### 2. Push-to-Talk (PTT) as Default

**Goal**: Make PTT the primary interaction mode, keeping VAD code for potential future use

**Desktop Overlay** (`frontend/src/demo/VoiceOverlay.tsx`):
- Restore PTT toggle UI (iOS-style switch with 🎤 Auto / ⌨️ PTT icons)
- Set default: `pushToTalkMode: true`
- Keep VAD code intact but inactive

**Mobile Overlay** (`frontend/src/demo/VoiceOverlayMobile.tsx`):
- Add NEW full-width bar button at bottom of overlay (like voice memo apps)
- Set default: `pushToTalkMode: true`
- Keep VAD code intact but inactive

**Files**:
- `frontend/src/demo/VoiceOverlay.tsx`
- `frontend/src/demo/VoiceOverlayMobile.tsx`

**Rationale**: PTT gives users explicit control over when audio is sent, reducing false positives and improving accuracy

---

### 3. Single-Field Tool Constraint

**Goal**: Force Gemini to update exactly 1 field per tool call

**Tool Definition Update** (`backend/config.py`):
- Update `update_form_fields` tool to accept only 1 field
- Change parameter description to emphasize "EXACTLY ONE FIELD"
- Update examples to show single-field calls only

**Validation** (`backend/services/validation_handler.py`):
- Add validation: reject tool calls with 0 fields or 2+ fields
- Return clear error message: "Tool must update exactly 1 field, received {count}"
- Comment out old multi-field code (preserve for future)
- Add parallel single-field validation logic

**System Instruction Update** (`backend/config.py`):
- Update `SYSTEM_INSTRUCTION` to reflect single-field workflow
- Add examples showing one field at a time
- Remove any references to batching multiple fields

**Rationale**: Multi-field updates correlate with higher hallucination rates. Single-field forces deliberate, confirmed updates.

---

### 4. Enhanced Confirmation Requirements

**Goal**: Ensure Gemini ALWAYS confirms field values before moving on

**System Instruction Changes** (`backend/config.py`):

Add to `SYSTEM_INSTRUCTION`:
```
CONFIRMATION POLICY (CRITICAL - NEVER SKIP):
• After EVERY field update, you MUST read back the value in user's spoken language
• Pattern: Ask → User Responds → Call update_form_fields → Read Back Value → Ask "Is that correct?" → Wait for Confirmation → Next Field
• Example:
  You: "What is your phone number?"
  User: "555-1234"
  You: [Call update_form_fields({'phone': '555-1234'})]
  You: "I've recorded your phone number as 555-1234. Is that correct?"
  User: "Yes"
  You: "Great! What is your email address?"
• NEVER fill a field without the user explicitly providing that information
• NEVER assume or guess field values
• NEVER move to next field until user confirms the value is correct
• If user says "no" or corrects you, update the field and confirm again
```

**Workflow Enforcement**:
- Gemini requests field
- User provides information for 1 field
- Gemini calls `update_form_fields` with 1 field
- Gemini reads back value in user's spoken language
- Gemini asks for confirmation
- User confirms or corrects
- If corrected, Gemini updates and confirms again
- Only after confirmation, move to next field

**Rationale**: Verbal confirmation is critical for non-English speakers who cannot read screen. Opt-out via PTT (user can interrupt).

---

### 5. Proactive Audio Activation

**Goal**: Enable Gemini to ignore irrelevant audio inputs (choppy audio, background conversation)

**Backend Config** (`backend/config.py`):
- Set `PROACTIVE_AUDIO: bool = True`

**Gemini API Config** (`backend/adapters/live_ai_gemini.py`):
- Add to session config in `_run_session_loop()`:
```python
config = {
    "response_modalities": ["AUDIO"],
    "proactivity": {
        "proactive_audio": True
    },
    "tools": tools_config,
    ...
}
```

**Reference**: See `planning_documents/code_examples/proactivate_audio.py`

**Existing Instructions**: Keep current off-topic redirection instructions (working well)

**Rationale**: Proactive audio helps Gemini filter out dirty audio and stay focused on form-filling conversation.

---

## Testing Plan

### Audio Filter Testing
- [ ] Test with quiet speaker (should still be heard clearly)
- [ ] Test with background noise (conversation, TV, traffic)
- [ ] Test with low-frequency rumble (HVAC, traffic)
- [ ] Verify VAD still detects speech properly with filters active

### PTT Mode Testing
- [ ] Desktop: Toggle switch appears and works correctly
- [ ] Mobile: Full-width bar button appears and responds to touch
- [ ] Both: PTT mode is default on page load
- [ ] Both: Audio only transmits when PTT button is pressed
- [ ] Both: Gemini cannot hear user when PTT not pressed

### Single-Field Validation Testing
- [ ] Gemini updates exactly 1 field per call (normal case)
- [ ] Tool call with 0 fields is rejected with clear error
- [ ] Tool call with 2+ fields is rejected with clear error
- [ ] Error messages guide Gemini to correct behavior
- [ ] Old multi-field code is commented out and preserved

### Confirmation Workflow Testing
- [ ] Gemini confirms EVERY field update verbally
- [ ] Confirmation is in user's spoken language
- [ ] Gemini waits for user confirmation before moving to next field
- [ ] User can interrupt confirmation with PTT to correct
- [ ] Gemini never fills fields without user providing information
- [ ] Gemini never guesses or assumes field values

### Proactive Audio Testing
- [ ] Gemini ignores choppy/dirty audio
- [ ] Gemini ignores background conversation
- [ ] Gemini responds to clear, relevant user input
- [ ] Existing off-topic redirection still works

---

## Implementation Order

1. ✅ Create branch: `feature/hallucination-reduction`
2. Add audio filters (noise gate + high-pass) to audio worklet
3. Restore PTT toggle UI on desktop overlay
4. Add PTT bar button UI to mobile overlay
5. Set PTT as default on both overlays
6. Update `update_form_fields` tool definition for single field
7. Add single-field validation in validation handler
8. Update system instruction for confirmation emphasis
9. Enable proactive_audio in Gemini config
10. Update `PROACTIVE_AUDIO` setting in config.py
11. Test audio filters with various conditions
12. Test PTT mode on desktop and mobile
13. Test single-field constraint enforcement
14. Test confirmation workflow end-to-end

---

## Files to Modify

### Frontend
- `frontend/src/shared/audioManager.ts` - Add audio filters
- `frontend/src/demo/VoiceOverlay.tsx` - Restore PTT toggle, set default
- `frontend/src/demo/VoiceOverlayMobile.tsx` - Add PTT bar, set default

### Backend
- `backend/config.py` - Tool definition, system instruction, PROACTIVE_AUDIO setting
- `backend/services/validation_handler.py` - Single-field validation
- `backend/adapters/live_ai_gemini.py` - Add proactive_audio to session config

---

## Code Preservation Strategy

**Multi-field code**: Comment out with clear markers for potential future revert
```python
# HALLUCINATION_REDUCTION: Temporarily disabled multi-field updates (Oct 30, 2025)
# May revert if single-field proves too restrictive
# OLD CODE:
# if len(updates) > 0:
#     validate_all_fields(updates)
# NEW CODE (single-field only):
if len(updates) != 1:
    return error_message("Tool must update exactly 1 field")
```

**VAD code**: Keep intact but inactive (conditional or default state change)
```typescript
// VAD kept inactive for now - may reactivate in future
const [pushToTalkMode, setPushToTalkMode] = useState(true)  // Was: false
```

---

## Success Metrics

**Target Improvements**:
- **Hallucination rate**: < 1% (from current ~5-10%)
- **Confirmation rate**: 100% (verbal confirmation for every field)
- **Accuracy rate**: > 99% (correct field values with user verification)
- **Background noise rejection**: No responses to irrelevant audio

**Monitoring**:
- Log confirmation workflow completion rate
- Track tool call rejections (0 or 2+ fields)
- Monitor user corrections per field (should decrease)
- Track audio filter impact on VAD false positives

---

## Rollback Plan

If hallucination reduction features cause issues:

1. **Audio filters causing issues**: Remove filters from worklet, revert to raw audio
2. **PTT too restrictive**: Change default back to VAD mode (keep PTT as option)
3. **Single-field too slow**: Uncomment multi-field code, update tool definition back
4. **Proactive audio causing problems**: Set `proactive_audio: False` in config

All original code preserved via comments and git history.

---

## Notes

- **Non-English speakers**: Primary use case - must prioritize accuracy over speed
- **Verbal confirmation**: Critical for users who cannot read screen
- **PTT interruption**: Users can skip long confirmations by interrupting with PTT
- **Audio quality**: Filters should help without excluding quiet speakers
- **Proactive audio**: Main goal is ignoring dirty/background audio, not topic filtering

---

## References

- `planning_documents/code_examples/proactivate_audio.py` - Proactive audio example
- `docs/releases/PTT_MODE_AND_UX_IMPROVEMENTS_OCT_2025.md` - Previous PTT implementation
- `planning_documents/PROJECT_CONTEXT.md` - Design principles (Accuracy Over Speed)
- `planning_documents/TECHNICAL_GUIDE.md` - Audio pipeline architecture
