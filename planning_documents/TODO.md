# Polyglot PDF - Consolidated TODO List

**Last Updated**: November 20, 2025
**Status**: Pre-ESC Pilot

---

## Critical Path (Must Complete Before Pilot)

### App Functionality ✅ COMPLETE
- [x] **Fix field validation** - A-number and other fields accepting invalid inputs
  - Backend validation now blocks invalid values from reaching frontend
  - Gemini receives informative error messages with pattern constraints
  - 7/7 unit tests passing
  - Completed: November 18, 2025

- [x] **Confirmation System Implementation** - Track user confirmations for liability protection
  - All phases complete (state model, tools, UI, logging, auto-confirmation)
  - Green checkmark UI indicators on all 6 field types
  - Audit logging (anonymized, NO PII) in `logs/confirmations/`
  - Completed: November 19, 2025

- [x] **Add native language disclaimer** - Voice announcement at session start
  - Gated modal with language selection
  - Non-dismissible until accepted
  - Backend logging of acceptance
  - 18 languages supported
  - Completed: November 19, 2025

- [x] **Implement print functionality** - Must work from tablet
  - Backend PDF filling with PyMuPDF
  - Dynamic field flag manipulation for conditional fields
  - Frontend download button
  - Tablet-friendly (browser native download)
  - Completed: November 20, 2025

- [ ] **Thorough end-to-end testing** - Full form completion multiple times
  - Estimated time: 4-6 hours
  - Test all field types
  - Test confirmation workflow
  - Test PDF generation
  - Test on actual tablets

### Legal/Compliance
- [ ] **Print paper waivers** - 20 copies of consent form
  - User understands tool is not legal advice
  - Physical signature required

- [ ] **Verify PII deletion** - Confirm all data clears on tab close/"clear form" button
  - SessionStorage cleared
  - No server-side retention

### Hardware/Setup
- [ ] **Wait for hardware delivery** - 60 disposable earbuds + 2 lapel mics
  - Status: Ordered, arriving soon
  - Test audio quality on arrival

- [ ] **Test with actual tablet hardware** - Verify functionality
  - Test Amazon Fire HD 8
  - Verify microphone quality
  - Test print/download functionality
  - Overall UX validation

---

## Nice to Have (Not Blocking Pilot)

### Features
- [ ] Multiple form support - Can add forms on-site as needed
  - I-589 schema ready, conformance pending
  - I-485, I-765, N-400 planned

- [ ] Digital save/download feature - Print-only is fine for pilot
  - Current: Download filled PDF works
  - Future: Cloud save for returning users

### Code Quality
- [x] **Fix critical bug in getFieldBySpokenName()** ✅ FIXED Nov 20, 2025
  - Was using deprecated `currentPartId` and `completedParts`
  - Now uses `currentSectionId` and `completedSections`
  - Location: `frontend/src/schema-forms/state/schemaFormState.ts:646-650`

- [x] **Update TECHNICAL_GUIDE.md** ✅ COMPLETE Nov 20, 2025
  - Update version to 4.0
  - Fix confirmationMethod documentation ('manual_edit' not 'manual_button')
  - Add idle timeout & reconnect section
  - Expand disclaimer implementation details
  - Add auto-scroll implementation section
  - Clarify JIT schema integration status
  - Standardize section vs parts terminology

- [ ] **Resolve terminology inconsistencies** - Parts vs Sections
  - Standardize on "sections" for navigation
  - Document that "parts" are organizational units in schema
  - Update comments in VoiceOverlayMobile.tsx (line 720)
  - Update backend token logging variable name (`current_part_id` → `current_section_id`)

---

## JIT Schema System (Future Optimization)

### Current Status
- ✅ Backend: 100% complete
- ✅ Frontend utilities: 100% complete
- ⚠️ Integration: Partial (by design - handshake uses legacy, then switches to JIT)
- ✅ Tests: 33/33 passing
- ✅ Token reduction: 94% verified (7,400 → 458 tokens)

### Remaining Work
- [ ] Live Gemini API testing with JIT mode enabled
- [ ] Production validation with real users
- [ ] Monitor token usage in production
- [ ] Document performance improvements
- [ ] Consider enabling by default once validated

**Feature Flag**: `USE_JIT_SCHEMA=true` in backend config (currently disabled)

---

## Documentation Cleanup

### Planning Documents to Consolidate/Remove
- [x] **CODEBASE_AUDIT_FINDINGS.md** - Created Nov 20, can be archived after TECHNICAL_GUIDE updated
- [x] **TECHNICAL_GUIDE_UPDATES_NEEDED.md** - Integrated into TECHNICAL_GUIDE.md v4.0
- [x] **5_LOGGING_OVERHAUL_PLAN.md** - Integrated into this TODO.md (deleted)
- [ ] **IMPLEMENTATION_PLAN.md** - Review and archive if superseded
- [ ] **GATED_DISCLAIMER_IMPLEMENTATION.md** - Archive (completed feature)
- [ ] **CONFIRMATION_SYSTEM_DESIGN.md** - Archive (completed feature)
- [ ] **VALIDATION_FIX_SUMMARY.md** - Archive (completed feature)
- [ ] **CRITICAL_PATH_TODO.MD** - Replace with this TODO.md

### Documentation to Update
- [ ] **PROJECT_STATE.md** - If exists, update or replace with consolidated docs
- [ ] **README.md** - Ensure setup instructions are current

---

## Known Issues

### Fixed (December 2025)
- [x] **Tablet push-to-talk stuck recording** - Fixed December 3, 2025
  - Long-press context menu was interrupting touch events
  - Added `preventDefault()` on touchstart/touchend
  - Added 5 safety mechanisms: max duration (30s), visibility change, window blur, connection loss, unmount cleanup
  - Location: `VoiceOverlay.tsx`, `VoiceOverlayMobile.tsx`

### Low Priority
- [ ] **Highlight timing inconsistency** - Two different durations (1500ms vs 2000ms)
  - `webFormConnection.ts`: 1500ms for field confirmation
  - `SchemaForm.tsx`: 2000ms for next field hint
  - Impact: Negligible (users won't notice)
  - Decision needed: Standardize or document as intentional

---

## Timeline

**Target**: Week of November 25, 2025 for ESC Pilot

**Remaining Days**: ~5 days

**Critical Path Estimate**:
- End-to-end testing: 4-6 hours
- Hardware arrival: Unknown (ordered)
- Hardware testing: 2-3 hours
- Paper waiver printing: 1 hour
- Contingency: 4 hours

**Status**: On track if hardware arrives by November 22

---

## Business Context

### Current Setup ✅
- LLC established
- E&O insurance active
- Cyber insurance active
- Cost per form: ~$5 (Gemini API)
- Target price: $20-50 per form

### Pilot Deployment
- **Location**: ESC nonprofit office
- **Hardware**: 8-inch Amazon Fire HD 8 tablets
- **Forms**: I-90 (Green Card Renewal) initially
- **Audio**: 60 disposable earbuds + 2 lapel mics
- **Network**: HTTPS required for microphone access

---

## Notes

- App already deletes PII on close ✅
- Live API version working smoothly ✅
- Confirmation logging implemented (anonymized) ✅
- Disclaimer acceptance logging implemented ✅
- PDF printing working on all platforms ✅

---


## Maintenance Tasks (Post-Pilot)

### Code Cleanup
- [ ] Remove deprecated demo system components
  - `adult_intake_demo.html` (marked deprecated)
  - Old `GreetingCarousel` components
  - Legacy authentication patterns
- [ ] Remove console.log spam (~268 frontend instances)

### Logging & Monitoring Infrastructure

**Status**: Phase 1 (Token Tracking) completed October 24, 2025

#### Phase 1: Token Tracking ✅ COMPLETE
- [x] Backend infrastructure (structured_logger.py, dev_file_logger.py, log_schemas.py)
- [x] Real-time token extraction from Gemini API usage_metadata
- [x] TEXT vs AUDIO modality breakdown (audio 6x more expensive)
- [x] Cost calculation with accurate pricing
- [x] Cumulative session tracking
- [x] Development logging to daily .jsonl files
- [x] Hardened against None values from API

#### Phase 2: Session Lifecycle Logging
- [ ] Generate form_session_id on first blur/connect (frontend)
- [ ] Store in sessionStorage: vff_form_session_id
- [ ] Log session events: session_start, session_pause, session_resume, session_complete, session_abandon
- [ ] Backend: Accept form_session_id in handshake, include in all events
- [ ] Log WebSocket events: ws_connect, ws_disconnect, ws_error, ws_timeout
- [ ] Session duration and completion rate tracking

#### Phase 3: Frontend Logger Implementation
- [ ] Create frontend/src/utils/logger.ts - Event emitter with batching
- [ ] Client-side logger in sessionStorage (PHI allowed - stays local)
- [ ] Field change tracking with old/new values (local only)
- [ ] Sanitized event batching to backend (NO values transmitted)
- [ ] Send via WebSocket: {type: "log_events", events: [...]}
- [ ] Batch every 5s or 10 events
- [ ] Fallback: POST /api/log if WebSocket closed
- [ ] Manual field update detection and logging

#### Phase 4: Field & Error Tracking
- [ ] Backend: Log field_voice_attempt on tool calls (include validation result)
- [ ] Frontend: Detect manual edits, log field_manual_edit if after voice fill
- [ ] Frontend: Log field_blur with fill_method, attempts, duration
- [ ] Section navigation logging: section_start, section_complete, section_switch
- [ ] Error categorization: validation, network, AI, tool, timeout
- [ ] Backend: Catch all exceptions, log error_* events with severity
- [ ] Frontend: Log error_network on disconnect/reconnect failures
- [ ] Include error context: field_id, section_number, tool_name, recoverable flag

#### Phase 5: BigQuery Integration
- [ ] Enable Cloud Logging API
- [ ] Create BigQuery dataset: voice_form_filler_logs
- [ ] Create tables: session_events, field_interactions, token_usage, errors
- [ ] Configure Log Sink: Cloud Logging → BigQuery
- [ ] Set retention: 30d (Cloud Logging), 90d (BigQuery raw), 2yr (aggregates)
- [ ] Backend log receiver: Listen for {type: "log_events"} WebSocket messages
- [ ] Validate structure and enrich with ws_session_id
- [ ] Emit to Cloud Logging (stdout JSON for Cloud Run)

#### Phase 6: Compliance & Audit Trail
- [ ] Create log_audit_event() function
- [ ] Separate BigQuery dataset: voice_form_filler_audit (6-year retention)
- [ ] Log audit events: audit_form_start, audit_field_update, audit_form_submit
- [ ] Hash IP addresses: SHA256(ip + salt) for privacy + traceability
- [ ] **CRITICAL VALIDATION**: Search BigQuery for field values - MUST return zero results
- [ ] Session timeline reconstruction capability
- [ ] HIPAA-compliant logging review

**Key Metrics to Track**:
- Token usage per section/form (with TEXT vs AUDIO breakdown)
- Cost per form session (current: ~$0.20 for 9-12 fields)
- Session completion rates
- Voice vs manual fill ratios
- Field validation error rates
- High-attempt fields (frustration signals)
- Voice→manual abandonment patterns

**Compliance Notes**:
- ⚠️ **NEVER LOG**: Field values, PII, PHI, user input, audio transcripts
- ✅ **ALWAYS LOG**: Field IDs, field types, counts, timestamps, interaction metadata

### Performance Monitoring
- [ ] Set up token usage monitoring dashboard (integrates with Phase 5)
- [ ] Track cost per form in production (requires Phase 2)
- [ ] Monitor error rates and validation failures (requires Phase 4)
- [ ] Collect user feedback on voice accuracy

### Future Forms
- [ ] Complete I-589 conformance
- [ ] Extract and validate I-485 schema
- [ ] Extract and validate I-765 schema
- [ ] Extract and validate N-400 schema

---

**Last Review**: November 20, 2025
**Next Review**: After ESC pilot completion
