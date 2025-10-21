# API & Testing Guide

**Last Updated**: October 10, 2025  
**Purpose**: Gemini API best practices and essential testing procedures

---

## Gemini System Instructions (Dynamic Updates)

**Warmup Phase**: Minimal system instruction via initial config

- Simple standby message: "Standby for form details"
- Fast connection, low token cost

**Upgrade Phase**: Dynamic system instruction update via `send_client_content()`

- Send full context as `role="system"` with `turn_complete=False`
- Follows proper Gemini Live API patterns
- Cleaner than text-based context injection

**Instruction Structure**:

1. **Persona**: Agent name, role, characteristics
2. **Conversational Rules**: Ordered steps (one-time vs loops)
3. **Tool Specifications**: EXACTLY when to invoke (use distinct sentences)
4. **Guardrails**: What NOT to do (with specific examples)

**Config**: Templates in `backend/config.py`:

- `SYSTEM_INSTRUCTION`: Minimal standby
- `SYSTEM_INSTRUCTION`: Full form-filling rules
- `INITIAL_MESSAGE`: Greeting prompt

---

## Tool Best Practices

**Be Specific**: Include invocation conditions in description

**Example**:

```json
{
  "name": "update_form_fields",
  "description": "Update form fields. Invoke ONLY after user speaks and you have field IDs + values. Do not invoke if uncertain.",
  "parameters": {"updates": {"type": "object"}}
}
```

**get_form_status**: Tell AI to acknowledge user first ("One moment...") to cover latency

---

## Manual Testing (20 min essentials)

**Prerequisites**:
- Backend: `scripts/start_backend.sh` → http://localhost:8000/docs
- Frontend: `cd frontend && npm run dev` → http://localhost:5174
- Test page: http://localhost:5174/test-demo-new.html

**Essential Scenarios**:

1. **Connection**: Connect → Verify session_id
2. **Audio**: Record → Speak → Playback smooth
3. **Fields**: AI fills → Green outline + checkmark
4. **State**: Refresh → DOM restored from sessionStorage
5. **Barge-In**: Interrupt Gemini → TTS stops <50ms

**Common Issues**:
- No connection? Backend port 8000? CORS set?
- No audio? GOOGLE_API_KEY set? Check logs
- Fields not updating? Tool call errors in console

---

## VAD Tuning Lab

**Quick Start**:
1. `cd frontend && npm run build:bookmarklet`
2. `uvicorn backend.main:app --reload --port 8000`
3. `cd frontend && npx vite --port 5173`
4. Open: http://localhost:5173/vad-tuning-lab.html

**Usage**: Connect → Adjust params → Update Config → Pick scenario → Test → Review

**Target Metrics**:
- P95 Latency < 180ms
- Avg Latency < 150ms
- Hallucination Rate < 1%
- False Start Rate < 3%

**Quick Fixes**:
- AI talks over you? ↓ start_sensitivity to LOW, ↓ silence_duration to 200ms
- Noise triggers? ↑ start_sensitivity to MED/HIGH, ↑ silence_duration to 350ms
- AI cuts you off? ↑ end_sensitivity to MED/HIGH, ↑ silence_duration to 400ms

---

## Unit Tests

**File**: `backend/tests/unit/test_warmup_and_prefilled.py` (17 tests)

**Run**:
```bash
pytest backend/tests/unit/test_warmup_and_prefilled.py -v
pytest backend/tests/unit/test_warmup_and_prefilled.py --cov=backend.services
```

**Coverage**: Warmup, token optimization, pre-filled forms, stateless architecture

---

## Form Parser Tests

**Files**: `frontend/src/webParser/*.test.ts` (4 test files, 5 tests)

**Run**:

```bash
cd frontend
npm test -- --run
```

**Coverage**:

- Traditional forms (Drupal webforms, select dropdowns)
- JavaScript-rendered forms (React/Paylocity)
- Radio button grouping and option extraction
- Cookie consent filtering
- Label normalization

**Test Forms**:

- Seattle Municipal Court (traditional)
- PeaceHealth DAISY Award (Drupal)
- Cowlitz Family Health Center (React/Paylocity)

---

## Adding Demo Form Enhancements

For forms with JS-rendered controls (React/Angular) that don't expose options in the DOM:

**1. Create option lists** (if not using COMMON_OPTIONS):

```typescript
// In formEnhancements.ts
const MY_FORM_OPTIONS = {
  CUSTOM_FIELD: ['Option 1', 'Option 2', 'Option 3']
};
```

**2. Add form configuration**:

```typescript
// In FORM_ENHANCEMENTS array
{
  urlPattern: 'example.com/form/12345',
  fieldOptions: {
    'fieldId': COMMON_OPTIONS.YES_NO,
    'stateField': COMMON_OPTIONS.US_STATES,
    'customField': MY_FORM_OPTIONS.CUSTOM_FIELD
  },
  fieldConstraints: {
    'dateField': { min: '1920-01-01', format: 'MM/DD/YYYY' }
  }
}
```

**3. Test locally with URL override**:

```bash
cd frontend
npx tsx scripts/parse-form.ts "../example_webforms/my-form.html" \
  --url "https://example.com/form/12345" > ../outputs/my-form-parsed.json
```

**4. Verify enhancements applied**:

```bash
grep -A8 '"fieldId"' ../outputs/my-form-parsed.json
# Should show "options": ["Yes", "No"] for enhanced fields
```

**Available COMMON_OPTIONS**:

- `YES_NO`: ['Yes', 'No']
- `US_STATES`: All 50 US states
- `COUNTRIES`: Top 15 countries + 'Other'
- `SCHOOL_TYPES`: High School, College, Graduate School, etc.

**Notes**:

- Enhancements only apply when URL pattern matches
- Existing DOM-extracted options take precedence
- Works on live pages (bookmarklet gets real URL automatically)
- Works on saved pages (must pass `--url` parameter)

---

**Timelines**: Full suite 45-60min | Essential tests 20min | VAD tuning 30-45min
