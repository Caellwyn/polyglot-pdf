# Features & Changes Needing Confirmation

**Date**: November 8, 2025  
**Purpose**: Track features/changes that appear in planning documents but have unclear completion status

---

## High Priority - Blocking Issues

### 1. Hallucination Reduction Features (HALLUCINATION_REDUCTION_PLAN.md)
**Status**: Branch created (`feature/hallucination-reduction`), but unclear if implemented

**Needs Confirmation**:
- [deprecated] Were audio preprocessing filters (noise gate + high-pass) implemented?
- [Yes] Is Push-to-Talk (PTT) now the default mode?
- [Yes] Was single-field tool constraint implemented in backend?
- [Yes] Were confirmation workflow requirements added to system instructions?
- [Deprecated] Was proactive audio feature activated in Gemini config?

**References**: 
- Plan created Oct 30, 2025
- Branch mentioned but no commits documented
- Technical guide mentions some audio fixes on Nov 7, 2025 (noise gate threshold changes)

### 2. Token Reduction Implementation (implementation_plan_bugs_and_tokens.md)
**Status**: Planned for Day 2-3 after bug fixes, implementation status unclear

**Needs Confirmation**:
- [ ] Was just-in-time field loading implemented?
- [ ] Does handshake now send field manifest instead of full schema?
- [ ] Were tool response formats updated to include next field?
- [ ] Was get_field_value tool enhanced for field loading?
- [ ] Are loaded fields being tracked in frontend?

**Expected Benefits**: Reduce initial context from 7,400 to <500 tokens

---

## Medium Priority - Voice AI Integration

### 3. Voice AI Conditional Logic (VOICE_AI_CONDITIONAL_REQUIREMENTS.md)
**Status**: Requirements documented Oct 31, 2025, implementation unclear

**Needs Confirmation**:
- [ ] Were 26 string-format conditionals converted to structured format?
- [ ] Was bidirectional conditional index built?
- [ ] Were JavaScript-compatible unlock instructions added?
- [ ] Was conditional_evaluator.js created for frontend?
- [ ] Was voice_ai_schema_transformer.py created?

### 4. Voice Overlay Integration Status (Phase 4A)
**Status**: Audit completed Nov 5, but actual implementation unclear

**Needs Confirmation**:
- [ ] Were VoiceOverlay.tsx updates completed (30 changes)?
- [ ] Were VoiceOverlayMobile.tsx updates completed (24 changes)?
- [ ] Was connection.ts updated (7 changes)?
- [ ] Are helper functions (getCurrentPartOrder, etc.) implemented?
- [Yes] Is voice overlay actually integrated with schema-form-demo.html?

---

## Low Priority - Documentation & Process

### 5. Frontend Consolidation Status
**Status**: Plan exists but execution unclear

**Needs Confirmation**:
- [ ] Was AdultIntakeDemo.tsx deprecated/removed?
- [ ] Was WebFormStateManager fully replaced?
- [ ] Are there still two parallel state management systems?
- [ ] Was the demo pattern fully migrated to schema pattern?

### 6. Schema Conformance Pipeline
**Status**: I-90 marked complete, but other forms unclear

**Needs Confirmation**:
- [Deferred] Was conformance applied to I-589 form?
- [No] Were conformance scripts created for other forms (I-485, I-765, N-400)?
- [?] Is the field ordering regex updated (`(\d+|[A-Z])\.`)?

### 7. Idle Timeout Implementation
**Status**: Technical guide says deprecated multi-level escalation, but current state unclear

**Needs Confirmation**:
- [Yes] Is it just 60-second timeout now?
- [Yes] Were nudges/warnings removed?
- [No] Does reconnect button work properly?

---

## Testing & Validation

### 8. Test Coverage Status
**Needs Confirmation**:
- [ ] Are there unit tests for token reduction changes?
- [ ] Are there integration tests for voice overlay with schema forms?
- [ ] Do hallucination reduction features have test coverage?
- [ ] Are conditional logic features tested?

### 9. Backend Tool Definitions
**Status**: Phase 3B marked complete but details unclear

**Needs Confirmation**:
- [ ] Do all 5 tools work with schema-based forms?
- [ ] Is validation_handler.py updated for single-field constraint?
- [ ] Are tool responses including proper next field hints?

---

## Environment & Configuration

### 10. Configuration Settings
**Needs Confirmation**:
- [False] What is current `PROACTIVE_AUDIO` setting in config.py?
- [Yes] Is `DISABLE_GEMINI_VAD` set correctly?
- [ ] Are noise gate thresholds at correct levels (-50dB vs -40dB)?
- [No, but that's a good idea!] Is `USE_TOKEN_REDUCTION` flag available?

---

## How to Confirm

1. **Check Git History**: Look for commits after planning dates
2. **Test Manually**: Try features in browser to see if they work
3. **Code Search**: Search for specific function names/variables mentioned
4. **Run Tests**: Execute test suites to see coverage
5. **Review Config**: Check backend/config.py for current settings
6. **Ask Team**: If working with others, verify implementation status

---

## Notes

- Some features may be partially implemented
- Planning docs sometimes describe ideal state, not current state
- Technical guide should be source of truth for completed features
- Check branch history for `feature/hallucination-reduction` and `claude/align-websockets-011CUpAutS2MaBKLNxYFQRQM`
