# Voice Form Filler - Project Context & Guidelines

**Last Updated**: October 22, 2025  
**Purpose**: AI onboarding guide for understanding the project and development practices

---

## What It Is

Voice-driven medical form filling system using Gemini Live API. A translation and accessibility tool that prioritizes accuracy, user confidence, and HIPAA compliance over speed.

**Primary Use Case**: Enable patients to complete medical intake forms in their native language through natural conversation, with emphasis on accuracy and control.

**Current Status**: Demo application ready with 174-field adult intake form working end-to-end.

---

## Core Design Principles

### 1. User-First Interaction
- **Patient-led conversation**: User speaks first to initiate interaction
- **Silent connection**: No AI greeting on connect, reducing anxiety  
- **Visual welcome**: Greeting carousel shows friendly prompts without audio pressure
- **Full control**: User decides when to start, pause, and resume

### 2. Privacy & HIPAA Compliance
- **Stateless backend**: Server stores ONLY form schema, never field values
- **Client-side state**: All form data lives in sessionStorage (auto-clears on tab close)
- **Ephemeral processing**: Gemini processes audio in real-time, no persistence
- **Zero PHI storage**: Logs contain session IDs and metrics only, never user data
- **TLS everywhere**: WSS for WebSocket, HTTPS for all connections

### 3. Accuracy Over Speed
- **Confirm every field**: Verbal readback before moving to next field
- **Sanity checking**: Validate logical errors (1800s birthdate, 2-digit phone)
- **No guessing**: AI asks for clarification if <90% confident
- **Easy corrections**: Natural language error recovery
- **One field at a time**: No batching (reduces errors)

### 4. User Control & Confidence
- **Transparent operation**: Visual confirmation of every field update
- **Pause/resume**: User controls conversation flow
- **Skip and return**: Can defer difficult fields
- **Clear progress**: Know where you are in the form
- **Collapsible UI**: Overlay can be minimized to prevent blocking form fields

### 5. Accessibility First
- **Language translation**: Converse in native language, form fills in English
- **Voice-only operation**: Works without typing or mouse
- **Background noise handling**: Client-side VAD filters ambient noise
- **Visual + verbal feedback**: Multiple confirmation channels
- **Error tolerance**: Handles accents, speech variations, interruptions

---

## Critical Development Rules

### READ THIS FIRST - These rules govern all development:

1. **Read planning docs before coding** - Understand context before implementing
2. **Test each piece before moving forward** - Unit tests, manual verification
3. **Follow the sprint cycle**: Plan → Implement → Test → Commit
4. **Update docs in place** - Never create new summary documents
5. **Important** - re-read rule 4 above.  NO NEW SUMMARY DOCUMENTS!!!

### Never Do
- ❌ Use `FunctionResponse` with `id` parameter (deprecated Gemini API)
- ❌ Modify `.venv` or example files
- ❌ Log field values (log IDs, types, counts only - NO PHI)
- ❌ Store PHI anywhere (logs, database, cache)
- ❌ Use `.innerHTML` with user/AI content (XSS risk)
- ❌ Create new "summary" or "status" documents

### Always Do
- ✅ Use latest model: `gemini-live-2.5-flash-preview-native-audio-09-2025`
- ✅ Create unit tests before making changes
- ✅ Maintain stateless backend (client = source of truth)
- ✅ Prioritize accuracy over speed
- ✅ Use `textContent` or `escapeHtml()` for display
- ✅ On Backend: Log metadata only: `{fieldId, fieldType, filled: boolean, timestamp}`

---

## Scope Definition

### In Scope
- **Field Types**: text, textarea, email, tel, number, date, time, datetime-local, url, password, checkbox, radio, select, combo
- **Forms**: Single-page medical intake, job applications, government services
- **Languages**: 18+ spoken languages for conversation, 80+ for form filling
- **Environments**: Works in noisy backgrounds (tested in crowded bar)

### Out of Scope
- **Parsing**: Arbitrary web forms, Shadow DOM, iframes, WYSIWYG editors
- **Forms**: Multi-page wizards, complex conditional logic, file uploads
- **Use Cases**: Non-medical forms (for MVP), batch processing, offline mode
- **Bookmarklet**: Removed - focus is on pre-mapped, known forms with defined schemas

---

## Key Metrics & Success Criteria

### Performance Targets
- VAD latency: <50ms barge-in
- Tool hallucinations: <1%
- Field accuracy: >99%
- Successful corrections: >95%
- Error rate: <1%

### Technical Success
- ✅ Works in noisy environments
- ✅ <1% tool call errors
- ✅ Handles 174-field form without crashes
- ✅ Clean idle timeout handling (60s)

### User Experience Success
- ✅ User feels in control at all times
- ✅ Every field verbally confirmed
- ✅ Easy error correction
- ✅ Works in user's native language

---

## Development Workflow

### Sprint Cycle (Required for Every Feature)

1. **Plan**: Read docs, understand requirements, identify risks
2. **Implement**: Write code following security patterns and principles
3. **Test**: Create unit tests, run manual tests, verify in noisy environment
4. **Commit**: Clean commit message, reference issue/feature

### Before Starting Any Task
- Read this document and TECHNICAL_GUIDE.md
- Understand stateless architecture
- Review security patterns
- Verify feature aligns with design principles

### When Debugging
- Browser console for client errors
- Backend logs for Gemini API issues  
- Network tab for WebSocket messages
- Test in noisy environment (VAD is critical)

---

## Common Issues & Solutions

### No WebSocket Connection
- ✓ Backend running on port 8000?
- ✓ CORS configured correctly?
- ✓ WebSocket URL matches environment?

### No Audio Input/Output
- ✓ GOOGLE_API_KEY or gcloud auth configured?
- ✓ Microphone permissions granted?
- ✓ Check browser console for Gemini connection errors

### Fields Not Updating
- ✓ Tool call errors in browser console?
- ✓ Field IDs match schema exactly?
- ✓ Check for extra quotes in field IDs (common Gemini error)
- ✓ Verify `DISABLE_GEMINI_VAD = True` if using manual activity signals

### State Mismatch
- Use "Clear Form" button to reset
- Check sessionStorage in DevTools
- Verify DOM matches sessionStorage

### VAD Issues
- ✓ VAD assets downloaded? (`frontend/download-vad-assets.sh`)
- ✓ ONNX model files accessible?
- ✓ Check `baseAssetPath` and `onnxWASMBasePath` config

---

## Quick Start Commands

### Local Development
```bash
# Backend (Vertex AI - recommended)
cd backend
gcloud auth application-default login  # One-time setup
cp .env.example .env
# Edit .env: Set VFF_DEV_LOGGING=true for verbose logs
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
./download-vad-assets.sh  # One-time: download VAD models
npm install
npm run dev  # Runs on http://localhost:5174

# Test page: http://localhost:5174/test-demo-new.html
```

### Testing
```bash
# Unit tests
pytest backend/tests/unit/ -v

# Frontend tests
cd frontend && npm test -- --run

# Manual testing checklist
1. Connect → Verify session_id appears
2. Record → Speak → Playback is smooth
3. Fields update → Green outline + checkmark
4. Refresh page → DOM restored from sessionStorage
5. Interrupt Gemini → TTS stops in <50ms
```

### Deployment
```bash
# Set environment variables
export VOICE_GCS_BUCKET=your-bucket-name
export VOICE_PROJECT_NAME=your-project-id

# Deploy
cd frontend
./deploy-demo.sh
```

---

## Recent Critical Fixes

### October 22, 2025 - Idle Timeout
- **Problem**: WebSocket timeouts causing reconnect loops
- **Solution**: Backend sends `idle_timeout` message, frontend shows manual reconnect button
- **Impact**: No wasted resources when users step away

### October 22, 2025 - VAD Improvements  
- **Problem**: Gemini making field update mistakes, missing speech
- **Solution**: Lowered VAD thresholds (0.90/0.70), increased pre-buffer to 700ms
- **Impact**: Better transcription accuracy, fewer corrections needed

### October 22, 2025 - Activity Signals
- **Problem**: Gemini not responding despite receiving audio
- **Solution**: Fixed frontend to call correct methods, disabled Gemini's automatic VAD
- **Configuration**: Set `DISABLE_GEMINI_VAD = True` when using manual signals

---

## Philosophy

We're building a tool that empowers patients to complete forms accurately in their own language, with confidence that their information is captured correctly and securely. Speed is secondary to accuracy and user control.