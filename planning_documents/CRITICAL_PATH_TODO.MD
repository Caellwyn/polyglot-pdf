# Polyglot Forms - Pre-ESC Pilot Checklist

## Critical Path Items (Must Complete Before Pilot)

### App Functionality
- [ ] **Fix field validation** - A-number and other fields accepting invalid inputs (Est: 2-3 hours)
- [ ] **Confirmation logging with timestamps** - Track user confirmations for liability protection (Est: 2-4 hours)
  - Log format: "Field X confirmed by user at timestamp Y" (anonymized, no PII)
  - Store process logs, not actual data
  - Logs demonstrate proper confirmation workflow for liability defense
- [ ] **Update "next field" logic** - Base on unconfirmed fields, not unfilled fields (Est: 1-2 hours)
  - System should prompt for next unconfirmed field
  - Skip fields that are filled but not yet confirmed
  - Ensure user explicitly confirms each field before moving on
- [ ] **Add native language disclaimer** - Voice announcement at session start about tool vs legal advice (Est: 30 min)
- [ ] **Implement print functionality** - Must work from tablet (Est: 2-4 hours)
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