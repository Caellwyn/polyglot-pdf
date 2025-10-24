# Voice Form Filler - Logging Overhaul Plan

**Last Updated**: October 24, 2025
**Purpose**: Production-ready logging for compliance, token tracking, and performance metrics
**Target**: Cloud Logging → BigQuery pipeline

---

## 📊 Progress Update - October 24, 2025

### ✅ Completed (Phase 1 - Token Tracking Infrastructure)

**Backend Infrastructure**:
- ✅ Created `backend/utils/structured_logger.py` - Production JSON logger for Cloud Run/BigQuery
- ✅ Created `backend/utils/dev_file_logger.py` - Development logger with daily `.jsonl` rotation
- ✅ Created `backend/utils/log_schemas.py` - TypedDict event schemas
- ✅ Removed legacy logging utilities (`dev_logger.py`, `tool_call_logger.py`)
- ✅ Updated all backend services to use new logging

**Token Tracking (PRIORITY #1)**:
- ✅ Implemented real-time token extraction from Gemini API `usage_metadata`
- ✅ **TEXT vs AUDIO modality breakdown** using `prompt_tokens_details` and `response_tokens_details`
- ✅ Cost calculation with accurate pricing (audio 6x more expensive than text)
- ✅ Cumulative session tracking (tokens and costs)
- ✅ Hardened against `None` values from API
- ✅ Pattern matching using `types.ModalityTokenCount`

**Pricing Configuration**:
```python
GEMINI_PRICING = {
    "text_input": $0.0000005,   # $0.50 per million
    "audio_input": $0.000003,   # $3.00 per million (6x!)
    "text_output": $0.000002,   # $2.00 per million
    "audio_output": $0.000012,  # $12.00 per million (6x!)
}
```

**Development Tooling**:
- ✅ Daily log rotation: `backend/logs/gemini_YYYY-MM-DD.jsonl`
- ✅ JSON Lines format for easy DataFrame analysis
- ✅ Environment flag: `VFF_DEV_LOGGING=true`
- ✅ Errors always output to terminal

**Key Insights**:
- Audio output tokens dominate costs (often 80%+ of total)
- Real-time cost visibility enables optimization decisions
- API can return `None` for token counts - defensive coding required

### 🚧 In Progress / Next Steps

**Phase 2 - Session Lifecycle** (NEXT):
- [ ] Generate `form_session_id` on first blur/connect
- [ ] Log `ws_connect`, `ws_disconnect`, `session_start`, `session_complete`
- [ ] Session duration and completion tracking

**Phase 3 - Frontend Logger**:
- [ ] Client-side logger in sessionStorage (PHI allowed - stays local)
- [ ] Field change tracking with old/new values
- [ ] Sanitized event batching to backend (NO values)
- [ ] Manual field update detection and logging

**Phase 4 - Remaining Backend**:
- [ ] Field interaction logging (`field_voice_attempt`, validation results)
- [ ] Error categorization and tracking
- [ ] Remove remaining console.log spam (~268 frontend instances)

**Phase 5 - BigQuery Integration**:
- [ ] Set up Cloud Logging → BigQuery sink
- [ ] Create datasets and tables
- [ ] Validate PHI-free logging with queries

**Phase 6 - Compliance & Audit** (Later):
- [ ] 6-year audit trail
- [ ] IP hashing
- [ ] Separate audit dataset

### 📝 Lessons Learned

1. **API Documentation Gaps**: Official docs had camelCase field names, Python SDK uses snake_case
2. **None Handling Critical**: API returns `None` for some token counts in edge cases
3. **Modality Breakdown Essential**: Audio costs 6x more - need separate tracking
4. **Development Logs Valuable**: Full Gemini message logs critical for debugging

---

## ⚠️ CRITICAL COMPLIANCE RULE

**NEVER LOG: Field values, PII, PHI, user input, audio transcripts, names, addresses, phone numbers, dates of birth, or ANY identifiable information**

**ALWAYS LOG: Field IDs, field types, counts, timestamps, interaction metadata, token usage, error codes**

Violations risk HIPAA fines and legal liability.

---

## Project Goals

### 1. Token Usage Tracking (PRIORITY)
**Problem**: $0.20 for 9-12 fields suggests inefficiency  
**Solution**: Track all token sources via Gemini `response.usage_metadata`

**Track**:
- Tokens per section
- Tokens per form session  
- Tokens per API call type (system instruction, audio, tool response, text message)
- Cumulative totals
- Cost estimates

### 2. Session & Performance Metrics
- Session duration (start → complete/abandon)
- Completion rates by section/form
- Voice vs manual fill ratios
- Field interaction patterns

### 3. Error Tracking & Debugging
- Categorized errors (validation, network, AI, tool, timeout)
- Error frequency and patterns
- Recovery success rates

### 4. Compliance Readiness (Phase 2)
- Audit trail schema defined
- HIPAA-compliant logging
- 6-year retention for audit events

---

## Architecture

```
Frontend Events → WebSocket → Backend Aggregator → Cloud Logging → BigQuery
                       ↓
            Backend System Events
```

**Storage**:
- Cloud Logging: 30 days (raw logs)
- BigQuery `voice_form_filler_logs`: 90 days (detailed events)
- BigQuery `voice_form_filler_audit`: 6 years (compliance)
- Monthly aggregates: 2 years

---

## ID Hierarchy

```typescript
{
  client_id: string;        // "demo" (from frontend config)
  form_id: string;          // "adult-intake-v2" (from URL path)
  form_version: string;     // "2.1.3" (from schema)
  form_session_id: string;  // UUID (persists across sections/refreshes)
  ws_session_id: string;    // UUID (per section/reconnect, backend-assigned)
}
```

### ID Lifecycle

**`form_session_id`** (Frontend):
- Generated: First `blur` event OR `connect` click (filters tourists)
- Storage: sessionStorage key `vff_form_session_id`
- Lifespan: Until tab close
- Survives: Page refresh, section switches

**`ws_session_id`** (Backend):
- Generated: Each WebSocket connection
- Lifespan: Until disconnect/section-complete
- Relationship: Many per `form_session_id`

**`client_id`** (Config):
- Source: Frontend config (hardcoded "demo")
- Future: Per-deployment environment variable

**`form_id`** (URL):
- Source: URL path `/forms/adult-intake-v2`
- Versioning: Extract from schema `form_version` field

**Session End**:
- Try `beforeunload` event → `navigator.sendBeacon('/api/log/session-end')`
- Fallback: Sessions >24h without completion = `"abandoned"`

---

## Base Event Schema

```typescript
interface BaseLogEvent {
  // Identifiers (REQUIRED)
  client_id: string;
  form_id: string;
  form_version: string;
  form_session_id: string;
  ws_session_id?: string;  // Optional for frontend-only events
  
  // Event metadata (REQUIRED)
  event_type: string;
  timestamp: string;  // ISO 8601
  source: "frontend" | "backend";
  
  // Context (OPTIONAL)
  section_number?: number;
  section_label?: string;
  field_id?: string;  // NO VALUES
  severity?: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";
  
  // Event-specific data
  metadata: Record<string, any>;
}
```

---

## Event Types

### Session Events
- `session_start` - First blur/connect (generates form_session_id)
- `session_pause` - User pauses
- `session_resume` - User resumes
- `session_complete` - All sections done
- `session_submit` - Form submitted
- `session_abandon` - Tab close OR >24h inactive
- `session_timeout` - Backend idle timeout (300s)

### WebSocket Events
- `ws_connect` - Connection established
- `ws_disconnect` - Closed with reason
- `ws_reconnect` - After network failure
- `ws_error` - Connection error

### Field Events
- `field_blur` - Focus lost (completion)
- `field_voice_attempt` - AI tool call for field
- `field_voice_success` - Voice fill confirmed
- `field_manual_edit` - User typed directly
- `field_correction` - User fixed AI value
- `field_validation_error` - Constraint violation

### Section Events
- `section_start` - Section begins
- `section_complete` - Section finished
- `section_switch` - Manual navigation

### Token Events
- `gemini_api_response` - API response with token counts
- `gemini_error` - API error

### Tool Events
- `tool_call` - Gemini invoked tool
- `tool_response` - Execution result

### Error Events
- `error_validation` - Field constraint failed
- `error_network` - Connection issue
- `error_ai` - Gemini API error
- `error_tool` - Tool execution failed
- `error_timeout` - Operation timeout

### Audit Events (Phase 2)
- `audit_form_start` - User started form
- `audit_field_update` - Field updated (no value)
- `audit_form_submit` - Form submitted

---

## Phase 1: Token Tracking (PRIORITY)

### Token Event Schema

```typescript
{
  event_type: "gemini_api_response",
  source: "backend",
  // ... standard fields
  metadata: {
    // From response.usage_metadata
    prompt_token_count: number,
    candidates_token_count: number,
    total_token_count: number,
    
    // Context
    api_call_type: "audio_stream" | "text_message" | "tool_response" | "session_start",
    tool_name?: string,
    
    // Sizes (for debugging)
    system_instruction_size?: number,  // Characters
    schema_size?: number,
    tool_result_size?: number,
    
    // Cumulative
    session_tokens_so_far: number,
    form_tokens_so_far: number,
    
    // Performance
    latency_ms: number,
    cost_estimate_usd: number
  }
}
```

### Tracking Points

Log tokens after EVERY Gemini API call:
1. `start_session()` - System instruction sent
2. `send_realtime_input()` - Audio chunks
3. `handle_tool_call()` - Tool response
4. `send_client_content()` - Text messages

### Cumulative Tracking

Backend maintains:
- `session_tokens`: Counter in `FormFillingService`
- `form_tokens`: Passed in handshake, returned to frontend

Frontend:
- Stores `vff_form_tokens_total` in sessionStorage
- Passes to backend on reconnect

---

## Phase 2: Session Lifecycle

### Session Start
```typescript
{
  event_type: "session_start",
  source: "frontend",
  metadata: {
    trigger: "blur" | "connect",
    form_type: "adult_intake",
    total_sections: 8,
    total_fields: 174,
    device_type: "mobile" | "desktop" | "tablet",
    browser: string,
    language: "es-MX"  // User's voice language
  }
}
```

### Section Complete
```typescript
{
  event_type: "section_complete",
  source: "frontend",
  section_number: 1,
  metadata: {
    duration_seconds: 187,
    fields_total: 12,
    fields_voice: 10,
    fields_manual: 2,
    fields_skipped: 0,
    corrections: 1,
    validation_errors: 2
  }
}
```

### Session Complete
```typescript
{
  event_type: "session_complete",
  source: "frontend",
  metadata: {
    duration_seconds: 1635,
    sections_completed: 8,
    fields_total: 174,
    fields_voice: 140,
    fields_manual: 34,
    total_corrections: 8,
    voice_to_manual_switches: 2
  }
}
```

---

## Phase 3: Field Interactions

### Field Voice Attempt
```typescript
{
  event_type: "field_voice_attempt",
  source: "backend",
  field_id: "dateOfBirth",
  metadata: {
    attempt_number: 1,
    tool_name: "update_form_fields",
    validation_passed: false,
    validation_error: "Invalid date | min=1900-01-01"
  }
}
```

### Field Manual Edit
```typescript
{
  event_type: "field_manual_edit",
  source: "frontend",
  field_id: "dateOfBirth",
  metadata: {
    previously_filled_by: "voice" | null,
    is_correction: true
  }
}
```

### Field Blur
```typescript
{
  event_type: "field_blur",
  source: "frontend",
  field_id: "dateOfBirth",
  metadata: {
    filled: true,
    fill_method: "voice" | "manual",
    attempts: 2,
    time_spent_seconds: 30
  }
}
```

---

## Phase 4: Error Tracking

### Error Schema
```typescript
{
  event_type: "error_*",
  source: "frontend" | "backend",
  severity: "WARNING" | "ERROR" | "CRITICAL",
  metadata: {
    error_message: string,
    error_code?: string,
    context: {
      field_id?: string,
      section_number?: number,
      tool_name?: string
    },
    stack_trace?: string,  // Backend only
    recoverable: boolean,
    recovery_action?: "retry" | "skip" | "abort"
  }
}
```

### Error Categories
- **Validation**: Field constraints violated
- **Network**: WebSocket/HTTP failures
- **AI**: Gemini API errors (503, 429, hallucinations)
- **Tool**: Execution failures, field not found
- **Timeout**: Session idle, API request, reconnection

---

## Phase 5: Compliance & Audit

### Audit Event Schema
```typescript
{
  event_type: "audit_*",
  source: "backend",
  metadata: {
    actor: "system" | "user",
    action: string,
    resource: string,  // field_id, form_id
    ip_address_hash: string,  // SHA256(ip + salt)
    user_agent: string,
    result: "success" | "failure",
    failure_reason?: string
  }
}
```

### Audit Events
- `audit_form_start` - Session begins
- `audit_field_update` - Field modified (no value)
- `audit_form_submit` - Form submitted

### Retention
- Audit logs: Separate BigQuery dataset, 6-year retention (HIPAA)
- IP hashing: SHA256 with salt (privacy + traceability)

---

## Phase 6: Performance Metrics

### Duration Tracking
- Field-level: `field_blur.metadata.time_spent_seconds`
- Section-level: `section_complete.metadata.duration_seconds`
- Session-level: `session_complete.metadata.duration_seconds`

### Voice vs Manual
- Per field: `field_blur.metadata.fill_method`
- Per section: `section_complete.metadata.{fields_voice, fields_manual}`
- Per session: `session_complete.metadata.voice_completion_rate`

### Language & Accessibility
```typescript
{
  event_type: "session_start",
  metadata: {
    voice_language: "es-MX",
    form_language: "en-US",
    translation_active: true
  }
}
```

### Frustration Signals
```typescript
{
  event_type: "frustration_signal",
  field_id: "householdIncome",
  metadata: {
    signal_type: "rapid_corrections" | "voice_to_manual_switch" | "field_abandoned",
    attempts: 5,
    time_spent_seconds: 120,
    eventually_filled: false
  }
}
```

---

## Implementation Checklist

### Step 1: Infrastructure Setup
- [ ] Enable Cloud Logging API
- [ ] Create BigQuery dataset: `voice_form_filler_logs`
- [ ] Create tables: `session_events`, `field_interactions`, `token_usage`, `errors`
- [ ] Configure Log Sink: Cloud Logging → BigQuery
- [ ] Set retention: 30d (Cloud Logging), 90d (BigQuery raw), 2yr (aggregates)

### Step 2: Remove Legacy Logging
- [x] Backend: Remove all `print()`, emoji logs, verbose debug ✅ Oct 24
- [ ] Frontend: Remove console.log spam (~268 instances)
- [ ] Verify: Clean console output

### Step 3: Backend Logger
- [x] Create `backend/utils/structured_logger.py`: Structured JSON logger ✅ Oct 24
- [x] Create `backend/utils/log_schemas.py`: TypedDict definitions ✅ Oct 24
- [x] Create `backend/utils/dev_file_logger.py`: Development file logger ✅ Oct 24
- [ ] Initialize in `main.py`: Single instance via dependency injection
- [x] Update services: Remove legacy logs, add new logging ✅ Oct 24

### Step 4: Token Tracking (PRIORITY) ✅ COMPLETED Oct 24
- [x] Add session token counters to `LiveAIGemini` adapter ✅ Oct 24
- [x] Extract `usage_metadata` after EVERY Gemini API response ✅ Oct 24
- [x] **Modality breakdown**: TEXT vs AUDIO tokens from `*_tokens_details` ✅ Oct 24
- [x] Include: prompt/response/total tokens, modality breakdown, cumulative, cost ✅ Oct 24
- [x] Cost calculation with accurate pricing (audio 6x text) ✅ Oct 24
- [x] Harden against `None` values from API ✅ Oct 24
- [ ] Frontend: Store `vff_form_tokens_total` in sessionStorage, pass in handshake

### Step 5: Session Lifecycle
- [ ] Frontend: Generate `form_session_id` on first blur/connect
- [ ] Store in sessionStorage: `vff_form_session_id`
- [ ] Log: `session_start`, `session_pause`, `session_resume`, `session_complete`, `session_abandon`
- [ ] Backend: Accept `form_session_id` in handshake, include in all events
- [ ] Log WebSocket events: `ws_connect`, `ws_disconnect`, `ws_error`, `ws_timeout`

### Step 6: Field Interactions
- [ ] Backend: Log `field_voice_attempt` on tool calls (include validation result)
- [ ] Frontend: Detect manual edits, log `field_manual_edit` if after voice fill
- [ ] Frontend: Log `field_blur` with fill_method, attempts, duration

### Step 7: Section Navigation
- [ ] Frontend: Log `section_start`, `section_complete`, `section_switch`
- [ ] Include: duration, field counts, corrections
- [ ] Backend: Accept section context in handshake

### Step 8: Error Tracking
- [ ] Backend: Catch all exceptions, log `error_*` events
- [ ] Categories: validation, AI, tool, timeout
- [ ] Include: message, code, context, severity, recoverable
- [ ] Frontend: Log `error_network` on disconnect/reconnect failures

### Step 9: Frontend Logger
- [ ] Create `frontend/src/utils/logger.ts`: Event emitter with batching
- [ ] Send via WebSocket: `{type: "log_events", events: [...]}`
- [ ] Batch: Every 5s or 10 events queued
- [ ] Fallback: POST `/api/log` if WebSocket closed
- [ ] Update `webFormConnection.ts`: Initialize logger, add logging calls

### Step 10: Backend Log Receiver
- [ ] Listen for `{type: "log_events"}` WebSocket message
- [ ] Validate structure
- [ ] Enrich with `ws_session_id`
- [ ] Emit to Cloud Logging (stdout JSON)

### Step 11: Compliance (Phase 2)
- [ ] Create `log_audit_event()` function
- [ ] Separate dataset: `voice_form_filler_audit`, 6-year retention
- [ ] Log: `audit_form_start`, `audit_field_update`, `audit_form_submit`
- [ ] Hash IP addresses: SHA256(ip + salt)

### Step 12: Testing & Validation
- [ ] Complete a section, verify token events in BigQuery
- [ ] Check cumulative totals match
- [ ] Compare with Vertex AI billing
- [ ] Test session lifecycle: start, refresh, complete
- [ ] Test field interactions: voice fill, manual edit, blur
- [ ] Test error logging: validation, disconnect
- [ ] **CRITICAL**: Search BigQuery for field values - MUST return zero results

---

## Configuration

### Frontend (`frontend/src/config.ts`)
```typescript
export const LOG_CONFIG = {
  client_id: "demo",
  batch_interval_ms: 5000,
  batch_size: 10,
  enable_console_logs: false  // Production
};
```

### Backend (`backend/config.py`)
```python
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "json"
BIGQUERY_PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
BIGQUERY_DATASET_ID = "voice_form_filler_logs"
BIGQUERY_AUDIT_DATASET_ID = "voice_form_filler_audit"

GEMINI_PRICING = {
    "prompt_tokens": 0.000001875,   # Gemini 2.0 Flash
    "candidate_tokens": 0.0000075,
}
```

---

## BigQuery Example Queries

### Token Usage Per Section
```sql
SELECT 
  section_number,
  SUM(JSON_VALUE(metadata, '$.total_token_count')) as total_tokens,
  COUNT(*) as api_calls
FROM `voice_form_filler_logs.session_events`
WHERE event_type = 'gemini_api_response'
GROUP BY section_number
ORDER BY section_number;
```

### Most Expensive Sessions
```sql
SELECT
  form_session_id,
  MAX(CAST(JSON_VALUE(metadata, '$.form_tokens_so_far') AS INT64)) as total_tokens,
  MAX(CAST(JSON_VALUE(metadata, '$.cost_estimate_usd') AS FLOAT64)) as cost_usd
FROM `voice_form_filler_logs.session_events`
WHERE event_type = 'gemini_api_response'
GROUP BY form_session_id
ORDER BY total_tokens DESC
LIMIT 20;
```

### Completion Rates
```sql
SELECT
  COUNT(DISTINCT CASE WHEN event_type = 'session_start' THEN form_session_id END) as started,
  COUNT(DISTINCT CASE WHEN event_type = 'session_complete' THEN form_session_id END) as completed,
  SAFE_DIVIDE(
    COUNT(DISTINCT CASE WHEN event_type = 'session_complete' THEN form_session_id END),
    COUNT(DISTINCT CASE WHEN event_type = 'session_start' THEN form_session_id END)
  ) as completion_rate
FROM `voice_form_filler_logs.session_events`;
```

---

## Success Criteria

### Token Tracking ✅
- [ ] Token events visible in BigQuery per section/form
- [ ] Can identify most expensive sections
- [ ] Token breakdown by type (system instruction, audio, tools)
- [ ] Matches Vertex AI billing

### Session Tracking ✅
- [ ] Complete lifecycle logged (start → complete/abandon)
- [ ] `form_session_id` survives refresh
- [ ] Accurate duration measurement
- [ ] Abandoned sessions identifiable (>24h)

### Field Tracking ✅
- [ ] Voice vs manual fill rates measurable
- [ ] High-attempt fields identifiable
- [ ] Voice→manual abandonment visible

### Error Tracking ✅
- [ ] All errors categorized and logged
- [ ] Queryable by type, severity, context
- [ ] Stack traces available (backend only)

### Compliance Ready ✅
- [ ] Audit schema defined
- [ ] IP hashing implemented
- [ ] 6-year retention configured
- [ ] Session timeline reconstructable

### No PII/PHI ✅
- [ ] BigQuery search for values returns zero
- [ ] Validation tests pass
- [ ] All logs reviewed

---

## Notes for Implementation

1. **Start with token tracking** - Priority #1
2. **Test incrementally** - Verify each phase before next
3. **Never log field values** - Add validation checks
4. **Use structured JSON** - All logs must be parseable
5. **Cloud Logging captures stdout** - Backend just prints JSON
6. **Frontend batches events** - Send via WebSocket every 5s
7. **BigQuery auto-schema** - First events define schema
8. **Cost awareness** - Batch aggressively, don't over-log
9. **Retention policies** - Configure lifecycle rules after deployment
10. **Test with complete form** - Verify all expected events logged

---

**END OF PLAN**
