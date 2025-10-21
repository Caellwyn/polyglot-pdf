# Production Readiness Plan

**Last Updated**: October 10, 2025  
**Critical Path to Launch**: 9-14 days | **Full Feature Complete**: 17-26 days

---

## Token Economics

**Gemini Live API**: $3/1M input tokens, $12/1M output tokens

**50k Token Cap** (recommended):
- Worst case cost: $0.60 (all output)
- Typical cost: $0.29 (70% input)
- At $1.00/form pricing = 40-70% margin
- At $0.75/form pricing = 20-60% margin

---

## Phase 1: Critical Bugs (Week 1 - 13-24 hrs)

### 1.1 VAD Self-Interruption (4-8 hrs)
**Problem**: Model cuts itself off mid-response

**Diagnose**: Add logging to identify if client-side or server-side VAD is triggering
- Client: Log state changes, audio levels, playback state
- Server: Log `serverContent.interrupted` events

**Fix**:
- Client-side: Increase ATTACK_TIME, RELEASE_TIME, TTS_BLEED_GUARD, MIN_SILENCE_DURATION
- Server-side: Change sensitivity LOW→MEDIUM, increase silence_duration_ms 250→350
- Test with `vad-tuning-lab-modular.html`

**Success**: <1% false positives, P95 latency <180ms, barge-in still works

---

### 1.2 Form Clear Bug (3-6 hrs)
**Problem**: Fields won't fill after clicking "Clear Form"

**Debug**:
1. Log schema/session_id/field states before/after clear
2. Verify schema reaches backend after clear
3. Check if manual "Rescan" fixes it

**Fix**: Clear + auto-rescan approach
- Clear DOM and client state
- Re-scan DOM for fresh schema
- Send upgrade message with new schema

**Success**: Clear→speak→fills correctly (5/5 tests)

---

### 1.3 Dropdown Language Mismatch (6-10 hrs)
**Problem**: Start in Chinese + English dropdown first field = entire session fails

**Root Cause**: Language confusion on first field breaks AI context

**Fix**:
1. **Schema**: Send dropdown options as `{label, value}` pairs (not just labels)
2. **Prompt**: Add explicit language rules to ''MESSAGE_TEMPLATE
   - "User language ≠ form language"
   - "Always use `value` attribute for dropdowns"
   - "First field language mismatch doesn't change form language"
3. **Detection**: Log warning if first field has language mismatch

**Test Matrix**: English/Spanish/Chinese × text/dropdown × matched/mismatched language (18 scenarios)

**Success**: All language combinations work, including first-field mismatches

---

## Phase 2: Billing Infrastructure (Week 1-2 - 24-34 hrs)

### 2.1 Usage Logging (8-12 hrs)
**What to Log** (per session):
```
session_id, customer_id, form_id
started_at, completed_at, duration_seconds
status: completed | abandoned | error
billable: true if completed + >50% fields filled
tokens_input, tokens_output, tokens_total
token_cap: 50000
fields_filled, fields_total
detected_language, form_language
cost_estimate
browser, mobile, form_domain
```

**NEVER log**: Field values, PHI, audio content

**Token Cap Enforcement**:
- Track running total from Gemini `response.usage_metadata`
- At 50k: Send "Session too long, please submit" + gracefully close
- Flag session as over-limit (still billable)

**Storage**: Cloud Logging (MVP) → BigQuery (scale)

**Implementation**:
- `UsageLogger` service: `start_session()`, `update_session()`, `complete_session()`
- Integrate at WebSocket connect/tool-call/disconnect

**Success**: All sessions logged, token cap enforced, no PHI in logs

---

### 2.2 Domain Whitelist (4-6 hrs)
**Map domains → customers** for billing and access control

**Whitelist Structure** (`config.py`):
```
domain → customer_id, name, plan, billable, 
         rate_per_completion, 
         max_concurrent_sessions, max_per_day, max_per_month
```

**Flow**:
1. Extract domain from WebSocket Origin header
2. Lookup in whitelist
3. Not found: Send "Domain not authorized" + close
4. Found: Attach customer config to `websocket.state`

**CORS**: Build allowed_origins from whitelist (no wildcards in prod)

**Success**: Whitelist enforced, customer_id in all logs, CORS locked down

---

### 2.3 Billing Dashboard (12-16 hrs)
**Simple read-only usage view** (no payment processing yet)

**API**:
- `GET /api/billing/usage/{customer_id}?start_date&end_date`
  - Query Cloud Logging for completed sessions
  - Aggregate by day, by form_id
  - Return: totals, daily_breakdown, top_forms

- `GET /api/billing/export/{customer_id}` → CSV download

**Dashboard** (`/billing?customer_id=...`):
- Summary cards: completions, cost, rate
- Daily usage line chart (30 days)
- Top 5 forms table
- Export CSV button

**Auth**: Token-based links (MVP)

**Success**: Dashboard accurate, mobile-friendly, CSV exports work

---

## Phase 3: Production Hardening (Week 3 - 16-22 hrs)

### 3.1 Error Handling (6-8 hrs)
**Comprehensive error catalog** with user-friendly messages

**Error Codes**:
- Connection: domain_not_authorized, session_limit_reached
- Billing: usage_quota_exceeded, daily_limit_reached, monthly_limit_reached
- Form: no_fillable_fields, form_too_large
- API: gemini_api_error, token_cap_exceeded
- Browser: microphone_permission_denied, csp_violation

**Each error needs**: What happened, what to do, who to contact

**Display**: In overlay (never browser alerts), log with context

---

### 3.2 Rate Limiting (4-6 hrs)
**Prevent cost overruns per customer**

**Limits** (from whitelist):
- Max concurrent sessions
- Max completions/day
- Max completions/month

**Enforcement**: Check on connection, increment on completion

**Storage**: In-memory (MVP) → Redis (scale)

**UX**: Friendly errors showing current usage vs limit

---

### 3.3 Monitoring & Alerts (6-8 hrs)
**Cloud Monitoring metrics**:
- `vff/sessions/active` (gauge)
- `vff/sessions/completed` (counter)
- `vff/sessions/error_rate` (%)
- `vff/api/gemini_cost` ($)
- `vff/api/tokens` (distribution)
- `vff/latency` (distribution)

**Alert Policies**:
- Error rate >5% for 5+ min
- API cost >$500/hr
- Active sessions >800 (80% of limit)
- Customer usage spike >200% of average

**Implementation**: `MetricsCollector` service sending to Cloud Monitoring API

---

## Phase 4: Security (Week 3-4 - 8-12 hrs)

### 4.1 XSS Prevention Audit (8-12 hrs)
**Security checklist**:
- [ ] No `.innerHTML` with user/AI content
- [ ] `escapeHtml()` utility created and used everywhere
- [ ] No `eval()` or `new Function()` (except CSP detection)
- [ ] All user input sanitized before display
- [ ] All AI responses sanitized before display
- [ ] No field values in logs
- [ ] sessionStorage cleared on tab close
- [ ] CSP detection working

**Deliverable**: Security audit report, no vulnerabilities

---

## Phase 5: Deferred Features (Week 2-3 - 54-80 hrs)
**Priority: Based on pilot customer feedback**

### 5.1 State Restoration (6-8 hrs)
**Reconnection after disconnect**:
- Auto-reconnect with exponential backoff (max 3-5 attempts)
- Send schema + current values from sessionStorage
- Resume filling where user left off
- Show "Reconnecting..." → "Connected" | "Connection lost"

---

### 5.2 Advanced Field Types (8-12 hrs each)
**Currently supported**: 18 HTML5 types (text, email, select, checkbox, radio, etc.)

**Deferred**:
- Checkbox groups (multiple with same name)
- File uploads (inform user to upload manually)
- Signature pads (inform user to sign manually)
- Custom date pickers (Flatpickr, etc.)

**Implement based on pilot needs**

---

### 5.3 Multi-Page Forms (16-24 hrs)
**Enable wizard-style forms**:
- Detect "Next"/"Previous" buttons
- Fill current page → Confirm → Click Next programmatically
- MutationObserver to detect page load
- Re-scan for new fields
- Track partial progress in sessionStorage

**Edge cases**: Validation errors, loading spinners, back navigation

---

### 5.4 SPA Auto-Detection (8-12 hrs)
**Auto-detect form changes** (vs manual "Rescan")

**Approach**: MutationObserver with smart notification
- Watch DOM for significant changes (5+ fields added/removed)
- Debounce 1 second to avoid noise
- Show notification: "Form changed. Click Rescan to update."
- Don't auto-rescan (could interrupt user)

**Challenge**: High false positive rate (why deferred)

---

### 5.5 Enhanced UI (16-24 hrs)
**Current**: Status indicator, buttons, field checkmarks

**Deferred**:
- Audio waveform visualization (4-6 hrs)
- Real-time transcript display (6-8 hrs)
- Field-by-field confirmation with undo (6-8 hrs)
- Latency metrics (developer mode) (2-3 hrs)
- Conversation history panel (3-4 hrs)

---

## Phase 6: Documentation (Week 4 - 12-18 hrs)

### 6.1 Customer Onboarding (8-12 hrs)
**Contents**: Getting started, domain whitelisting, integration steps, dashboard usage, troubleshooting, best practices, support

**Formats**: PDF, HTML, 10-min video walkthrough

**Goal**: Demo presenter installs in <2 minutes

---

### 6.2 API Documentation (4-6 hrs)
**OpenAPI spec** for billing endpoints

**Include**: Request/response schemas, auth, rate limits, error codes, curl/Python/JS examples

---

## Timeline & Critical Path

### Critical Path to Launch (9-14 days)
```
Phase 1: Bug Fixes          13-24 hrs (2-3 days)
Phase 2: Billing            24-34 hrs (3-4 days)
Phase 3: Production         16-22 hrs (2-3 days)
Phase 4: Security            8-12 hrs (1-2 days)
────────────────────────────────────────────────
Total Critical Path:        61-92 hrs (9-14 days)
```

### Full Feature Complete (17-26 days)
```
+ Phase 5: Deferred         54-80 hrs (7-10 days)
+ Phase 6: Documentation    12-18 hrs (2 days)
────────────────────────────────────────────────
Total All Phases:          127-190 hrs (17-26 days)
```

**Recommendation**: Ship after critical path, build Phase 5 based on pilot feedback

---

## Week-by-Week Rollout

**Week 1-2**: Phase 1 + Phase 2
- Fix bugs, add billing
- Internal testing on demo sites
- Ready for first pilot

**Week 3**: Phase 3 + Phase 4
- Production hardening
- Security audit
- Onboard 2-3 pilot customers

**Week 4**: Phase 6 (+ Phase 5 if needed)
- Documentation
- Incorporate pilot feedback
- Prepare for broader rollout

**Week 5+**: General availability
- Monitor usage and costs
- Iterate based on feedback
- Build Phase 5 features as requested

---

## Success Criteria

### Phase 1 ✅
- VAD false positives <1%
- "Clear Form" works 5/5 tests
- All language combinations work

### Phase 2 ✅
- All sessions logged (tokens, duration, customer_id)
- Token cap enforced at 50k
- Dashboard shows accurate data

### Phase 3 ✅
- All errors have friendly messages
- Rate limits enforced
- Monitoring metrics flowing
- Alerts configured

### Phase 4 ✅
- Security audit passed (no XSS)
- No PHI in logs

### Production Ready ✅
- All critical path complete (Phases 1-4)
- 3+ pilot customers live
- <5% error rate
- <2s average latency
- $0.20-0.40 average cost per completion
- Positive customer feedback

---

## Business Model Validation

### Cost Structure
**Per completion**:
- Gemini API: $0.15-0.60 (typical $0.29)
- Cloud Run: $0.01
- Total: $0.16-0.61

**Pricing**: $0.50-1.00 per completion

**Gross margin**: 20-80% (healthy)

### Break-Even
**Assumptions**: $0.75/form, 70% margin, $5k/month fixed costs
- Need: ~9,500 completions/month
- Or: 6-10 medium clinics (1,500 forms/month each)

### Scale Projections
**10 customers @ 500 forms/month**:
- Revenue: $2,500-5,000/month
- Costs: $800-3,050/month
- Profit: $1,700-4,200/month

**100 customers @ 1,000 forms/month**:
- Revenue: $50,000-100,000/month
- Costs: $16,000-61,000/month
- Profit: $34,000-84,000/month

---

## Risk Mitigation

| Risk | Mitigation | Fallback |
|------|------------|----------|
| Token usage spikes | 50k cap enforced | Reduce to 30k or raise prices |
| Customer disputes | Real-time dashboard | Manual review, goodwill credit |
| Gemini pricing changes | Monitor updates | Pass-through with 60d notice |
| Hit 1k session limit | Monitor at 700+ | Multi-project architecture |
| HIPAA questions | Stateless + docs | Legal review, audit |

---

## Field Type Support

**Supported** (18 types): ✅
- text, textarea, email, tel, url, password
- number, date, time, datetime-local
- checkbox, radio, select
- button, signature

**Deferred** (on demand): ⏸️
- Checkbox groups
- File uploads (guide user)
- Custom date pickers
- WYSIWYG editors

**Out of Scope**: ❌
- Canvas drawing
- Video/audio recording
- iframes
- Shadow DOM

---

## Day 1 Kickoff (5-7 hours)

**Immediate priorities**:
1. [ ] VAD diagnostic logging (2 hrs)
2. [ ] Token cap enforcement (2 hrs)
3. [ ] Create DOMAIN_WHITELIST (1 hr)
4. [ ] Test Chinese→English dropdown (1 hr)

**Week 1 goal**: All Phase 1 bugs fixed, basic logging live, domain whitelist active

---

## Monitoring Dashboard (Track Weekly)

**Key Metrics**:
- Completion rate (completed / started)
- Avg cost per completion
- Error rate
- Token usage distribution
- Customer satisfaction score

**Target KPIs**:
- Completion rate: >80%
- Error rate: <5%
- Avg latency: <2s
- Avg cost: $0.20-0.40
- Customer NPS: >40

---

**Ready to start? Begin with Phase 1, Task 1.1 (VAD diagnostics) - quickest win that unblocks everything else.**
