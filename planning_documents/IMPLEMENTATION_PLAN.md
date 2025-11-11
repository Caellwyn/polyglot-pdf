# Token Reduction Implementation Plan

**Version**: 1.1  
**Created**: November 10, 2025  
**Last Updated**: November 10, 2025  
**Purpose**: Reduce Gemini context tokens from ~7,400 to <500 initial tokens through just-in-time field loading

---

## Executive Summary

This plan implements a just-in-time (JIT) schema loading system where Gemini receives only field manifests initially (field_id/spoken_name pairs), then loads complete field schemas as needed. This reduces initial context by ~90% while maintaining full functionality.

### Key Principles
- Manifest-first approach with on-demand schema loading
- Section-based context resets to prevent token accumulation  
- Previous section manifests retained for cross-section queries
- Dependency checking at tool execution time (not in manifest)
- Frontend tracks which schemas have been sent to Gemini
- Happy path (linear filling) optimized over edge cases

### Important Terminology
- **Part**: User-facing navigation unit (e.g., "Part 1 - Information About You")
- **Section**: Internal code term often referring to parts
- **Field Manifest**: Lightweight field_id/spoken_name pairs
- **Full Schema**: Complete field definition with validation, help text, options

---

## What Changes: Before vs After

### Before (Current Implementation)
- **Initial Handshake**: Sends entire section schema (~7,400 tokens)
- **Field Information**: All fields loaded upfront
- **Tool Usage**: update_form_fields only
- **Context Growth**: Stays constant through section

### After (JIT Implementation)
- **Initial Handshake**: Sends manifest + first field only (~500 tokens)
- **Field Information**: Loaded just-in-time as needed
- **Tool Usage**: update_form_fields + occasional get_field_value
- **Context Growth**: Gradual increase, capped by section resets

### What Stays the Same
- User experience (no visible changes)
- Form filling accuracy
- Voice interaction patterns
- Section/part navigation
- Manual edit capability

---

## Phase 1: Schema Preparation & Validation

**Duration**: 1-2 days
**Goal**: Ensure all schemas are ready for manifest extraction with unique identifiers
**Status**: ✅ COMPLETE (I-90), 🔄 Pending (I-589)

### Steps

#### 1.1 Spoken Name Uniqueness Validation ✅ COMPLETE
- **Task**: Audit all form schemas for duplicate spoken names
- **Actions**:
  - ✅ Created validation script `fix_duplicate_spoken_names.py` to check uniqueness across entire form
  - ✅ Generated conflict report for I-90 (19 duplicate spoken names, 46 fields affected)
  - ✅ Updated I-90 schema with unique spoken names using help text-based disambiguation
  - ✅ Validated 100% uniqueness: All 132 I-90 spoken names are now unique
  - ✅ Disambiguation strategy implemented:
    - Address fields: prefix with context ("mailing city", "physical city")
    - Unit types: prefix with role ("interpreter's unit type", "preparer's unit type")
    - Part 8 fields: numbered by entry ("entry 1 page number", "entry 2 page number")
    - Pre-populated fields: marked with "page 8" prefix
  - ✅ Deployed to all locations:
    - `pdf_schema_extractor/test_schemas/test_pdfs/i-90/i-90_schema.json`
    - `frontend/public/pdf_schema_extractor/test_schemas/test_pdfs/i-90/i-90_schema.json`
    - `schema-editor/public/schemas/i-90/i-90_schema.json`
  - 🔄 I-589 schema pending (needs conformance first - no spoken names yet)
- **Owner**: Schema extraction app team
- **Location**: `pdf_schema_extractor/test_schemas/test_pdfs/*/`
- **Tool**: `pdf_schema_extractor/fix_duplicate_spoken_names.py`
- **Note**: This work happens in the schema extraction app, not main codebase

#### 1.2 Field Dependency Simplification
- **Task**: Keep conditionals out of manifests; handle at tool execution time
- **Actions**:
  - Keep existing conditional fields in full schema (needed for web UI and validation)
  - Do NOT include conditional/dependency information in manifests sent to Gemini
  - Manifest only contains: `field_id` + `spoken_name` (no show_if, no conditional_fields)
  - Implement dynamic conditional checking in tool handlers:
    - When Gemini calls `get_field_value` on a locked/hidden field
    - Frontend/backend validates field state (is it locked? hidden? read-only?)
    - If locked, return clear error with dependency info:
      ```json
      {
        "success": false,
        "reason": "field_locked",
        "message": "This field is not yet available. First, answer: [blocking field spoken name]",
        "required_fields": [
          {"field_id": "...", "spoken_name": "marital status", "required_value": "Married"}
        ]
      }
      ```
    - Gemini reads this and knows to ask about the blocking field first
  - Same validation applies to `update_form_fields` attempts on locked fields
- **Owner**: Backend team (tool handlers) + Frontend team (conditional state checking)
- **Rationale**: Keeps manifests lightweight (~400 tokens), dependencies checked only when user tries to access them, guides Gemini naturally to required fields

#### 1.3 Test Schema Validation
- **Task**: Validate current schemas can generate clean manifests
- **Actions**:
  - Test manifest extraction with I-90 v9_conformant schema
  - Verify all field_ids are present and unique
  - Verify all spoken_names are present and unique
  - Document any fields with missing spoken names
  - Calculate actual token counts for I-90 manifest
- **Owner**: Backend team
- **Tool Location**: Create as `backend/utils/manifest_validator.py`

### Exit Criteria
- [x] Zero duplicate spoken names within I-90 form (132/132 unique)
- [ ] Zero duplicate spoken names within I-589 form (pending conformance)
- [ ] Manifest extraction succeeds for I-90 and I-589
- [ ] Token count verified <500 for I-90 manifest
- [x] Spoken name disambiguation rules documented and automated in `fix_duplicate_spoken_names.py`

---

## Phase 2: Backend Infrastructure

**Duration**: 3-4 days  
**Goal**: Modify backend to support manifest-based communication and JIT schema loading

### Steps

#### 2.1 Configuration & Feature Flag ✅ COMPLETE
- **Task**: Add toggleable JIT schema mode
- **Location**: `backend/config.py`
- **Actions**:
  - ✅ Added `USE_JIT_SCHEMA = os.getenv("USE_JIT_SCHEMA", "false").lower() == "true"`
  - ✅ Documented in `.env.example` with usage instructions
  - ✅ Default: `False` (disabled until Phase 3 testing complete)
  - 🔄 Logging on startup pending (Phase 2.2)
  - 🔄 Pass flag to form_filling_service initialization (Phase 2.2)
- **Rollback**: Setting flag to false reverts to current behavior instantly

#### 2.2 Manifest Generation Service ✅ COMPLETE
- **Task**: Create service to generate field manifests
- **Location**: `backend/services/manifest_service.py` ✅ CREATED
- **Functions Implemented**:
  - ✅ `generate_part_manifest()`: Creates lightweight field_id/spoken_name manifest
  - ✅ `get_next_field_schema()`: Gets schema for next field (used with next_field_hint)
  - ✅ `should_include_schema_in_response()`: Checks if schema already sent
  - ✅ `format_manifest_for_context()`: Pipe-separated format for Gemini
  - ✅ `estimate_manifest_tokens()`: Token counting utility
- **Key Design Decisions**:
  - Pipe-separated format: `field_id|spoken_name` (avoids JSON quote issues with brackets)
  - NO validation rules in manifest
  - NO help text in manifest
  - NO options for select/radio/checkbox fields
  - NO conditional logic in manifest
  - Includes previous_parts for cross-section lookups (read-only)
- **Schema Delivery Strategy** (Critical):
  - **next_field_hint**: Always includes schema for the hinted field (guides Gemini forward)
  - **get_field_value**: Includes schema ONLY if not already sent (user-directed, no redirect)
  - **Tracked state**: loaded_field_ids set prevents duplicate schemas in context

#### 2.3 System Instruction Template Updates
- **Task**: Create JIT-specific instruction template
- **Location**: `backend/config.py` - New `JIT_SYSTEM_INSTRUCTION_TEMPLATE`
- **Key Instructions to Add**:
  ```
  You receive a field manifest with spoken names and IDs.
  Use get_field_value to retrieve full field details when needed.
  The next_field_hint after each update includes complete schema for the next field.
  Users cannot see conditional fields on the UI until unlocked.
  If a user asks about a locked field, check its dependencies first.
  Previous section manifests allow lookups but not updates across sections.
  ```
- **Swap Logic**: Use JIT template when `USE_JIT_SCHEMA=true`

#### 2.4 Enhanced get_field_value Tool ✅ DESIGN COMPLETE
- **Location**: `backend/services/callback_handler.py` - `handle_get_field_value()`
- **Frontend Utility**: `frontend/src/schema-forms/utils/conditionalFieldCheck.ts` ✅ CREATED
- **Current Behavior**: Returns just the value
- **New Behavior**:
  ```typescript
  // Frontend: Check field accessibility first
  const accessResult = checkFieldAccess(spokenName, schema, fieldValues);

  if (!accessResult.accessible) {
      return {
          found: true,  // Field exists in schema
          accessible: false,
          reason: accessResult.reason,  // "field_hidden" | "field_read_only"
          message: accessResult.message,
          required_fields: accessResult.required_fields  // What to fill first
      };
  }

  // Field is accessible - return value + schema if NOT already sent
  // NOTE: NO next_field_hint here (prevents redirect from user's question)
  const includeSchema = !loadedFieldIds.has(fieldId);
  if (includeSchema) {
      loadedFieldIds.add(fieldId);  // Mark as sent
  }

  return {
      found: true,
      accessible: true,
      value: fieldValues[fieldId],
      schema_included: includeSchema,
      schema: includeSchema ? getFullFieldSchema(fieldId) : null
      // NO next_field_hint - user stays in control
  };
  ```

- **Response Format**:
  ```json
  // Field is locked/hidden
  {
    "found": true,
    "accessible": false,
    "reason": "field_hidden",
    "message": "The field 'spouse name' is not yet available. First, you need to fill the field 'marital status' with the value 'Married'.",
    "required_fields": [
      {
        "field_id": "p1_marital_status",
        "spoken_name": "marital status",
        "required_value": "Married",
        "current_value": null
      }
    ]
  }

  // Field is accessible
  {
    "found": true,
    "accessible": true,
    "value": "John Smith",
    "schema_included": false,  // Already sent
    "schema": null
  }
  ```

- **Implementation Status**:
  - ✅ Frontend utility created (`conditionalFieldCheck.ts`)
  - ✅ `checkFieldAccess()` function implemented
  - ✅ `getDependencyChain()` helper for complex dependencies
  - ✅ Uses existing `shouldShowField()` validation logic
  - ✅ Handles field_hidden, field_read_only, field_not_found cases
  - 🔄 Backend integration pending (needs to call frontend utility)
  - 🔄 WebSocket message handling pending

#### 2.5 Update Tool Response Enhancement
- **Location**: `backend/services/callback_handler.py` - `handle_update_form_fields()`
- **Current Behavior**: Returns success message with next_field_hint (spoken name only)
- **New Behavior**: Include next field hint WITH full schema (guides Gemini forward)
  ```python
  def build_update_response(self, updated_field, next_field, loaded_field_ids):
      # Get next field schema using manifest_service
      next_schema = get_next_field_schema(part_data, updated_field.id)

      if next_schema:
          loaded_field_ids.add(next_schema['id'])  # Mark as sent

      return {
          "success": True,
          "message": f"Updated {updated_field.spoken_name}",
          "next_field_hint": next_field.spoken_name,
          "next_field_schema": next_schema  # ALWAYS included with hint
          # This guides Gemini to the next field naturally
      }
  ```
- **Key Distinction**:
  - `update_form_fields` response: Includes hint + schema (guides forward)
  - `get_field_value` response: Schema only if not sent (user-directed, no hint)

#### 2.6 Handshake Context Preparation
- **Location**: `backend/services/form_filling_service.py` - `_prepare_handshake_context()`
- **Current**: Sends entire section schema (7,400 tokens)
- **New**: Send manifest only (first field schema sent via next_field_hint)
  ```python
  if USE_JIT_SCHEMA:
      manifest = generate_part_manifest(current_part, previous_parts)

      # First field schema attached to next_field_hint in system instructions
      # No need to send separately - unified delivery via hint mechanism
      context = {
          "manifest": format_manifest_for_context(manifest),
          "token_count": estimate_manifest_tokens(manifest)  # For monitoring
      }
  else:
      context = existing_full_schema_logic()
  ```
- **Note**: First field schema delivered via `next_field_hint` in system instructions, not as separate payload

### Exit Criteria
- [ ] Feature flag toggles successfully between modes
- [ ] Manifest generation produces valid JSON <500 tokens
- [ ] get_field_value returns dependency info for locked fields
- [ ] update_form_fields includes next_field_hint
- [ ] Token logger shows actual reduction metrics
- [ ] System runs identically with flag off

---
- **Location**: `backend/services/form_filling_service.py`
- **Changes**:
  - Replace full schema with manifest in handshake
  - Include first field's full schema with handshake
  - Add previous section manifests on section switch
  - Log token usage for comparison

### Exit Criteria
- [ ] Feature flag toggles between modes successfully
- [ ] Manifest generation produces <500 token payloads
- [ ] System instructions explain JIT workflow clearly
- [ ] Tool handlers support dependency checking
- [ ] Token logging shows 90% reduction in initial context

---

## Phase 3: Frontend State Management

**Duration**: 2-3 days  
**Goal**: Track field information delivery and coordinate with backend

### Steps

#### 3.1 State Tracking Implementation
- **Task**: Add JIT tracking to state manager
- **Location**: `frontend/src/schema-forms/state/schemaFormState.ts`
- **New State Properties**:
  ```typescript
  interface SchemaFormState {
    // existing properties...
    loadedFieldIds: Set<string>;  // Fields where Gemini has full schema
    previousPartManifests: Map<string, FieldManifest>;  // Note: using "part" 
    jitModeEnabled: boolean;  // From backend feature flag
  }
  ```
- **SessionStorage Serialization**:
  - Convert Set to Array for JSON: `Array.from(loadedFieldIds)`
  - Convert Map to Object: `Object.fromEntries(previousPartManifests)`
  - Deserialize on load: `new Set(saved.loadedFieldIds)`
- **Update Timing**: Add field to loadedFieldIds when:
  - Included in initial handshake (first field)
  - Returned from get_field_value with schema
  - Included in next_field_hint

#### 3.2 Manifest Generation Utilities
- **Task**: Create frontend manifest builders
- **Location**: `frontend/src/schema-forms/utils/manifestUtils.ts` (new)
- **Core Functions**:
  ```typescript
  // Generate manifest for current part (called "section" in backend)
  function generatePartManifest(part: Part, sections: Section[]): FieldManifest {
    // Extract all fields from sections within this part
    // Return only field_id and spoken_name
    // Maintain field order
  }
  
  // Determine if schema needed for get_field_value response
  function shouldIncludeSchema(fieldId: string, state: SchemaFormState): boolean {
    return !state.loadedFieldIds.has(fieldId);
  }
  
  // Build complete manifest for handshake
  function buildHandshakeManifest(currentPart: Part, state: SchemaFormState) {
    // Current part manifest
    // Previous part manifests from state
    // Calculate token estimate
  }
  ```

#### 3.3 Connection Manager Updates
- **Task**: Modify WebSocket connection for JIT mode
- **Location**: `frontend/src/shared/connection.ts`
- **Handshake Changes**:
  ```typescript
  private prepareHandshakePayload() {
    if (this.jitModeEnabled) {
      return {
        type: "handshake",
        manifest: buildHandshakeManifest(this.currentPart, this.state),
        first_field: this.getFirstFieldSchema(),
        loaded_fields: Array.from(this.state.loadedFieldIds)
      };
    } else {
      // Existing full schema logic
    }
  }
  ```
- **Tool Response Handling**:
  - Extract next_field_hint from update responses
  - Add field to loadedFieldIds when schema received
  - Update state after each tool call

#### 3.4 Checkbox Group Optimization
- **Task**: Handle checkbox groups as single units
- **Location**: `frontend/src/schema-forms/components/fields/CheckboxField.tsx`
- **Special Handling**:
  - Checkbox groups already treated as single field in schema
  - When loading schema for checkbox field, all options included
  - No special JIT handling needed (works with existing structure)
- **Manifest Entry**: Single entry like `{"field_id": "Part1_Checkbox4", "spoken_name": "race categories"}`

#### 3.5 Cross-Part Navigation Support
- **Task**: Enable queries across parts without updates
- **Location**: `frontend/src/shared/connection.ts`
- **Implementation**:
  - When switching parts, retain manifests in state
  - get_field_value can query any part's fields
  - update_form_fields restricted to current part only
  - Clear loadedFieldIds on part switch (Gemini context reset)
- **User Messaging**: If user tries to update previous part field:
  ```
  "To change that field, would you like to go back to Part X?"
  ```

### Exit Criteria
- [ ] State correctly tracks all loaded field IDs
- [ ] SessionStorage properly serializes Sets and Maps
- [ ] Manifest generation completes in <50ms
- [ ] Handshake uses manifests when JIT enabled
- [ ] Previous part manifests retained for lookups
- [ ] Checkbox groups handled as single fields

---

## Phase 4: Integration & Testing

**Duration**: 3 days  
**Goal**: Integrate all components and thoroughly test the system

### Steps

#### 4.1 Integration Test Suite
- **Location**: `backend/tests/integration/test_jit_schema.py` (new)
- **Test Scenarios with Expected Outcomes**:
  
  **Linear Flow Test**:
  - Start Part 1, fill fields 1→10 sequentially
  - Verify: Each field loads schema only once
  - Verify: Next_field_hint prevents get_field_value calls
  - Success: <10 get_field_value calls for 10 fields
  
  **Skip Navigation Test**:
  - Start Part 1, user jumps to field 20
  - Verify: get_field_value loads field 20 schema
  - Verify: Dependencies checked if field 20 is conditional
  - Success: Field 20 updates correctly or returns dependency error
  
  **Part Switching Test**:
  - Complete Part 1, switch to Part 2
  - Verify: Gemini context reset (loadedFieldIds cleared)
  - Verify: Part 1 manifest retained for lookups
  - User asks about Part 1 field value
  - Success: get_field_value returns value without schema
  
  **Conditional Field Test**:
  - Field 20 depends on field 18 = "Yes"
  - User tries to fill field 20 first
  - Verify: get_field_value returns locked status
  - Verify: Dependency message guides to field 18
  - Success: Clear error message, no confusion
  
  **Checkbox Group Test**:
  - Navigate to checkbox field with 20+ options
  - Verify: Single manifest entry for entire group
  - Verify: Full schema includes all options at once
  - Success: All options read in one go

#### 4.2 Token Measurement Suite
- **Tool**: Enhanced `backend/utils/token_file_logger.py`
- **Metrics to Capture**:
  ```python
  {
    "session_id": "...",
    "mode": "jit|full",
    "part_id": "part_1",
    "initial_handshake_tokens": 487,
    "manifes_tokens": 387,
    "first_field_tokens": 100,
    "cumulative_schema_tokens": 2341,  # Running total
    "get_field_value_calls": 3,
    "tool_calls_total": 45,
    "field_updates": 37
  }
  ```
- **Comparison Report**: Generate before/after metrics for same form

#### 4.3 Error Recovery Testing
- **Scenarios**:
  
  **Mid-Session Feature Toggle**:
  - Start session with JIT enabled
  - Toggle flag off mid-session
  - Verify: Next session uses full schema
  - Success: No crashes, clean transition
  
  **Corrupted Manifest**:
  - Inject malformed manifest
  - Verify: Graceful fallback to full schema
  - Success: Error logged, session continues
  
  **Missing Spoken Names**:
  - Remove spoken_name from field
  - Verify: Validation catches before session start
  - Success: Clear error message

#### 4.4 Performance Benchmarking
- **Test Setup**: I-90 form, Part 1 (37 fields)
- **Measurements**:
  | Metric | Full Schema | JIT Schema | Target |
  |--------|------------|------------|---------|
  | Initial tokens | 7,400 | Measured | <500 |
  | Tokens at field 10 | 7,400 | Measured | <2,500 |
  | Tokens at field 37 | 7,400 | Measured | <5,000 |
  | get_field_value calls | 0 | Measured | <5 |
  | Response time (avg) | Baseline | Measured | ±0.5s |
  | Memory usage | Baseline | Measured | ±10% |

#### 4.5 User Experience Testing
- **Test with Internal Team**:
  - 5 linear fillers (follow prompts exactly)
  - 5 skip-around users (jump between fields)
  - 5 bilingual users (test non-English flow)
- **Observation Points**:
  - Any confusion when field locked?
  - Any delays noticed?
  - Any accuracy differences?
- **Success Criteria**:
  - No increase in user errors
  - No increase in clarification requests
  - No complaints about response time

### Exit Criteria
- [ ] All integration tests passing (100%)
- [ ] Token reduction ≥85% verified for I-90 Part 1
- [ ] No regression in response time (±0.5s)
- [ ] No regression in accuracy (error rate ≤1%)
- [ ] Error scenarios handled gracefully
- [ ] 10+ internal users tested without issues

---

## Phase 5: Monitoring & Optimization

**Duration**: Ongoing  
**Goal**: Monitor production performance and optimize based on real usage

### Steps

#### 5.1 Monitoring Implementation
- **Metrics**:
  - Token usage per session/section/field
  - get_field_value call frequency
  - Cache hit rates for field schemas
  - Dependency check failures
  - Section switch frequency
- **Tools**: Existing token logger enhanced for JIT metrics

#### 5.2 Performance Analysis
- **Weekly Reviews**:
  - Identify high-token sections
  - Find frequently accessed fields
  - Analyze tool call patterns
  - Review error rates
- **Optimization Opportunities**:
  - Pre-load frequently accessed fields
  - Adjust section boundaries
  - Refine next_field_hint logic

#### 5.3 Future Optimizations (Backlog)
- **Potential Enhancements**:
  - Predictive loading (2-3 fields ahead)
  - Smart caching based on user patterns
  - Dynamic section splitting for long sections
  - Compressed manifest format
  - Incremental manifest updates

### Exit Criteria
- [ ] Monitoring dashboard operational
- [ ] Weekly metrics reviews scheduled
- [ ] Optimization backlog prioritized
- [ ] Documentation updated with findings

---

## Rollback Strategy

### Quick Rollback
1. Set `USE_JIT_SCHEMA=false` in backend environment
2. Frontend automatically adapts to full schema mode
3. No code deployment required

### Partial Rollback
- Enable JIT for specific forms only
- Disable for problematic sections
- Maintain monitoring to identify issues

### Full Rollback Procedure
1. Disable feature flag
2. Monitor for 24 hours
3. If stable, consider code removal
4. Document lessons learned

---

## Success Metrics Summary

### Primary Goals
- **Token Reduction**: ≥85% reduction in initial context (7,400 → <500)
- **Maintained Accuracy**: No increase in form-filling errors
- **Performance**: No user-perceived latency increase

### Secondary Goals
- **Tool Efficiency**: <5% increase in get_field_value calls
- **Developer Experience**: Clear debugging and monitoring
- **Scalability**: System handles forms with 200+ fields

### Key Performance Indicators
| Metric | Current | Target | Acceptable Range |
|--------|---------|--------|------------------|
| Initial tokens | ~7,400 | <500 | 400-600 |
| Tokens per field | ~300 | <250 | 200-300 |
| Tool call errors | <1% | <1% | 0-2% |
| Response latency | ~2s | ~2s | 1.5-2.5s |
| Cache hit rate | N/A | >80% | 70-90% |

---

## Risk Assessment

### High Risks

**1. Token Accumulation Still Excessive**
- **Risk**: By end of 37-field section, most schemas loaded anyway
- **Mitigation**: 
  - Monitor cumulative tokens at 25%, 50%, 75%, 100% completion
  - If tokens exceed 5,000 at 75%, consider mid-section reset
  - Long-term: Explore per-question sections for large forms
- **Fallback**: Revert to full schema with feature flag

**2. Spoken Name Uniqueness Enforcement**
- **Risk**: Duplicate spoken names break field lookups
- **Mitigation**:
  - Validation script must run before deployment
  - Schema extraction app must enforce uniqueness
  - Runtime detection with clear error messages
- **Fallback**: Use field_id as backup identifier

### Medium Risks

**3. Conditional Field Confusion**
- **Risk**: Users ask about fields they can't see, get confused by "locked" message
- **Mitigation**:
  - Clear dependency messages: "First, I need to know about [field X]"
  - Guide user back to blocking field naturally
  - Log frequency to assess if this is actually a problem
- **Fallback**: If >5% of interactions hit this, revisit approach

**4. Cross-Part Query Performance**
- **Risk**: Multiple get_field_value calls when referencing previous parts
- **Mitigation**:
  - Manifests include all previous parts for quick lookup
  - Cache recent queries in Gemini's context
  - Monitor cross-part query frequency
- **Optimization**: If common, consider keeping frequent fields in context

**5. Next Field Hint Reliability**
- **Risk**: If next_field_hint logic fails, Gemini lacks field info
- **Mitigation**:
  - Robust next field detection logic
  - get_field_value as backup mechanism
  - Test thoroughly with conditional fields
- **Monitoring**: Track get_field_value call frequency as health metric

### Low Risks

**6. SessionStorage Serialization Issues**
- **Risk**: Sets/Maps don't serialize, state lost on refresh
- **Mitigation**:
  - Explicit serialization utilities tested
  - Graceful degradation if state corrupted
  - User can continue with fresh state
- **Impact**: Minimal - just rebuilds loaded fields list

**7. Development Complexity**
- **Risk**: JIT mode adds debugging complexity
- **Mitigation**:
  - Feature flag for easy comparison
  - Enhanced logging for JIT operations
  - Clear documentation of data flow
- **Long-term**: Remove full schema mode after stable

### Risk Monitoring Dashboard

Create monitoring dashboard with these key indicators:
```
🟢 Green: <500 initial tokens, <5% get_field_value calls
🟡 Yellow: 500-750 tokens, 5-10% get_field_value calls  
🔴 Red: >750 tokens, >10% get_field_value calls
```

If dashboard shows yellow/red for >24 hours, consider rollback.

---

## Implementation Timeline

### Week 1: Foundation (Nov 11-15)
- **Monday**: Phase 1.1 - Spoken name uniqueness validation
- **Tuesday**: Phase 1.2-1.3 - Simplification and validation
- **Wednesday**: Phase 2.1-2.2 - Backend config and manifest service
- **Thursday**: Phase 2.3-2.4 - System instructions and tool updates
- **Friday**: Phase 2.5-2.6 - Context management and testing

### Week 2: Integration (Nov 18-22)
- **Monday-Tuesday**: Phase 3 - Frontend implementation (all steps)
- **Wednesday**: Phase 4.1-4.2 - Integration tests and token measurement
- **Thursday**: Phase 4.3-4.4 - Error recovery and benchmarking
- **Friday**: Phase 4.5 - User testing and documentation

### Week 3: Stabilization (Nov 25-29)
- **Monday**: Bug fixes from testing
- **Tuesday**: Performance optimization based on metrics
- **Wednesday**: Documentation updates
- **Thursday**: Final testing and sign-off
- **Friday**: Production deployment prep

### Implementation Order (Critical Path)

**Must Complete in Order**:
1. ✅ Fix critical bugs first (section navigation, radio buttons)
2. Spoken name uniqueness (blocks everything else)
3. Backend manifest generation (needed for testing)
4. Frontend state tracking (needed for handshake)
5. Tool handler updates (core functionality)
6. Integration testing (validates approach)

**Can Parallelize**:
- System instruction updates (while building manifest service)
- Frontend utilities (while backend work proceeds)
- Documentation (ongoing)
- Monitoring setup (anytime before deployment)

---

## Team Responsibilities

### Backend Team
- Manifest generation service
- Tool handler modifications
- System instruction updates
- Token monitoring enhancements

### Frontend Team
- State management updates
- Manifest utilities
- WebSocket integration
- UI for dependency messages

### QA Team
- Test scenario execution
- Performance benchmarking
- User acceptance coordination
- Edge case documentation

### DevOps Team
- Feature flag management
- Monitoring dashboard setup
- Rollback procedures
- Performance tracking

---

## Documentation Requirements

### To Update
- TECHNICAL_GUIDE.md - After implementation complete
- API documentation - New tool response formats
- System instruction templates - JIT mode instructions
- Debugging guide - How to troubleshoot JIT issues

### To Create
- JIT Mode Operation Guide
- Performance Tuning Guide
- Manifest Format Specification
- Dependency Resolution Guide

---

## Appendix A: Manifest Format Specification

### Initial Handshake Manifest (JIT Mode)
```json
{
  "type": "handshake",
  "mode": "jit",
  "manifest": {
    "current_part": {
      "part_id": "part_1",
      "part_label": "Information About You",
      "field_count": 37,
      "fields": [
        {"field_id": "Part1_Text1", "spoken_name": "family name"},
        {"field_id": "Part1_Text2", "spoken_name": "given name"},
        {"field_id": "Part1_Text3", "spoken_name": "middle name"},
        // ... 34 more field entries
      ]
    },
    "previous_parts": []  // Empty on first part
  },
  "first_field": {
    // Complete schema for Part1_Text1
    "field_id": "Part1_Text1",
    "type": "text",
    "label": "Family Name",
    "spoken_name": "family name",
    "validation": {
      "required": true,
      "pattern": "^[A-Za-z-' ]+$"
    },
    "help_text": "Enter your family name as it appears on your documents"
  }
}
```

### Part Switch Manifest (Moving to Part 2)
```json
{
  "type": "handshake", 
  "mode": "jit",
  "manifest": {
    "current_part": {
      "part_id": "part_2",
      "part_label": "Application Type",
      "field_count": 5,
      "fields": [
        {"field_id": "Part2_Radio1", "spoken_name": "application reason"},
        {"field_id": "Part2_Text1", "spoken_name": "receipt number"},
        // ... 3 more fields
      ]
    },
    "previous_parts": [
      {
        "part_id": "part_1",
        "fields": [
          {"field_id": "Part1_Text1", "spoken_name": "family name"},
          {"field_id": "Part1_Text2", "spoken_name": "given name"},
          // ... just field_id/spoken_name pairs
        ]
      }
    ]
  },
  "first_field": {
    // Complete schema for Part2_Radio1
  }
}
```

### get_field_value Response Examples

**Field Not Yet Loaded (includes schema)**:
```json
{
  "success": true,
  "field_id": "Part1_Text20",
  "value": null,
  "schema_included": true,
  "schema": {
    "type": "text",
    "label": "City of Birth",
    "spoken_name": "birth city",
    "validation": {"required": true},
    "help_text": "Enter the city where you were born"
  }
}
```

**Field Already Loaded (no schema)**:
```json
{
  "success": true,
  "field_id": "Part1_Text1",
  "value": "Smith",
  "schema_included": false,
  "schema": null
}
```

**Conditional Field Locked**:
```json
{
  "success": false,
  "reason": "field_locked",
  "field_id": "Part1_Text25",
  "dependencies": [
    {
      "field_id": "Part1_Radio3",
      "spoken_name": "marital status",
      "required_value": "Married"
    }
  ],
  "message": "Please provide your marital status first"
}
```

### update_form_fields Response with Next Field Hint
```json
{
  "success": true,
  "updated_field": {
    "field_id": "Part1_Text1",
    "value": "Smith"
  },
  "message": "Updated family name to Smith",
  "next_field_hint": {
    "field_id": "Part1_Text2",
    "spoken_name": "given name",
    "schema": {
      "type": "text",
      "label": "Given Name (First Name)",
      "validation": {"required": true},
      "help_text": "Enter your given/first name"
    },
    "prompt": "Now, what is your given name?"
  }
}
```

---

## Appendix B: Testing Checklist

### Pre-Implementation Tests
- [ ] Schema validation passes
- [ ] Manifest generation works
- [ ] Token counting accurate

### Integration Tests
- [ ] Linear flow (1→10)
- [ ] Skip navigation (→20)
- [ ] Backward navigation (20→5)
- [ ] Section switching
- [ ] Dependency checking
- [ ] Manual edits
- [ ] Session recovery
- [ ] Checkbox groups

### Performance Tests
- [ ] Initial tokens <500
- [ ] Per-field tokens <250
- [ ] Response time ≤2.5s
- [ ] Tool calls ≤5% increase

### User Tests
- [ ] Accuracy maintained
- [ ] No confusion increase
- [ ] Error recovery works
- [ ] Multi-language support

---

## Debugging & Troubleshooting Guide

### Common Issues and Solutions

**Issue: Gemini asks about fields out of order**
- Check: Is next_field_hint being sent correctly?
- Check: Are field orders preserved in manifest?
- Debug: Log next_field_hint contents
- Fix: Ensure field.order is used for sequencing

**Issue: get_field_value called too frequently**
- Check: Token logger shows >10% tool calls are get_field_value
- Debug: Log which fields trigger get_field_value
- Likely Cause: next_field_hint not including schema
- Fix: Verify schema included in hint

**Issue: "Field locked" errors on visible fields**
- Check: Frontend conditionals match backend logic
- Debug: Log conditional evaluation on both sides
- Fix: Sync conditional logic between frontend/backend

**Issue: Token count not decreasing**
- Check: USE_JIT_SCHEMA flag is true
- Check: Manifest being generated correctly
- Debug: Log actual tokens in handshake
- Fix: Verify manifest generation not including full schemas

### Debug Logging Points

Add structured logging at these key points:
```python
# Backend
logger.info("JIT_MODE", extra={
    "location": "handshake",
    "manifest_tokens": count,
    "first_field_tokens": count,
    "total_tokens": count,
    "mode": "jit" if USE_JIT_SCHEMA else "full"
})

logger.info("FIELD_LOADED", extra={
    "field_id": field_id,
    "method": "handshake|get_field_value|next_hint",
    "schema_included": True/False,
    "tokens": count
})
```

```typescript
// Frontend
console.log("[JIT] Field loaded:", {
  fieldId,
  source: 'initial|tool|hint',
  loadedCount: state.loadedFieldIds.size,
  timestamp: Date.now()
});
```

### Testing Checklist for Developers

Before marking JIT implementation complete:
- [ ] Initial tokens <500 verified in logs
- [ ] next_field_hint prevents most get_field_value calls
- [ ] Checkbox groups load all options at once
- [ ] Part switching clears loadedFieldIds
- [ ] Previous part lookups work without schema
- [ ] Conditional fields return clear dependency info
- [ ] Feature flag toggles cleanly
- [ ] No performance regression
- [ ] Token accumulation stays under 5,000 per part

---

## Notes & Considerations

1. **Token Accumulation**: As users progress through a section, token usage will increase as schemas accumulate in context. Section resets prevent unbounded growth.

2. **Happy Path Optimization**: System optimized for linear progression. Get_field_value calls expected to be minimal in normal usage.

3. **Dependency Complexity**: Simple dependency checking at tool level keeps manifest lightweight while maintaining safety.

4. **Cross-Section Queries**: Manifest retention allows lookups without full schema reload, balancing functionality with token efficiency.

5. **Future Enhancements**: Architecture allows for further optimization like predictive loading or dynamic sectioning without major refactoring.

---

**Document Version**: 1.0  
**Last Updated**: November 10, 2025  
**Next Review**: After Phase 2 completion  
**Status**: Ready for Implementation