# Reconnection Flow Summary

## Current State (What's Already Working)

### ✅ Frontend computes correct `initial_field_hint`
- `webFormConnection.ts:1377` - Calls `computeNextFieldHintString()`
- Uses `computeNextField(state, { skipConfirmed: true })` - gets NEXT UNCONFIRMED field
- Sent in handshake message (line 1392)

### ✅ Backend receives and uses `initial_field_hint`
- `websocket_routes.py:650` - Extracts from handshake
- `websocket_routes.py:709` - Passes to `_handle_fill_session`
- `websocket_routes.py:193` - Passes to `build_form_context_message` as `next_field_hint`
- `ai_context.py:318,337` - Used in system instruction template

### ✅ System instruction includes next field hint
- `config.py:256` - "1. Ask for: {next_field_hint}"
- `config.py:232` - "Greet warmly... ask for: {next_field_hint}"
- Gemini receives this in her system instructions

## Problem

After reconnection, Gemini:
1. ❌ Doesn't proactively greet and ask for next field
2. ❌ Sometimes switches to different language
3. ❌ May ask for first field instead of current unconfirmed field

## Root Cause

The system instruction contains the hint, but **no initiating message is sent** after reconnection. The initiating message is what tells Gemini "start talking now and ask for this field."

Currently, initiating messages are only sent when:
- User first selects language (sends disclaimer)
- User changes language (sends `change_spoken_language`)
- Section switch (sends initiating message)

But NOT on reconnection after timeout.

## Solution

### Option 1: Frontend Auto-sends Language Message (RECOMMENDED)

**On `session_ready` received:**
1. Check if `disclaimerShown` flag is true (stored in sessionStorage)
2. If true (reconnect), automatically send:
   ```javascript
   this.send({
     type: "change_spoken_language",
     spoken_language: this.currentSpokenLanguage,  // Last selected language
     next_field_hint: this.computeNextFieldHintString()
   });
   ```

This reuses existing backend logic (`websocket_routes.py:431`) which sends initiating message.

### Option 2: Backend Auto-sends on Reconnect

**In `_handle_fill_session` after `start_session`:**
1. Check if reconnect (has `current_values` with fields)
2. Extract `spoken_language` from handshake
3. Auto-send initiating message:
   ```python
   if initial_field_hint and is_reconnect:
       await service.send_initiating_message(spoken_language, initial_field_hint)
   ```

Requires adding `spoken_language` and `is_reconnect` to handshake.

## Recommended Implementation (Option 1)

### Frontend Changes (`webFormConnection.ts`)

```typescript
// Add property to track disclaimer state
private disclaimerShown: boolean = false;
private currentSpokenLanguage: string | null = null;

// In handleSessionReady (after receiving session_ready)
private handleSessionReady(message: any): void {
  console.log('[WebFormConnection] Session ready');

  // Check if this is a reconnect (disclaimer already shown)
  const disclaimerShown = sessionStorage.getItem('vff_disclaimer_shown') === 'true';
  const lastSpokenLanguage = sessionStorage.getItem('vff_spoken_language');

  if (disclaimerShown && lastSpokenLanguage) {
    // Auto-send language message to trigger initiating prompt (skip disclaimer)
    const nextFieldHint = this.computeNextFieldHintString();
    if (nextFieldHint) {
      this.send({
        type: 'change_spoken_language',
        spoken_language: lastSpokenLanguage,
        next_field_hint: nextFieldHint
      });
      console.log('[WebFormConnection] Auto-sent language message for reconnect');
    }
  }

  // Call callback
  if (this.callbacks.onSessionReady) {
    this.callbacks.onSessionReady();
  }
}

// When user first selects language, store it
private handleLanguageSelect(language: string): void {
  sessionStorage.setItem('vff_spoken_language', language);
  sessionStorage.setItem('vff_disclaimer_shown', 'true');
  this.currentSpokenLanguage = language;
  this.disclaimerShown = true;
  // ... send change_spoken_language message
}
```

### Backend Changes

None needed! Reuses existing `change_spoken_language` handler.

## Expected Flow After Implementation

### Initial Connection
1. Frontend connects → sends handshake
2. Backend → sends `session_ready`
3. Frontend → User selects language → sends `change_spoken_language`
4. Backend → sends disclaimer message
5. Frontend → User clicks "I Agree" → sends `change_spoken_language` again
6. Backend → sends initiating message with next field hint
7. Gemini → Greets and asks for first field

### Reconnection (After Timeout)
1. Frontend reconnects → sends handshake with `initial_field_hint` (current unconfirmed field)
2. Backend → builds system instruction with updated hint → sends `session_ready`
3. **Frontend → AUTO sends `change_spoken_language` with last language + current hint**
4. **Backend → sends initiating message (no disclaimer)**
5. **Gemini → Greets and asks for CURRENT unconfirmed field in SAME language**

## Benefits

- ✅ Reuses existing code (no backend changes)
- ✅ Maintains language across reconnects
- ✅ Skips disclaimer on reconnect
- ✅ Gemini proactively resumes from correct field
- ✅ Smooth UX - feels like continuation, not restart

## Implementation Files

### Frontend
- `frontend/src/webFormConnection.ts` - Add auto-send logic in `handleSessionReady`
- `frontend/src/shared/connection.ts` - May need to expose `onSessionReady` callback

### Backend
- No changes needed (reuses existing `change_spoken_language` handler)

## Testing

1. **Initial connection**: Verify disclaimer shown, language selection works
2. **Reconnect after timeout**:
   - Fill fields 1-3
   - Wait for timeout
   - Reconnect
   - Verify: Gemini greets in same language and asks for field #4
3. **Reconnect after manual disconnect**:
   - Same as above but manual disconnect/reconnect
4. **Language persistence**:
   - Select Spanish
   - Fill 2 fields
   - Reconnect
   - Verify: Gemini still speaks Spanish

