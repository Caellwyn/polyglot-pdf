# Polyglot Forms - Pre-ESC Pilot Checklist

## Critical Path Items (Must Complete Before Pilot)

### App Functionality
- [x] **Fix field validation** - A-number and other fields accepting invalid inputs ✅ COMPLETE
  - Backend validation now blocks invalid values from reaching frontend
  - Gemini receives informative error messages with pattern constraints
  - 7/7 unit tests passing

- [x] **Confirmation System Implementation** - Track user confirmations for liability protection ✅ COMPLETE (Nov 18, 2025)

  **Phase 1: State & Data Model** ✅ COMPLETE
  - [x] 1.1 Add `confirmed` boolean to FieldValue type (frontend)
  - [x] 1.2 Update SchemaFormState to track confirmation status per field
  - [x] 1.3 Add confirmation status to backend field state responses

  **Phase 2: Gemini Tools** ✅ COMPLETE
  - [x] 2.1 Create `confirm_field` tool declaration
    - Parameters: field_id, confirmation_method (verbal/manual)
    - Returns: success status, next unconfirmed field hint
  - [x] 2.2 Implement confirm_field tool handler in backend
  - [x] 2.3 Update `get_form_status` tool to return confirmation status (with token optimization)
    - Response: {field_id: {value: "...", confirmed: true/false}}
  - [x] 2.4 Update system instruction to explain confirmation workflow
    - "After filling a field, ask user to confirm before moving on"
    - "Manual edits are automatically confirmed"

  **Phase 3: Next Field Logic** ✅ COMPLETE
  - [x] 3.1 Update computeNextField() to prioritize unconfirmed fields
  - [x] 3.2 Change next_field_hint to focus on first unconfirmed field
  - [x] 3.3 Tests: 7/7 navigation confirmation tests passing

  **Phase 4: UI Indicators** ✅ COMPLETE
  - [x] 4.1 Add visual confirmation indicator (green checkmark badge) to all field types
  - [x] 4.2 Add CSS styles for confirmed vs unconfirmed states
  - [x] 4.3 Update all 6 field components (TextField, TextAreaField, RadioField, CheckboxField, DateField, SelectField)
  - [x] 4.4 Add `form-field--confirmed` CSS class and badge styling

  **Phase 5: Auto-Confirmation Rules** ✅ COMPLETE
  - [x] 5.1 Mark manual edits as automatically confirmed
  - [x] 5.2 Ensure manual field updates set confirmed=true with confirmation_method='manual_edit'
  - [x] 5.3 Implemented in SchemaForm.tsx handleFieldChange()

  **Phase 6: Confirmation Logging** ✅ COMPLETE
  - [x] 6.1 Log confirmation events with timestamps (anonymized, no PII)
    - Format: {timestamp, form_id, form_session_id, field_id, field_name, confirmation_method}
  - [x] 6.2 Create logs/confirmations/ directory structure
  - [x] 6.3 One JSONL file per form_session_id for easy correlation
  - [x] 6.4 Implemented log_form_session_start() and log_form_session_end() functions
  - [x] 6.5 Unit tests passing in test_confirm_field_tool.py
- [x] **Add native language disclaimer** - Voice announcement at session start about tool vs legal advice ✅ COMPLETE (Nov 18, 2025)
  - Implemented in SYSTEM_INSTRUCTION and JIT_SYSTEM_INSTRUCTION templates
  - Gemini announces disclaimer on first interaction (section 1, filled_count=0)
  - Disclaimer text: "This tool helps you fill out forms, but it is NOT legal advice. For legal guidance, please consult an attorney or qualified legal professional. Do you understand and wish to continue?"
  - Automatically translated to user's detected language
  - Waits for user acknowledgment before proceeding
  - Skipped on subsequent sections (section > 1 OR filled_count > 0)
  - Backend tests passing (5/5)
- [x] **Implement print functionality** - Must work from tablet ✅ COMPLETE (Nov 20, 2025)
  - Backend PDF filling fully implemented in `backend/routes/pdf_fill_routes.py`
  - Dynamic field flag manipulation for read-only fields (unlocks conditional fields)
  - Support for all field types: text, textarea, date, radio, checkbox (single & group)
  - Frontend "Download Filled PDF" button in `SchemaForm.tsx`
  - Uses form-kit system: `kitId` + `pdfUrl` → filled PDF bytes
  - Works with any form + schema pair (I-90 tested, future forms supported)
  - Tablet-friendly: download triggers browser's native download (works on mobile)
- [ ] **Thorough end-to-end testing** - Full form completion multiple times (Est: 4-6 hours)

### Legal/Compliance
- [ ] **Print paper waivers** - 20 copies of consent form (user understands tool is not legal advice)
- [ ] **Verify PII deletion** - Confirm all data clears on tab close/"clear form" button

### Hardware/Setup
- [ ] **Wait for hardware delivery** - 60 disposable earbuds + 2 lapel mics (ordered, arriving soon)
- [ ] **Test with actual tablet hardware** - Verify mic quality, print functionality, overall UX

## Nice to Have (Not Blocking)
- [ ] Multiple form support (can add forms on-site as needed)
- [ ] Digital save/download feature (print-only is fine for pilot)

## Estimated Timeline
- **Thursday**: Validation, logging, field logic fixes (6-8 hours)
- **Friday**: Disclaimer, printing, full testing (6-8 hours)  
- **Weekend/Monday**: Buffer for surprises
- **Target: Week of Nov 25**: ESC pilot ready

## Notes
- Already have: LLC, E&O insurance, cyber insurance ✅
- App already deletes PII on close ✅
- Live API version working smoothly ✅
- Cost per form: ~$5, selling at $20-50 ✅

## Confirmation & Logging Details
**What to log (anonymized):**
- Timestamp when each field was confirmed
- Field name/ID (not the actual data entered)
- Confirmation method (voice confirmation, button press, etc.)

**What NOT to log:**
- Actual user data (names, SSNs, A-numbers, addresses)
- Any PII that could identify the user

**Purpose:** Demonstrate your process was sound (user confirmed each entry) without creating PII liability