# Polyglot PDF Form System - Implementation Plan

**Created**: October 25, 2025
**Status**: Planning Phase
**Vision**: Transform voice-driven form filler into PDF-first, multilingual form processing system

---

## Executive Summary

This plan outlines the transformation from a web-form-first system to a **PDF-driven, multilingual form processing platform**. The system will:

- Extract schema from USCIS PDF forms automatically (LLM + PyMuPDF)
- Generate dynamic web forms from extracted schemas
- Support voice-driven form filling in 24+ languages via Gemini Live
- Export completed forms back to PDF format
- Provide admin UI for schema verification and manual adjustments

**Key Technology Decisions:**
- **Voice Backend**: Gemini Live 2.5 Flash Preview (native audio I/O, auto-translation, 24+ languages)
- **PDF Processing**: PyMuPDF + LLM pipeline for extraction
- **Architecture**: PDF → Schema → WebForm → Backend → LLM → PDF Export

---

## Schema Design Clarifications (Oct 26, 2025)

**Web Form Structure:**
1. **Children Fields Grouping**: Group all children fields together in web form view for better UX
2. **Auto-Fill NA Logic**: When user fills one expandable field with "NA", auto-fill all remaining similar fields with "NA" (user can override)
3. **Auto-Mapping to Supplements**: Web form never explicitly shows supplements - auto-map to Supplement A (children) and Supplement B (narratives) during PDF export

**Narrative Handling:**
1. **Multiple Supplement Copies**: Support very long narratives by generating multiple Supplement B copies as needed
2. **Arbitrary Length**: Final PDFs can be arbitrarily long with many supplements (max ~100 pages)
3. **Formatting**: Use double newline (`\n\n`) for paragraph separation in narratives for readability in final PDF

**AI Context Management:**
1. **Deferred Concern**: Token efficiency for long narratives is separate from schema design
2. **Current Approach**: If narratives in one section, all context available to Gemini
3. **Future Optimization**: Address token management after schema pipeline is built

**Focus**: Stay focused on schema model and ground truth schema for I-589, build PDF-schema pipeline first.

---

## Implementation Phases

### **Phase 1: PDF → Schema Foundation** (Weeks 1-2)

Design schema model, build extraction pipeline, create admin verification UI.

#### **Phase 1A: Analyze PDF Structure & Design Schema Model**

**Goal**: Understand USCIS PDF structure and design comprehensive schema model.

**Tasks**:
- Analyze example USCIS PDFs (I-485, I-765, N-400) for field types, constraints, sections
- Design `FormSchema` model extending/replacing current `webForm` structure
- Define field types:
  - Basic: text, textarea, checkbox, radio, select, date
  - Special: signature, multi-page (children, employment history, addresses)
- Define schema structure: sections, validation rules, field metadata
- Create example schemas for 2-3 common forms

**Deliverables**:
- `models/form_schema.py` - Complete schema model
- `docs/schema_format.md` - Schema specification
- Example schema JSON files in `backend/schemas/examples/`

**Success Criteria**:
- Schema model supports all USCIS field types
- Example schemas validate against model
- Schema includes multi-language support fields

---

#### **Phase 1B: Build PDF → Schema Extraction Pipeline**

**Goal**: Automated extraction of form structure and fields from PDF.

**Tasks**:
- Implement PyMuPDF-based PDF parser to extract:
  - Field positions, types, labels
  - Checkbox/radio button groups
  - Text field constraints
  - Section boundaries
- Build LLM pipeline for field classification and grouping
- Implement confidence scoring for extracted fields
- Create validation layer to ensure extracted schema is complete
- Handle edge cases (multi-column layouts, complex tables)

**Deliverables**:
- `backend/pdf_extractor.py` - PDF → Schema converter
- `backend/llm_classifier.py` - LLM-based field classification
- API endpoint: `POST /api/schemas/extract-from-pdf` (accepts PDF, returns FormSchema JSON)
- Unit tests for extraction accuracy (>85% field detection rate)

**Success Criteria**:
- Successfully extracts schema from 3 different USCIS forms
- Confidence scores identify uncertain fields for manual review
- Extraction completes in <30 seconds per PDF

---

#### **Phase 1C: Create Admin UI for Schema Verification**

**Goal**: Interface for humans to verify and correct LLM-extracted schemas.

**Tasks**:
- Create admin page: `/admin/schema-review`
- Build schema verification interface:
  - Side-by-side: original PDF (left) vs. extracted schema (right)
  - Highlight low-confidence fields in yellow
  - Allow manual field editing (label, type, validation rules)
  - Add/remove fields, reorder sections
- Implement approval workflow (approve → save to production schemas)
- Add schema versioning for iterative improvements

**Deliverables**:
- `frontend/src/pages/AdminSchemaReview.tsx` - Admin verification UI
- API endpoints for schema CRUD operations
- User guide: `docs/admin_schema_guide.md`

**Success Criteria**:
- Admin can review and approve extracted schema in <10 minutes
- Manual corrections save and update schema
- Approved schemas available for form generation

---

### **Phase 2: Schema → WebForm** (Weeks 3-4)

Build dynamic form renderer, pagination, and session persistence.

#### **Phase 2A: Design Schema → WebForm Field Mapping**

**Goal**: Create robust mapping layer from schema to React components.

**Tasks**:
- Design mapping system: Schema field types → React form components
- Implement field type conversions:
  - `text` → `<input type="text" />`
  - `date` → `<DatePicker />`
  - `checkbox` → `<Checkbox />`
  - `multi-entry` → Dynamic list component (add/remove rows)
- Apply validation rules from schema to components
- Handle conditional field visibility (if supported in schema)
- **Web Form Auto-Mapping to Supplements**:
  - Children fields grouped together in web form view
  - Auto-map overflow children to Supplement A (web form doesn't explicitly show supplement sections)
  - Narrative fields auto-map to Supplement B as needed
  - Backend generates supplements automatically during PDF export
- **Smart NA Auto-Fill Logic**:
  - When user fills one expandable field with "NA", auto-fill all remaining similar fields with "NA"
  - Reduces repetitive data entry for optional fields
  - User can override auto-filled values if needed

**Deliverables**:
- `frontend/src/components/FormRenderer/` - Component library
- `frontend/src/utils/schemaMapper.ts` - Mapping logic
- `frontend/src/utils/autoFillLogic.ts` - NA auto-fill implementation
- Unit tests for all field type mappings
- Unit tests for auto-fill logic

**Success Criteria**:
- All schema field types render correctly
- Validation rules enforced on frontend
- Schema updates automatically reflect in form
- Children fields grouped and mapped to Supplement A automatically
- NA auto-fill works seamlessly for expandable fields

---

#### **Phase 2B: Implement WebForm Pagination & Dynamic Pages**

**Goal**: Multi-page forms with dynamic sections for variable-length data.

**Tasks**:
- Create pagination system driven by schema sections
- Implement dynamic multi-entry pages:
  - Children (variable number of entries)
  - Employment history (add/remove jobs)
  - Addresses (add/remove addresses)
- Add navigation: Next/Previous section, Jump to section
- Show progress indicator: "Section 3 of 7, 45% Complete"
- Handle long forms (>100 fields) with performance optimizations

**Deliverables**:
- `frontend/src/components/FormPagination.tsx` - Pagination component
- `frontend/src/components/DynamicList.tsx` - Multi-entry component
- Navigation bar with section overview

**Success Criteria**:
- Navigate through 7-section form smoothly
- Add/remove dynamic entries without losing data
- Progress indicator accurate to ±2%

---

#### **Phase 2C: Build Save/Load Functionality**

**Goal**: Session persistence for incomplete forms.

**Tasks**:
- Implement session management:
  - Create session on form start (generate session_id)
  - Auto-save every 30 seconds + on field blur
  - Manual "Save Progress" button
- Build session storage backend (file-based or DB)
- Create "Resume Session" flow:
  - Load session by ID
  - Populate form with saved data
  - Restore scroll position and current section
- Add session expiration (7 days)

**Deliverables**:
- `backend/session_manager.py` - Session CRUD operations
- API endpoints: `POST /api/sessions`, `GET /api/sessions/{id}`, `PUT /api/sessions/{id}`
- Auto-save indicator in UI

**Success Criteria**:
- Form data persists across browser refresh
- Can resume session after 3 days
- Auto-save triggers within 2 seconds of field change

---

### **Phase 3: Backend Integration** (Week 5)

Update WebSocket handlers and design Gemini tool definitions.

#### **Phase 3A: Design Schema-Based WebSocket Handlers**

**Goal**: WebSocket communication for schema-driven forms.

**Tasks**:
- Update WebSocket handlers to work with schema-based field IDs
- Implement event types:
  - `field_update` - Update single field value
  - `section_complete` - Mark section as finished
  - `form_save` - Trigger session save
- Add form metadata management (schema_name, version, session_id)
- Handle validation errors via WebSocket (real-time feedback)

**Deliverables**:
- Updated `backend/websocket_handler.py`
- WebSocket schema documentation in `docs/ws_schema.md`
- Integration tests for all event types

**Success Criteria**:
- Field updates propagate in <100ms
- Validation errors sent back to frontend in real-time
- WebSocket reconnection preserves form state

---

#### **Phase 3B: Create Tool Definitions for Schema-Driven Updates**

**Goal**: Function calling interface for Gemini to interact with forms.

**Tool Call Flow Architecture**:
- **Blocking Responses**: Every Gemini tool_call is blocking and expects a response
- **Frontend Validation**: Frontend validates tool calls BEFORE sending to backend:
  - `field_update` is not empty
  - `field_update` references actual field_ids from schema
  - `field_update` values respect field constraints (type, format, single value for radios, etc.)
- **Backend Passthrough**: Backend receives validated tool calls, processes them, returns results
- **Response Types**:
  - `field_query` → Returns field value
  - `field_update` → Returns validation confirmation message
  - `section_change` → **Special case**: Ends current Gemini session, starts new one (no response sent)

**Tasks**:
- Design Gemini function calling tools:
  - `update_field(field_id, value)` - Update single field
  - `update_multiple_fields(updates)` - Batch update
  - `get_field_info(field_id)` - Query field metadata
  - `validate_field(field_id, value)` - Pre-validate before update
  - `navigate_to_section(section_id)` - Change current section (special handling)
- Create tool definition JSON for Gemini API
- Implement tool execution handlers in backend
- Implement frontend tool validation layer
- Add error handling and retry logic

**Deliverables**:
- `backend/gemini_tools.py` - Tool definitions and handlers
- `frontend/src/utils/toolValidator.ts` - Frontend tool validation
- `backend/config/gemini_tool_schema.json` - Gemini function calling schema
- Unit tests for each tool handler
- Unit tests for frontend validation

**Success Criteria**:
- All tools execute successfully in test environment
- Frontend validation catches invalid tool calls before backend
- Tools handle edge cases (invalid field_id, type mismatch)
- Tool responses include validation feedback
- Section change correctly restarts Gemini session

---

### **Phase 4: Gemini Integration** (Week 6)

Integrate Gemini Live with new tools, implement frontend validation.

#### **Phase 4A: Integrate Gemini with New Tools & Test**

**Goal**: Connect Gemini Live to schema-driven tools.

**Tasks**:
- Update Gemini session initialization with new tool definitions
- Implement tool call routing from Gemini to backend handlers
- Test basic voice interactions:
  - "Set my first name to John"
  - "Go to the address section"
  - "What's in field 5?"
- Add error handling for failed tool calls
- Implement retry logic for transient failures

**Deliverables**:
- Updated `backend/gemini_client.py` with new tool support
- Integration tests: Voice → Tool Call → Field Update → Validation
- Test script for common voice commands

**Success Criteria**:
- Voice commands successfully update fields
- Tool call latency <500ms
- Error messages readable and actionable

---

#### **Phase 4B: Implement Schema-Based Frontend Validation**

**Goal**: Real-time validation based on schema constraints.

**Tasks**:
- Implement validation on field blur and submit:
  - Required fields (show error if empty)
  - Type validation (email, phone, date formats)
  - Length constraints (min/max characters)
  - Custom regex patterns
- Add visual feedback:
  - Red border + error message for invalid fields
  - Green checkmark for valid fields
  - Inline validation messages
- Prevent section navigation if required fields incomplete
- Validate multi-entry lists (e.g., at least 1 child if "Do you have children?" = Yes)

**Deliverables**:
- `frontend/src/utils/validator.ts` - Validation logic
- Visual validation components
- Unit tests for all validation rules

**Success Criteria**:
- Invalid entries caught immediately on blur
- Clear error messages guide user to fix issues
- Cannot submit form with validation errors

---

#### **Phase 4C: Tune tool_response Messages**

**Goal**: Optimize validation feedback for Gemini's responses.

**Tasks**:
- Design `tool_response` message format for validation errors:
  - Success: `{"status": "ok", "message": "First name updated to John"}`
  - Error: `{"status": "error", "field": "email", "message": "Invalid email format. Please provide a valid email address."}`
- Test Gemini's voice responses to validation errors
- Refine prompts to ensure Gemini explains errors clearly
- Add context to error messages (e.g., "Email must contain @")
- Implement multi-language support for error messages (Spanish, Chinese, etc.)

**Deliverables**:
- Updated `tool_response` format in all tool handlers
- Test suite for validation error scenarios
- Prompt tuning document: `docs/gemini_prompt_tuning.md`

**Success Criteria**:
- Gemini speaks error messages clearly and helpfully
- Users understand how to correct validation errors via voice
- Error messages work in 5+ languages

---

### **Phase 5: PDF Export & Print** (Week 7)

Generate completed PDFs from form data with dynamic supplement generation.

**Goal**: Export filled forms to printable, official-looking PDFs with support for very long narratives.

**Implementation Options** (Decision deferred to this phase):

**Option A: Frontend PDF Writing (pdf-lib)**:
- Frontend uses pdf-lib to write field data directly in browser
- User downloads PDF directly from browser
- Backend uninvolved in PDF generation (remains stateless)
- Pros: No backend load, works offline, user owns PDF immediately
- Cons: Larger frontend bundle, limited to browser capabilities

**Option B: Backend PDF Writing (Python library)**:
- Frontend sends form data to backend for PDF generation
- Backend uses PyMuPDF or similar to fill PDF fields
- Backend returns filled PDF as download (does NOT store it)
- Backend remains stateless (generates PDF on-demand, no persistence)
- Pros: More powerful PDF manipulation, smaller frontend bundle
- Cons: Backend processing time, requires server request

**Tasks** (common to both options):
- Map form data to original PDF field positions
- Fill in all fields programmatically
- Handle multi-page forms (children, employment, dynamic sections)
- **Dynamic Supplement Generation**:
  - **Supplement A (Children)**: Auto-generate copies for overflow children (>4)
  - **Supplement B (Narratives)**: Auto-generate multiple copies for very long narratives
  - Support arbitrarily long narratives (up to ~100 pages max)
  - Each supplement includes header fields (A-Number, Date, Name, Signature)
  - Track supplement page numbers in final PDF
- **Narrative Formatting**:
  - Use double newline (`\n\n`) for paragraph separation in narratives
  - Ensure readability and proper spacing in final PDF
  - Handle text overflow across multiple Supplement B pages
- Ensure generated PDF is fillable (not flattened)
- Add metadata to PDF (session_id, schema_name, completion_date, supplement_count)
- Create print-optimized layout
- Support downloading completed PDF

**Deliverables** (Option A):
- `frontend/src/utils/pdfWriter.ts` - pdf-lib integration
- `frontend/src/utils/supplementGenerator.ts` - Supplement A/B generation logic
- Frontend download button with progress indicator

**Deliverables** (Option B):
- `backend/pdf_generator.py` - Form data → PDF converter (stateless)
- `backend/supplement_generator.py` - Supplement A/B generation logic
- API endpoint: `POST /api/pdf/generate` (does NOT store PDF, returns immediately)
- Frontend download button with progress indicator

**Success Criteria**:
- Generated PDF matches original USCIS form layout
- All fields populated correctly (>99% accuracy)
- PDF opens in Adobe Reader, Chrome, Preview without issues
- Export completes in <10 seconds for 100-field form (excluding very long narratives)
- Supplement A auto-generated for >4 children
- Supplement B auto-generated for narratives requiring >1 page
- Narratives formatted with double newline for readability
- Final PDFs can be up to ~100 pages with multiple supplements
- **Backend remains stateless** (if Option B chosen, PDF generated on-demand, never stored)

---

### **Phase 6: Testing & Pilot** (Week 8)

Comprehensive testing across languages, forms, and use cases.

#### **Phase 6A: Multi-Language End-to-End Testing**

**Goal**: Verify system works in 5+ languages.

**Tasks**:
- Test voice input in languages:
  - Spanish
  - Mandarin Chinese
  - Vietnamese
  - Arabic
  - Tagalog
- Verify Gemini's native translation works correctly
- Test field name translation/localization (if supported)
- Check PDF export with non-English characters
- Validate date/number formatting for different locales

**Deliverables**:
- Test suite for each language with 10+ voice commands
- Language testing report with pass/fail results
- Documentation of any language-specific issues

**Success Criteria**:
- Forms completable in 5+ languages via voice
- Non-English characters render correctly in PDF
- Gemini accurately translates and updates fields

---

#### **Phase 6B: Field-Level Testing Across USCIS Forms**

**Goal**: Verify system handles different form types and edge cases.

**Tasks**:
- Test with multiple USCIS forms:
  - I-485 (Application to Register Permanent Residence)
  - I-765 (Employment Authorization)
  - N-400 (Naturalization)
  - I-130 (Petition for Alien Relative)
- Edge case testing:
  - Long text fields (>500 characters)
  - Special characters in names (é, ñ, 中)
  - Date edge cases (leap years, future dates)
  - Multi-entry lists with 10+ items
- Validation rule coverage:
  - Test all field types and validation rules
  - Verify error messages are accurate

**Deliverables**:
- Test matrix: Forms × Field Types × Edge Cases
- Bug report for any failures
- Test coverage report (target: >90% pass rate)

**Success Criteria**:
- All tested forms complete successfully
- Edge cases handled gracefully
- Test pass rate >90%

---

#### **Phase 6C: Pilot Testing with Real Users**

**Goal**: Real-world validation with 5-10 users.

**Tasks**:
- Recruit 5-10 pilot users (diverse language backgrounds)
- Provide pilot users with test forms (non-production)
- Conduct moderated sessions:
  - Observe users filling forms via voice
  - Collect feedback on UX, voice accuracy, errors
  - Note pain points and confusion
- Analyze session data:
  - Completion rates
  - Time to complete
  - Error rates by field type
- Iterate based on feedback

**Deliverables**:
- Pilot testing guide for facilitators
- User feedback report with key findings
- Prioritized bug/improvement list
- Go/no-go recommendation for production

**Success Criteria**:
- 80% of pilot users complete form successfully
- Average completion time <20 minutes for I-485
- User satisfaction score >4/5
- <5 critical bugs identified

---

## Timeline Summary

| Phase | Duration | Key Deliverable |
|-------|----------|----------------|
| 1A: Schema Design | Week 1 | FormSchema model + examples |
| 1B: PDF Extraction | Week 1-2 | Working PDF → Schema pipeline |
| 1C: Admin UI | Week 2 | Schema verification interface |
| 2A: Field Mapping | Week 3 | Schema → React component mapping |
| 2B: Pagination | Week 3 | Multi-page form navigation |
| 2C: Save/Load | Week 4 | Session persistence |
| 3A: WebSocket | Week 5 | Schema-based event handlers |
| 3B: Tool Definitions | Week 5 | Gemini function calling tools |
| 4A: Gemini Integration | Week 6 | Voice → tool call flow |
| 4B: Frontend Validation | Week 6 | Real-time validation UI |
| 4C: Validation Tuning | Week 6 | Optimized error messages |
| 5: PDF Export | Week 7 | PDF generation from form data |
| 6A: Multi-Language | Week 8 | 5+ language testing |
| 6B: Field Testing | Week 8 | Edge case coverage |
| 6C: Pilot | Week 8 | User testing + go/no-go |

**Total Duration**: 8 weeks

---

## Dependencies & Parallelization

**Can Parallelize**:
- Phase 1C (Admin UI) can start once 1A (schema design) complete
- Phase 3B (tool definitions) can start during Phase 2
- Phase 5 (PDF export) can be prototyped during Phase 4

**Must Be Sequential**:
- 1A → 1B (schema design before extraction)
- 1B → 2A (extraction before mapping)
- 2A → 2B → 3A (mapping before pagination before WebSocket)
- 3A → 4A (WebSocket before Gemini integration)
- 4A → 4B → 4C (integration before validation before tuning)
- All phases → 6 (testing requires complete system)

---

## Key Architecture Decisions

### AI Context Management (Deferred)

**Note**: Token efficiency for long narratives is a separate concern from schema design and will be addressed in a future phase.

**Current Approach**:
- If narratives are grouped in one section, Gemini will have all narrative context available
- Long narratives may consume many tokens, but this doesn't affect schema structure
- Gemini manages its own context - we cannot directly control it
- Focus remains on building ground truth schema and PDF-schema pipeline first

**Future Optimization** (Post-MVP):
- Implement narrative chunking strategies if needed
- Explore context window optimization techniques
- Monitor token usage and implement cost controls
- Consider alternative approaches if long narratives cause issues

### Stateless Backend with Frontend Data Flow

**Data Flow**:
```
FRONTEND (Source of Truth)
├── Downloads: PDF file (large) + FormSchema JSON (small)
├── Maintains: All form state in sessionStorage
├── Renders: Dynamic form from schema
└── Sends: Only Gemini-required sections → Backend

BACKEND (Stateless Passthrough)
├── Stores: Schemas only (no user data)
├── Processes: Schema sections + current values → Gemini
└── Returns: Tool call results → Frontend

GEMINI (Ephemeral Session Storage)
├── Stores: Field values in session-based context storage
├── Context: Exists only for duration of voice session
└── Cleared: When session ends or times out
```

**Field Value Storage Locations**:
1. **Frontend (sessionStorage)**: Primary source of truth, persists until tab close
2. **Gemini Session Context**: Temporary storage during voice interaction only
3. **Backend**: NEVER stores field values (schemas only)

**Why Frontend Downloads PDF + Schema Directly?**
- **Efficiency**: PDFs can be large (1-5MB), no need to route through backend
- **Stateless Backend**: Backend never stores or serves user data (HIPAA compliance)
- **Frontend Needs Both**: Schema for rendering, PDF for user reference/download
- **Backend Only Needs Context**: Sends only current section + values to Gemini

**Security Model**:
- **Field values** stored only in:
  - User's browser (sessionStorage - auto-clears on tab close)
  - Gemini's ephemeral session context (cleared when session ends)
- **Backend** stores only:
  - Form schemas (template structure, no user data)
  - Session metadata (session_id, timestamps - no field values)
- **No PII/PHI in backend** logs or storage (HIPAA compliant)

**Benefits**:
- Backend remains stateless processing passthrough
- Frontend is source of truth for all state (consistent with existing architecture)
- Reduced backend load (no large file serving)
- Maintains privacy guarantees (no PII/PHI in backend)
- User owns their data (in sessionStorage and downloadable PDF)

### Why PDF-First?

The system starts with existing, validated USCIS PDFs rather than designing forms from scratch. Benefits:
- **Accuracy**: Forms match official USCIS layouts exactly
- **Trust**: Users see familiar official forms
- **Efficiency**: No need to manually design 50+ forms
- **Updates**: When USCIS updates forms, just re-extract

### Why Gemini Live (Not Whisper)?

Gemini Live 2.5 Flash Preview provides native audio I/O and auto-translation:
- **Integrated**: Single API handles speech → understanding → response → speech
- **Multilingual**: Supports 24+ languages natively, no separate translation layer
- **Smart**: Understands context better than Whisper + separate LLM
- **Simpler**: No need to manage Whisper, translation service, and LLM separately

### Schema-Driven Architecture

All form behavior driven by schema:
- **Flexible**: Add new forms by adding schemas, no code changes
- **Consistent**: Same rendering + validation logic for all forms
- **Maintainable**: Update form = update schema JSON
- **Testable**: Validate schemas independently of code

---

## Success Metrics

### Functional
- [ ] Extract schema from USCIS PDF with >85% field detection accuracy
- [ ] Admin can verify/approve schema in <10 minutes
- [ ] Forms render correctly from schema (100+ fields)
- [ ] Voice commands update fields in 5+ languages
- [ ] PDF export matches original form layout (>99% accuracy)
- [ ] Session resume works after browser close

### Performance
- [ ] PDF extraction <30 seconds
- [ ] Form render <1 second for 200-field schema
- [ ] Voice → field update latency <500ms
- [ ] PDF export <10 seconds for 100-field form
- [ ] Auto-save triggers <2 seconds after field change

### Quality
- [ ] Backend test coverage >80%
- [ ] Frontend test coverage >70%
- [ ] Multi-language test pass rate >90%
- [ ] Pilot user completion rate >80%
- [ ] User satisfaction score >4/5

---

## Risk Mitigation

**Risk**: PDF extraction accuracy too low (<85%)
**Mitigation**: Admin UI allows manual correction; start with 3-4 forms and refine pipeline

**Risk**: Gemini voice commands don't work well in certain languages
**Mitigation**: Test early (Phase 4A), provide keyboard fallback

**Risk**: PDF export doesn't match original form layout
**Mitigation**: Use PyMuPDF to preserve original form structure, extensive testing in Phase 6B

**Risk**: Users find voice interface confusing
**Mitigation**: Pilot testing (Phase 6C) identifies issues early, iterate on prompts

**Risk**: Form rendering slow for large forms (>200 fields)
**Mitigation**: Implement lazy loading, section-based rendering, performance testing in Phase 2B

---

## Out of Scope (Future Backlog)

Features deferred to post-MVP:

- **Whisper Integration**: Gemini Live handles audio natively
- **Custom PDF Templates**: Start with USCIS forms only
- **Offline Mode**: Requires complex sync logic
- **Mobile App**: Web-first, mobile-responsive only
- **E-Signatures**: Not required for USCIS submission (wet signature)
- **Payment Integration**: Not needed for form filling
- **Conditional Logic**: Simple forms first, add if needed
- **Analytics Dashboard**: Add after pilot validation

---

## Next Steps

1. **Review & Approve Plan**: Stakeholder sign-off on approach
2. **Set Up Project Board**: Track phases in GitHub Projects or similar
3. **Begin Phase 1A**: Schema design (Week 1)
4. **Schedule Weekly Check-ins**: Review progress, adjust timeline
5. **Prepare Test Data**: Gather 5+ USCIS PDF forms for testing

---

**Document Owner**: Development Team
**Last Updated**: October 25, 2025
**Status**: Awaiting approval to begin Phase 1A
