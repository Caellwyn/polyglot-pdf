!!!DO NOT CHANGE THIS DOCUMENT!!!

# Implementation Tasks for Code Assistant

**Last Updated**: October 10, 2025  
**Purpose**: Technical task list for development work

---

## Phase 1: Critical Bug Fixes

### Task 1.1: VAD Self-Interruption
**Files**: `frontend/src/lib/audioManager.ts`, `backend/adapters/live_ai_gemini.py`, `backend/config.py`

**Step 1 - Add Diagnostics**:
- Client-side: Log VAD state changes with timestamps, audio levels, playback state (tag: `[VAD DIAGNOSTIC]`)
- Server-side: Log Gemini `serverContent.interrupted` events (tag: `[VAD DIAGNOSTIC]`)

**Step 2 - Fix Based on Findings**:
- If client-side issue: Increase ATTACK_TIME, RELEASE_TIME, TTS_BLEED_GUARD, MIN_SILENCE_DURATION
- If server-side issue: Change `start_of_speech_sensitivity` LOW→MEDIUM, increase `silence_duration_ms` 250→350
- Test with `vad-tuning-lab-modular.html`

**Success Criteria**:
- Model completes responses without self-interruption (test 5 sessions)
- User can still interrupt (barge-in works)
- P95 latency <180ms
- False positives <1%

---

### Task 1.2: Form Clear Bug
**Files**: `frontend/src/lib/webFormConnection.ts`, `frontend/src/lib/webFormState.ts`, `backend/services/form_filling_service.py`

**Debug**:
1. Add logging before/after clear: schema, session_id, field states
2. Verify schema reaches backend after clear
3. Test if manual "Rescan" fixes it

**Fix** (recommended approach):
- Clear DOM and client state
- Re-scan DOM for fresh schema
- Send upgrade message with new schema
- Update UI with success message

**Success Criteria**:
- Click "Clear Form" → all values cleared
- Speak new values → fields fill correctly
- Works 5/5 tests

---

### Task 1.3: Dropdown Language Mismatch
**Files**: `frontend/src/lib/formParser.ts`, `backend/config.py`, `backend/services/form_filling_service.py`

**Problem**: Starting in non-English language with English dropdown as first field breaks entire session

**Fix Part 1 - Schema**:
- Parse dropdown options as structured objects: `{label: "display text", value: "form_value"}`
- Include currently selected value
- Send both label and value to backend

**Fix Part 2 - Prompt** (in `backend/config.py` ''MESSAGE_TEMPLATE):
Add language handling rules:
- "Form should be filled in: {form_language}"
- "User may speak ANY language - auto-detect and translate"
- "Dropdown options may be in different language than form language"
- "Always use 'value' attribute for dropdowns, never display label"
- "If first field has language mismatch, don't get confused about form language"

**Fix Part 3 - Detection**:
- Detect if first field has language mismatch
- Log warning server-side

**Test Matrix** (test each 3x):
- English form + English user + English dropdown ✅
- English form + Spanish user + English dropdown (should work)
- Chinese form + English user + English dropdown (currently fails - fix this)
- Chinese form + Chinese user + English dropdown (currently fails - fix this)
- Chinese form + English user + text field (already works)

**Success Criteria**:
- All language combinations work
- Dropdown uses `value` attribute
- First-field language mismatch doesn't break session

---

## Phase 2: Billing Infrastructure

### Task 2.1: Usage Logging
**Files**: `backend/services/usage_logger.py` (new), `backend/config.py`, `backend/routes/websocket_routes.py`, `backend/adapters/live_ai_gemini.py`

**Create UsageLogger Service**:

Methods:
- `start_session(session_id, customer_id, form_id)` - Log session start
- `update_session(session_id, **kwargs)` - Update during execution
- `complete_session(session_id, customer_id, status, tokens_input, tokens_output, duration_seconds, fields_filled, fields_total, billable)`

**Log Structure** (per session):
```python
{
    "session_id": str,
    "customer_id": str,
    "form_id": str,
    "started_at": ISO timestamp,
    "completed_at": ISO timestamp,
    "duration_seconds": int,
    "status": "completed" | "abandoned" | "error",
    "billable": bool,  # True only if completed + >50% fields filled
    "tokens_input": int,
    "tokens_output": int,
    "tokens_total": int,
    "token_cap": 50000,
    "fields_filled": int,
    "fields_total": int,
    "detected_language": str,
    "form_language": str,
    "cost_estimate": float,
    "browser": str,
    "mobile": bool,
    "form_domain": str
}
```

**NEVER log**: Field values, PHI, audio content

**Token Cap Enforcement**:
- Set `MAX_TOKENS_PER_SESSION = 50000` in `config.py`
- Track running total from Gemini `response.usage_metadata`
- Check after each Gemini response
- If exceeded:
  - Log error with session_id and total
  - Send message to user: "Session too long, please submit"
  - Mark session as over-limit (still billable)
  - Close gracefully

**Cost Calculation**:
```python
input_cost = tokens_input * 0.000003
output_cost = tokens_output * 0.000012
total_cost = input_cost + output_cost
```

**Integration Points**:
- WebSocket accept → `start_session()`
- Tool calls processed → `update_session()`
- WebSocket close → `complete_session()`

**Storage**: Cloud Logging (structured logs)

**Success Criteria**:
- All sessions logged with complete metadata
- Token cap enforced at 50k
- No PHI in logs (grep to verify)
- Cost estimates accurate

---

### Task 2.2: Domain Whitelist
**Files**: `backend/config.py`, `backend/middleware/domain_validator.py` (new), `backend/main.py`, `backend/routes/websocket_routes.py`

**Create DOMAIN_WHITELIST in config.py**:
```python
DOMAIN_WHITELIST = {
    "localhost": {
        "customer_id": "dev_local",
        "name": "Development",
        "plan": "unlimited",
        "billable": False,
        "rate_per_completion": 0.00,
        "max_concurrent_sessions": 999,
        "max_completions_per_day": 999999,
        "max_completions_per_month": 999999
    },
    "demo.clinic-a.com": {
        "customer_id": "clinic_001",
        "name": "Pilot Clinic A",
        "plan": "professional",
        "billable": True,
        "rate_per_completion": 0.75,
        "max_concurrent_sessions": 10,
        "max_completions_per_day": 500,
        "max_completions_per_month": 10000
    }
    # Add more as needed
}
```

**Create domain_validator.py**:

Functions needed:
- `extract_domain(origin: str) -> str` - Parse domain from Origin header
- `get_customer_from_origin(origin: str) -> dict` - Lookup in whitelist
- `validate_websocket_connection(websocket) -> bool` - Validate before accepting

**Validation Flow**:
1. Extract domain from `websocket.headers.get("origin")`
2. Look up in whitelist
3. If not found:
   - Send error: `{"type": "error", "error_code": "domain_not_authorized", "message": "Domain not authorized. Contact support@..."}`
   - Close WebSocket
   - Return False
4. If found:
   - Attach to `websocket.state.customer_id`, `websocket.state.billable`, etc.
   - Return True

**Update CORS in main.py**:
- Build `allowed_origins` list from whitelist domains
- For localhost: Allow `http://localhost:5173`, `http://localhost:5174`, `http://localhost:8000`
- For production: `https://{domain}` only
- Replace wildcard `"*"` with specific list

**Integration**:
- In WebSocket handler: Call `validate_websocket_connection()` BEFORE accepting
- Use `websocket.state.customer_id` in all logging

**Success Criteria**:
- Whitelisted domains connect
- Non-whitelisted domains get friendly error
- customer_id appears in all session logs
- CORS only allows whitelisted origins

---

### Task 2.3: Billing Dashboard
**Files**: `backend/routes/billing_routes.py` (new), `frontend/src/pages/BillingDashboard.tsx` (new), `backend/main.py`, `frontend/src/main.tsx`

**Backend API**:

Create `billing_routes.py`:

```python
@router.get("/api/billing/usage/{customer_id}")
async def get_usage(
    customer_id: str,
    start_date: date = None,  # Defaults to first of current month
    end_date: date = None      # Defaults to today
):
    # Query Cloud Logging for sessions where:
    # - jsonPayload.customer_id == customer_id
    # - jsonPayload.event == "session_complete"
    # - timestamp between start_date and end_date
    
    # Return:
    {
        "customer_id": str,
        "period": {"start": str, "end": str},
        "summary": {
            "total_completions": int,
            "total_cost": float,
            "rate_per_completion": float
        },
        "daily_breakdown": [
            {"date": str, "completions": int, "cost": float},
            ...
        ],
        "top_forms": [
            {"form_id": str, "count": int},
            ...
        ]
    }

@router.get("/api/billing/export/{customer_id}")
async def export_csv(customer_id: str, start_date: date = None, end_date: date = None):
    # Same query as above
    # Return CSV: Date,Session ID,Form ID,Duration,Tokens,Cost,Billable
    # Content-Type: text/csv
```

Query helper (pseudo-code):
```python
from google.cloud import logging

def query_usage(customer_id: str, start_date: date, end_date: date):
    client = logging.Client()
    logger = client.logger("voice-form-filler-usage")
    
    filter_str = (
        f'jsonPayload.customer_id="{customer_id}" AND '
        f'jsonPayload.event="session_complete" AND '
        f'timestamp>="{start_date}" AND timestamp<="{end_date}"'
    )
    
    entries = logger.list_entries(filter_=filter_str)
    return [entry.payload for entry in entries]
```

**Frontend Dashboard**:

Create `BillingDashboard.tsx`:
- Route: `/billing?customer_id=clinic_001`
- Fetch usage data from API on mount
- Display:
  - 3 summary cards (completions, cost, rate)
  - Line chart showing daily completions (use Recharts)
  - Table of top 5 forms by usage
  - Export CSV button
- Handle loading and error states

**Register Routes**:
- Backend: Add `app.include_router(billing_routes.router)` in `main.py`
- Frontend: Add `<Route path="/billing" element={<BillingDashboard />} />` in `main.tsx`

**Success Criteria**:
- Dashboard loads at `/billing?customer_id=...`
- Summary cards accurate
- Graph displays correctly
- CSV export works
- Mobile-friendly

---

## Phase 3: Production Hardening

### Task 3.1: Error Handling
**Files**: `frontend/src/lib/errors.ts` (new), `frontend/src/bookmarklet/overlay.ts`, `backend/routes/websocket_routes.py`

**Create Error Catalog** (errors.ts):
```typescript
enum ErrorCode {
    DOMAIN_NOT_AUTHORIZED = "domain_not_authorized",
    SESSION_LIMIT_REACHED = "session_limit_reached",
    USAGE_QUOTA_EXCEEDED = "usage_quota_exceeded",
    DAILY_LIMIT_REACHED = "daily_limit_reached",
    MONTHLY_LIMIT_REACHED = "monthly_limit_reached",
    NO_FILLABLE_FIELDS = "no_fillable_fields",
    FORM_TOO_LARGE = "form_too_large",
    GEMINI_API_ERROR = "gemini_api_error",
    TOKEN_CAP_EXCEEDED = "token_cap_exceeded",
    MICROPHONE_PERMISSION_DENIED = "microphone_permission_denied",
    CSP_VIOLATION = "csp_violation"
}

const ERROR_MESSAGES: Record<ErrorCode, string> = {
    // Map each code to user-friendly message
}

function getErrorMessage(code: ErrorCode): string
```

**Display Errors**:
- In overlay (not browser alerts)
- Show error message from catalog
- Log to console with full context
- Update status indicator to "Error"

**Backend Error Responses**:
```python
async def send_error(websocket: WebSocket, error_code: str, details: str = None):
    await websocket.send_json({
        "type": "error",
        "error_code": error_code,
        "details": details  # Optional, for debugging
    })
```

**Success Criteria**:
- All error codes have friendly messages
- Errors displayed in UI (not alerts)
- All errors logged with context

---

### Task 3.2: Rate Limiting
**Files**: `backend/services/rate_limiter.py` (new), `backend/routes/websocket_routes.py`

**Create RateLimiter Service**:

```python
class RateLimiter:
    def __init__(self):
        self.active_sessions: Dict[str, int] = {}  # customer_id -> count
        self.daily_completions: Dict[str, Dict[str, int]] = {}  # customer_id -> {date -> count}
        self.monthly_completions: Dict[str, Dict[str, int]] = {}  # customer_id -> {month -> count}
    
    def check_concurrent_limit(customer_id: str, max_concurrent: int) -> bool
    def increment_active_sessions(customer_id: str)
    def decrement_active_sessions(customer_id: str)
    
    def check_daily_limit(customer_id: str, max_per_day: int) -> bool
    def increment_daily_completions(customer_id: str)
    
    def check_monthly_limit(customer_id: str, max_per_month: int) -> bool
    def increment_monthly_completions(customer_id: str)
```

**Integration**:
- On WebSocket connect: Check all limits before accepting
- On WebSocket disconnect: Decrement active sessions
- On session complete (if billable): Increment daily and monthly counters

**Error Responses**:
- If limit exceeded: Send appropriate error code, close connection

**Success Criteria**:
- Limits enforced correctly
- Counters reset (daily at midnight, monthly on 1st)
- Friendly error messages

---

### Task 3.3: Monitoring
**Files**: `backend/services/metrics.py` (new), `backend/routes/websocket_routes.py`, `backend/main.py`

**Create MetricsCollector Service**:

```python
class MetricsCollector:
    def record_active_sessions(count: int)
    def record_session_completed(customer_id: str)
    def record_session_abandoned(customer_id: str, reason: str)
    def record_error(error_code: str)
    def record_gemini_cost(cost: float)
    def record_token_usage(tokens: int)
    def record_latency(latency_ms: float, operation: str)
```

Send to Cloud Monitoring (custom metrics):
- `custom.googleapis.com/vff/sessions/active`
- `custom.googleapis.com/vff/sessions/completed`
- `custom.googleapis.com/vff/sessions/error_rate`
- `custom.googleapis.com/vff/api/gemini_cost`
- `custom.googleapis.com/vff/api/tokens`
- `custom.googleapis.com/vff/latency`

**Integration Points**:
- WebSocket connect/disconnect → active sessions
- Session complete → completion + cost + tokens
- Session error → error counter
- Operations → latency

**Success Criteria**:
- Metrics appear in Cloud Monitoring console
- Metrics accurate (compare to logs)

---

## Phase 4: Security

### Task 4.1: XSS Prevention Audit
**Files**: All frontend files, `frontend/src/lib/sanitize.ts` (new)

**Create sanitize.ts**:
```typescript
function escapeHtml(text: string): string {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
```

**Audit Checklist**:
- [ ] Find all uses of `.innerHTML` - replace with `textContent` or `escapeHtml()`
- [ ] All user input sanitized before display
- [ ] All AI responses sanitized before display
- [ ] No `eval()` or `new Function()` (except CSP detection)
- [ ] No field values in logs (only IDs)
- [ ] sessionStorage cleared on tab close
- [ ] CSP detection working

**Success Criteria**:
- No XSS vulnerabilities
- All content sanitized
- Security patterns followed

---

## Phase 5: Deferred Features (Optional)

### Task 5.1: State Restoration
**Files**: `frontend/src/lib/webFormConnection.ts`, `frontend/src/bookmarklet/overlay.ts`, `backend/services/form_filling_service.py`

**Reconnection Logic**:
- Detect WebSocket disconnect event
- Attempt reconnection with exponential backoff (1s, 2s, 4s, 8s, 16s)
- Max 3-5 attempts
- On reconnect: Send schema + current field values from sessionStorage
- Backend: Create new session with existing state

**User Feedback**:
- Show "Reconnecting..." during attempts
- Show "Connected" on success
- Show "Connection lost" after max attempts
- Offer manual retry button

---

### Task 5.2: Multi-Page Forms
**Files**: `frontend/src/lib/multiPageNavigator.ts` (new), `frontend/src/lib/formParser.ts`, `frontend/src/lib/webFormConnection.ts`

**Detection**:
- Look for "Next", "Continue", "Previous" buttons
- Identify page indicators (e.g., "Step 1 of 3")

**Navigation**:
- Fill all fields on current page
- Confirm with user: "Ready for next page?"
- Click "Next" button programmatically
- Use MutationObserver to detect new page load
- Re-scan for new fields
- Continue filling

**State Management**:
- Track: current_page, total_pages
- Store partial progress in sessionStorage
- Handle "Previous" navigation

---

### Task 5.3: SPA Auto-Detection
**Files**: `frontend/src/lib/formParser.ts`, `frontend/src/bookmarklet/overlay.ts`

**Implementation**:
- Create MutationObserver watching form container
- Debounce 1 second to avoid noise
- Detect significant changes (5+ fields added/removed)
- Show notification: "Form changed. Click Rescan to update."
- Don't auto-rescan (could interrupt user)

**Schema Diffing**:
- Compare old schema vs new schema
- Preserve values for unchanged fields
- Only prompt for new fields

---

### Task 5.4: Enhanced UI
**Files**: Various in `frontend/src/bookmarklet/`

**Options** (implement based on feedback):
- Audio waveform visualization during recording
- Real-time transcript display (user speech + AI response)
- Field-by-field confirmation with undo
- Latency metrics (developer mode)
- Conversation history panel

---

## General Implementation Notes

**Security Patterns** (always follow):
- NEVER use `.innerHTML` with user/AI content
- ALWAYS use `textContent` or `escapeHtml()`
- NEVER log field values (only IDs, counts, timings)
- NEVER store PHI (sessionStorage for IDs only)
- ALWAYS detect CSP, show error (never bypass)
- ALWAYS use exponential backoff (max 3 attempts)

**Logging Best Practices**:
- Log metadata only: `{fieldId, fieldType, filled: boolean, timestamp}`
- Use structured logging (JSON)
- Tag for easy filtering: `[VAD DIAGNOSTIC]`, `[ERROR]`, etc.
- Include context but never sensitive data

**Testing**:
- Test on localhost first
- Test on demo sites before pilot
- Manual testing required for VAD tuning
- Automated tests for schema parsing, validation

**File Naming**:
- Services: `snake_case.py` (e.g., `usage_logger.py`)
- React components: `PascalCase.tsx` (e.g., `BillingDashboard.tsx`)
- Utilities: `camelCase.ts` (e.g., `sanitize.ts`)

---

## Quick Reference

**Token Cap**: 50,000 tokens per session (hard limit)

**Field Types Supported**: text, textarea, email, tel, url, password, number, date, time, datetime-local, checkbox, radio, select, button, signature

**Billable Session**: Status = completed AND fields_filled > 50% of fields_required

**Domain Whitelist Location**: `backend/config.py` → `DOMAIN_WHITELIST`

**VAD Tuning Lab**: `frontend/vad-tuning-lab-modular.html`

**Cloud Logging Filter** (usage queries):
```
jsonPayload.customer_id="clinic_001" AND 
jsonPayload.event="session_complete" AND 
timestamp>="2025-10-01"
```

---

**Start with Phase 1, Task 1.1 (VAD diagnostics) - it's blocking other work and easiest to validate.**
