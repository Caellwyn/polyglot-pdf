# Testing TODO - Section Navigation Refactor & Auto-Scroll Feature

**Created**: November 18, 2025
**Purpose**: Comprehensive testing checklist for section-based navigation and auto-scroll features
**Status**: Ready for Testing

---

## 1. Section Navigation Testing

### 1.1 Sequential Navigation (Critical)
- [ ] Load I-90 form in schema-form-demo.html
- [ ] Start at section 1.1
- [ ] Click "Next" button
- [ ] **Verify**: Navigation goes to section 1.2 (not section 2)
- [ ] Click "Next" again
- [ ] **Verify**: Navigation goes to section 1.3
- [ ] Click "Next" again
- [ ] **Verify**: Navigation goes to section 1.4
- [ ] Click "Next" again
- [ ] **Verify**: Navigation goes to section 2 (after completing all 1.x sections)
- [ ] **Expected**: Sequential progression through all 16 sections

### 1.2 Previous Button Navigation
- [ ] Navigate to section 2
- [ ] Click "Previous" button
- [ ] **Verify**: Returns to section 1.4 (last subsection of part 1)
- [ ] Click "Previous" again
- [ ] **Verify**: Returns to section 1.3
- [ ] **Expected**: Backward navigation works correctly

### 1.3 Section Validation Before Navigation
- [ ] Go to section 1.1
- [ ] Leave required fields empty
- [ ] Click "Next" button
- [ ] **Verify**: Alert appears: "Please complete all required fields before continuing"
- [ ] **Verify**: Navigation is blocked
- [ ] Fill in all required fields
- [ ] Click "Next" button
- [ ] **Verify**: Navigation proceeds to section 1.2

### 1.4 Progress Bar Display
- [ ] Start at section 1.1
- [ ] **Verify**: Progress text shows "Section 1 of 16"
- [ ] **Verify**: Progress percentage is correct (~6%)
- [ ] Navigate to section 8 (middle of form)
- [ ] **Verify**: Progress text shows "Section 8 of 16"
- [ ] **Verify**: Progress percentage shows ~50%
- [ ] Navigate to section 16
- [ ] **Verify**: Progress text shows "Section 16 of 16"
- [ ] **Verify**: Progress bar is at 100%

### 1.5 Section Completion Tracking
- [ ] Complete all fields in section 1.1
- [ ] Navigate to section 1.2
- [ ] Open section dropdown (if available in UI)
- [ ] **Verify**: Section 1.1 shows as completed (checkmark or similar indicator)
- [ ] Navigate back to section 1.1
- [ ] **Verify**: All previously entered values are preserved

---

## 2. Voice Overlay Section Dropdown Testing

### 2.1 Desktop Overlay - Section Dropdown
- [ ] Load schema-form-demo.html
- [ ] Open desktop voice overlay
- [ ] Click on section dropdown
- [ ] **Verify**: All 16 sections are listed
- [ ] **Verify**: Current section shows → indicator
- [ ] **Verify**: Completed sections show ✓ indicator
- [ ] **Verify**: Pending sections show ○ indicator
- [ ] **Verify**: Section labels are correct (e.g., "Part 1.1", "Part 1.2", "Part 2")
- [ ] Click on section 3 in dropdown
- [ ] **Verify**: Navigation switches to section 3
- [ ] **Verify**: Section 3 content loads correctly
- [ ] **Verify**: Field count updates to show section 3 fields

### 2.2 Mobile Overlay - Section Dropdown
- [ ] Load schema-form-demo.html on mobile device or use responsive mode
- [ ] Open mobile voice overlay
- [ ] Tap on section dropdown
- [ ] **Verify**: All 16 sections are listed
- [ ] **Verify**: Current section shows → indicator
- [ ] **Verify**: Touch targets are large enough (44px minimum)
- [ ] Tap on section 5 in dropdown
- [ ] **Verify**: Navigation switches to section 5
- [ ] **Verify**: Dropdown closes after selection
- [ ] **Verify**: Section 5 content renders correctly on mobile

### 2.3 Section Dropdown After Form Progress
- [ ] Start at section 1.1
- [ ] Fill out sections 1.1, 1.2, 1.3 completely
- [ ] Navigate to section 2
- [ ] Open section dropdown
- [ ] **Verify**: Sections 1.1, 1.2, 1.3 show ✓ (completed)
- [ ] **Verify**: Section 2 shows → (current)
- [ ] **Verify**: Sections 3-16 show ○ (pending)
- [ ] Click on completed section 1.2
- [ ] **Verify**: Navigation works
- [ ] **Verify**: Previously entered data is intact

---

## 3. Auto-Scroll Feature Testing

### 3.1 Desktop Auto-Scroll When Gemini Fills Field
- [ ] Connect to voice filling system
- [ ] Speak to fill a field that is off-screen
- [ ] **Verify**: Page smoothly scrolls to bring the field into view
- [ ] **Verify**: Field is centered in viewport
- [ ] **Verify**: Blue highlight animation appears (1.5s pulse)
- [ ] **Verify**: Field border becomes blue during highlight
- [ ] **Verify**: Field scales slightly (1.02x) at animation peak
- [ ] **Verify**: Animation completes and field returns to normal

### 3.2 Mobile Auto-Scroll When Gemini Fills Field
- [ ] Connect to voice filling system on mobile device
- [ ] Speak to fill a field that is below the fold
- [ ] **Verify**: Page smoothly scrolls to bring the field into view
- [ ] **Verify**: Field is centered in viewport
- [ ] **Verify**: Highlight animation works on mobile
- [ ] **Verify**: No keyboard popup occurs (focus is not stolen)

### 3.3 Auto-Scroll Does Not Interfere with User Typing
- [ ] Connect to voice filling system
- [ ] Start typing in field A
- [ ] While typing, speak to fill field B (off-screen)
- [ ] **Verify**: Field B scrolls into view
- [ ] **Verify**: Cursor stays in field A (no focus steal)
- [ ] **Verify**: Can continue typing in field A without interruption
- [ ] **Expected**: Auto-scroll does not disrupt user's current input

### 3.4 Auto-Scroll Only Triggers for AI-Filled Fields
- [ ] Manually type into a field (not using voice)
- [ ] **Verify**: No auto-scroll occurs
- [ ] **Verify**: No highlight animation appears
- [ ] Use voice to fill a field
- [ ] **Verify**: Auto-scroll occurs
- [ ] **Verify**: Highlight animation appears
- [ ] **Expected**: Only AI-filled fields (confirmed: true) trigger auto-scroll

### 3.5 Auto-Scroll with Multiple Rapid Updates
- [ ] Connect to voice filling system
- [ ] Speak a long sentence that fills multiple fields quickly
- [ ] **Verify**: Each field scrolls into view in sequence
- [ ] **Verify**: Animations don't overlap or cause UI glitches
- [ ] **Verify**: Final field is visible when AI finishes
- [ ] **Expected**: Smooth UX even with rapid updates

---

## 4. Gemini Session Reset per Section

### 4.1 Session Reset When Switching Sections
- [ ] Connect to voice filling system
- [ ] Complete section 1.1 with voice
- [ ] Navigate to section 1.2
- [ ] Check backend logs for "gemini_session_closed_for_section_switch"
- [ ] **Verify**: New session started for section 1.2
- [ ] Ask Gemini a question about a field in section 1.1
- [ ] **Verify**: Gemini can still reference previous section (previous_spoken_names)
- [ ] **Expected**: Session resets but retains context of previous sections

### 4.2 Section Context in System Instruction
- [ ] Connect to voice filling system
- [ ] Start section 1.1
- [ ] Check backend logs for handshake payload
- [ ] **Verify**: section_id = "part_1_1"
- [ ] **Verify**: section_number = 1
- [ ] **Verify**: total_sections = 16
- [ ] **Verify**: section_label = "Part 1.1"
- [ ] Navigate to section 2
- [ ] **Verify**: section_id = "part_2"
- [ ] **Verify**: section_number = 5 (or correct order number)

---

## 5. State Persistence Testing

### 5.1 SessionStorage Persistence
- [ ] Fill out sections 1.1 and 1.2
- [ ] Navigate to section 1.3
- [ ] Refresh the page
- [ ] **Verify**: Still on section 1.3 after refresh
- [ ] Navigate back to section 1.1
- [ ] **Verify**: All previously entered data is intact
- [ ] Navigate to section 1.2
- [ ] **Verify**: All data preserved

### 5.2 Completed Sections Tracking
- [ ] Complete sections 1.1, 1.2, 1.3
- [ ] Navigate to section 2
- [ ] Refresh the page
- [ ] Open section dropdown
- [ ] **Verify**: Sections 1.1, 1.2, 1.3 still show as completed (✓)
- [ ] **Verify**: Current section is still section 2

### 5.3 Cross-Session Data Integrity
- [ ] Fill out multiple sections
- [ ] Close the tab
- [ ] Open new tab with same URL
- [ ] **Verify**: Data is NOT persisted (sessionStorage cleared)
- [ ] **Expected**: Privacy requirement - data clears on tab close

---

## 6. Edge Cases & Error Handling

### 6.1 Navigation to Non-Existent Section
- [ ] In browser console, try to navigate to invalid section ID
- [ ] **Verify**: Error is caught gracefully
- [ ] **Verify**: User stays on current section
- [ ] **Verify**: No UI crash or blank screen

### 6.2 Section Deduplication Validation
- [ ] Load schema with intentional duplicate section IDs
- [ ] **Verify**: Deduplication removes exact duplicates only
- [ ] **Verify**: All unique sections remain (no pattern-based merging)
- [ ] **Verify**: Navigation through unique sections works correctly

### 6.3 Empty Section Handling
- [ ] Create test schema with section containing 0 fields
- [ ] Navigate to empty section
- [ ] **Verify**: No crash
- [ ] **Verify**: "Next" button still works
- [ ] **Verify**: Progress bar accounts for empty section

### 6.4 Very Long Section Names
- [ ] Create test schema with 100+ character section label
- [ ] Load form
- [ ] **Verify**: Section label truncates or wraps appropriately
- [ ] **Verify**: Dropdown remains usable
- [ ] **Verify**: No layout breaking

---

## 7. Full Form Walkthrough

### 7.1 Complete I-90 Form End-to-End
- [ ] Load I-90 schema
- [ ] Start at section 1.1
- [ ] Fill out all fields in section 1.1 (use mix of manual + voice)
- [ ] Navigate to section 1.2
- [ ] Fill out all fields in section 1.2
- [ ] Continue through all 16 sections
- [ ] **Verify**: Navigation is sequential at all times
- [ ] **Verify**: No sections are skipped
- [ ] **Verify**: All data is preserved when navigating back
- [ ] **Verify**: Progress bar reaches 100% at section 16
- [ ] **Verify**: Can review all sections before final submission

### 7.2 Voice-Only Form Completion
- [ ] Load I-90 schema
- [ ] Use ONLY voice to fill out entire form
- [ ] **Verify**: Auto-scroll works for every field
- [ ] **Verify**: Gemini properly handles section transitions
- [ ] **Verify**: Can complete entire form without manual navigation
- [ ] **Expected**: Voice-only workflow is smooth and complete

---

## 8. Performance & Responsiveness

### 8.1 Navigation Performance
- [ ] Navigate through all 16 sections
- [ ] **Verify**: Each navigation completes in <300ms
- [ ] **Verify**: No visible lag or freezing
- [ ] **Verify**: Animations are smooth

### 8.2 Auto-Scroll Performance
- [ ] Fill 20 fields rapidly with voice
- [ ] **Verify**: Auto-scroll animations don't cause lag
- [ ] **Verify**: UI remains responsive during animations
- [ ] **Verify**: No memory leaks (check browser dev tools)

### 8.3 Large Form Performance
- [ ] Load I-90 schema (132 fields, 16 sections)
- [ ] Navigate through entire form
- [ ] **Verify**: No performance degradation
- [ ] **Verify**: SessionStorage read/write remains fast
- [ ] **Verify**: Progress bar updates smoothly

---

## 9. Cross-Browser Testing

### 9.1 Chrome/Edge
- [ ] Test all navigation features
- [ ] Test auto-scroll feature
- [ ] Test section dropdown
- [ ] **Verify**: All features work correctly

### 9.2 Firefox
- [ ] Test all navigation features
- [ ] Test auto-scroll feature
- [ ] Test section dropdown
- [ ] **Verify**: All features work correctly

### 9.3 Safari (Desktop & iOS)
- [ ] Test all navigation features
- [ ] Test auto-scroll feature
- [ ] Test section dropdown on iOS
- [ ] **Verify**: scrollIntoView works correctly
- [ ] **Verify**: CSS animations render properly

---

## 10. Accessibility Testing

### 10.1 Keyboard Navigation
- [ ] Use Tab key to navigate through form
- [ ] Use Enter to press "Next" button
- [ ] **Verify**: Focus order is logical
- [ ] **Verify**: Section transitions work with keyboard only

### 10.2 Screen Reader Compatibility
- [ ] Enable screen reader
- [ ] Navigate through sections
- [ ] **Verify**: Section changes are announced
- [ ] **Verify**: Progress updates are announced
- [ ] **Verify**: Field updates are announced
- [ ] **Verify**: Validation errors are announced

---

## Test Results Summary

**Date Tested**: _____________

**Tester**: _____________

**Overall Result**: ☐ PASS ☐ FAIL ☐ PARTIAL

**Critical Issues Found**: _____________

**Notes**: _____________

---

## Regression Testing Checklist

After fixing any bugs, re-run these critical tests:

- [ ] Section navigation sequence (1.1→1.2→1.3→2)
- [ ] Auto-scroll when Gemini fills field
- [ ] Section dropdown shows all 16 sections
- [ ] Progress bar counts sections correctly
- [ ] State persists across page refreshes
- [ ] Voice overlay section switching works
- [ ] No focus stealing during auto-scroll
- [ ] Gemini session resets per section

---

**Testing Priority**:
1. **Critical**: Section navigation sequence (test first)
2. **High**: Auto-scroll feature, section dropdown
3. **Medium**: State persistence, Gemini session reset
4. **Low**: Edge cases, cross-browser compatibility

**Estimated Testing Time**: 2-3 hours for complete walkthrough
