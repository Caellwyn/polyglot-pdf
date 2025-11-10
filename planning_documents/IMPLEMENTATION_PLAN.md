# Consolidated Implementation Plan

**Date**: November 8, 2025  
**Status**: Active Development  
**Purpose**: Single source of truth for all pending implementation work

---

## Critical Bugs ✅ ALL FIXED (Nov 8, 2025)

All 5 critical bugs related to FieldValue wrapper handling have been fixed:
- ✅ Bug 1: [object Object] display
- ✅ Bug 2: Radio buttons reset form
- ✅ Bug 3: Section navigation broken
- ✅ Bug 4: Validation always failing
- ✅ Bug 5: Conditional fields not showing

See TECHNICAL_GUIDE.md for detailed implementation notes.

---

## Token Reduction Implementation (Priority 2)

### Goal: Reduce token usage by ~90% (from 7,400 to <500 initial)
**Time Estimate**: 2-3 days

### Backend Changes

#### 1. Lightweight Handshake Context
**File**: `backend/services/form_filling_service.py`

```python
def _prepare_handshake_context(self, section_data):
    # Send field manifest (400 tokens) + current field (200 tokens)
    # Instead of entire section (7,400 tokens)
```

#### 2. Update System Instruction
**File**: `backend/config.py`
- Add field manifest section
- Update workflow to load fields just-in-time
- Add field access instructions

#### 3. Tool Response Enhancement
**File**: `backend/services/callback_handler.py`
- Include next field details in update responses
- Enhance get_field_value for field loading

### Frontend Changes

#### 1. Update Handshake Payload
**File**: `frontend/src/webFormConnection.ts`
- Create field manifest
- Send current field detail only

#### 2. Track Loaded Fields
**File**: `frontend/src/schema-forms/state/schemaFormState.ts`
- Add `loadedFieldIds: Set<string>`
- Track which fields have been sent to Gemini

### Testing & Metrics
- Monitor token usage with logging
- Test linear flow (fields 1-10)
- Test skip navigation (jump to field 20)
- Test section changes
- Target: <500 initial tokens, <250 per field

---

## Hallucination Reduction Features (Priority 3)

### Goal: Reduce hallucination rate to <1%
**Branch**: `feature/hallucination-reduction`

### 1. Audio Processing Improvements
**Status**: Partially complete (noise gate adjusted Nov 7)  
**TODO**: Verify high-pass filter implementation

**Files**: `frontend/src/shared/audioManager.ts`, `audio-processor.worklet.ts`
- ✅ Noise gate at -50dB (completed Nov 7)
- ⚠️ High-pass filter at 80Hz (needs confirmation)
- ✅ PTT mode bypasses noise gate

### ✅ 2. Push-to-Talk Default Mode
**Files**: `VoiceOverlay.tsx`, `VoiceOverlayMobile.tsx`
- Set `pushToTalkMode: true` as default
- Add PTT bar button for mobile
- Keep VAD code inactive but available

### 3. Single-Field Tool Constraint
**Files**: `backend/config.py`, `backend/services/validation_handler.py`
- Update tool definition to accept exactly 1 field
- Add validation to reject 0 or 2+ field updates
- Update system instruction examples

### 4. Enhanced Confirmation Workflow
**File**: `backend/config.py`
- Add strict confirmation policy to system instruction
- Pattern: Ask → Respond → Update → Read Back → Confirm → Next
- Never skip confirmation for non-English speakers

### 5. [Deprecated] Proactive Audio Activation
**Files**: `backend/config.py`, `backend/adapters/live_ai_gemini.py`
- Set `PROACTIVE_AUDIO: bool = True`
- Add to session config: `"proactivity": {"proactive_audio": True}`

---

## Voice AI Conditional Logic (Priority 4)

### Goal: Enable runtime conditional field display/validation
**Time Estimate**: 3-4 days

### Phase 1: Convert String Conditionals
**Tool**: Create `conditional_logic_parser.py`
- Parse 26 string-format conditionals into structured format
- Extract trigger fields, values, dependent fields

### Phase 2: Build Bidirectional Index
**Tool**: Create `build_conditional_index.py`
- Generate trigger → dependent mappings
- Generate dependent → trigger mappings
- Add to schema top-level

### Phase 3: JavaScript Runtime Evaluator
**Tool**: Create `conditional_evaluator.js`
- Evaluate condition expressions
- Return fields to show/hide/unlock
- Validate conditionally required fields

### Phase 4: Voice AI Transformer
**Tool**: Create `voice_ai_schema_transformer.py`
- Add skip_if metadata
- Optimize for streaming
- Flatten conditional relationships

---

## Voice Overlay Integration (Priority 5)

### Goal: Complete Phase 4A integration
**Files**: `VoiceOverlay.tsx`, `VoiceOverlayMobile.tsx`, `connection.ts`

### Required Changes (61 total)
- **VoiceOverlay.tsx**: 30 updates
- **VoiceOverlayMobile.tsx**: 24 updates
- **connection.ts**: 7 updates

### Key Updates
1. Replace WebFormStateManager with SchemaFormStateManager
2. Update state variables (currentSection → currentPartId)
3. Fix section dropdown to use parts array
4. Add helper functions for part navigation
5. Update all state sync logic

---

## Multi-Form Conformance (Priority 6)

### Goal: Apply conformance to multiple USCIS forms
**Status**: I-90 complete, others pending

### Next Forms
1. **I-589 (Asylum)** - Apply existing conformance script
2. **I-485 (Adjustment of Status)** - Create conformance adaptation
3. **I-765 (Work Permit)** - Create conformance adaptation
4. **N-400 (Citizenship)** - Create conformance adaptation

### Process per Form
1. Adapt `conform_i90_schema.py` for form structure
2. Run 6-step conformance pipeline
3. Validate with Pydantic models
4. Run round-trip PDF testing

---

## Testing & Documentation Updates

### Testing Priorities
1. Unit tests for token reduction
2. Integration tests for voice overlay
3. Hallucination reduction test scenarios
4. Conditional logic test cases
5. Multi-form round-trip tests

### Documentation Updates
1. Update TECHNICAL_GUIDE.md with completed features only
2. Update PROJECT_CONTEXT.md with current architecture
3. Remove deprecated planning sections
4. Add troubleshooting for new features

---

## Implementation Schedule

### Week 1 (Nov 11-15)
**Focus**: Critical Bug Fixes & Token Reduction
- [ ] Day 1: Fix Bug 2 (Radio buttons) - 2 hours
- [ ] Day 1: Fix Bug 3 (Section navigation) - 4 hours  
- [ ] Day 2-3: Implement token reduction backend
- [ ] Day 4: Implement token reduction frontend
- [ ] Day 5: Test and document fixes

### Week 2 (Nov 18-22)
**Focus**: Hallucination Reduction & Testing
- [ ] Day 1-2: Complete hallucination reduction features
- [ ] Day 3: Voice overlay integration updates
- [ ] Day 4-5: Comprehensive testing and fixes

### Week 3 (Nov 25-29)
**Focus**: Conditional Logic & Multi-Form
- [ ] Day 1-2: Implement conditional logic system
- [ ] Day 3-4: Apply conformance to I-589
- [ ] Day 5: Documentation and cleanup

---

## Success Metrics

### Bug Fixes
- [ ] All form fields display correctly (no [object Object])
- [ ] Radio buttons don't reset other fields
- [ ] All 8 sections are navigable

### Performance
- [ ] Initial context <500 tokens
- [ ] Hallucination rate <1%
- [ ] Confirmation rate 100%

### Features
- [ ] Conditional logic works in voice and web
- [ ] Multiple forms conform to schema model
- [ ] Voice overlay fully integrated

---

## Rollback Strategy

Each feature has independent rollback:
- **Token Reduction**: `USE_TOKEN_REDUCTION = False` flag
- **Hallucination**: Revert audio filters, PTT default, proactive settings
- **Voice Overlay**: Keep old WebFormStateManager as fallback
- **Conditionals**: Disable evaluator, fall back to static display

---

## Notes

- Branch `fix/critical-bugs-and-token-reduction` for bugs + tokens
- Branch `feature/hallucination-reduction` for AI accuracy
- Keep features isolated for easier testing/rollback
- Update TECHNICAL_GUIDE.md only after feature is working
- Test each feature thoroughly before moving to next
