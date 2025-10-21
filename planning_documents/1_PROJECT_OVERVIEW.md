# Voice Form Filler - Project Overview

**Last Updated**: October 18, 2025  
**Status**: Demo Ready (Phase 2 Complete + User-First Protocol)  
**Focus**: Medical intake translation & accessibility tool

---

## Critical Rules for AI Assistants

**READ THIS FIRST** - These rules govern all development work:

1. **Read planning docs before coding** - Understand context before implementing
2. **Update existing docs, never create new ones** - No duplicate "summary" documents
3. **Test each piece before moving forward** - Unit tests, manual verification, document results
4. **Follow the sprint cycle**: Plan → Implement → Test → Document → Commit
5. **Never**: 
   - Use `FunctionResponse` with `id` parameter (deprecated)
   - Modify `.venv` or example files
   - Use old model (`gemini-live-09-2025`)
   - Log field values (log IDs, types, counts only)
   - Store PHI anywhere
6. **Always**:
   - Use latest model: `gemini-2.0-flash-exp`
   - Create unit tests before making changes
   - Maintain stateless backend (client = source of truth)
   - Prioritize accuracy over speed

**Current Focus**: Demo application only. Bookmarklet is deprecated and not maintained.

---

## What It Is

Voice-driven medical form filling system using Gemini Live API. Designed as a translation and accessibility tool that prioritizes accuracy, user confidence, and HIPAA compliance over speed.

**Primary Use Case**: Enable patients to complete medical intake forms in their native language through natural conversation, with emphasis on accuracy and control.

**User-First Protocol**: Connection opens silently with visual greeting carousel. User speaks first to initiate conversation, establishing a patient-led interaction model that reduces anxiety and gives full control to the user.

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
- **Dev logging safety**: Production logging disabled by default (VFF_DEV_LOGGING=false)

### 3. Accuracy Over Speed
- **Confirm every field**: Verbal readback before moving to next field
- **Sanity checking**: Validate logical errors (1800s birthdate, 2-digit phone, city/ZIP mismatch)
- **No guessing**: AI asks for clarification if <90% confident
- **Easy corrections**: Natural language error recovery ("Actually, that should be...")
- **One field at a time**: No batching (reduces errors)

### 4. User Control & Confidence
- **Transparent operation**: Visual confirmation of every field update
- **Pause/resume**: User controls conversation flow
- **Skip and return**: Can defer difficult fields
- **Clear progress**: Know where you are in the form
- **Undo-friendly**: Easy to review and correct
- **Collapsible UI**: Overlay can be minimized to prevent blocking form fields

### 5. Accessibility First
- **Language translation**: Converse in native language, form fills in English
- **Voice-only operation**: Works without typing or mouse
- **Background noise handling**: Client-side VAD filters ambient noise
- **Visual + verbal feedback**: Multiple confirmation channels
- **Error tolerance**: Handles accents, speech variations, interruptions

---

## Current Status

**✅ Phase 1**: Client navigation, field hints, fuzzy matching  
**✅ Phase 2**: Bidirectional audio, tool calling, visual confirmation  
**✅ VAD Integration**: @ricky0123/vad-web for foreground/background discrimination  
**✅ Production Demo**: Adult intake form (174 fields) working end-to-end  
**✅ User-First Protocol**: Silent connection with greeting carousel, user speaks first  
**✅ UI Enhancements**: Collapsible overlay, cleaned-up controls  
**🚧 Phase 3**: System instruction refinement for confirmation workflow

### Deprecated Components
**⚠️ Bookmarklet**: Original arbitrary web form parser is no longer maintained. Parsing unknown web forms is out of scope for MVP. Focus is on pre-mapped, known forms (medical intake, job applications, government forms).

---

## Architecture

### Client (Source of Truth)
- **sessionStorage**: Schema, current values, session ID
- **DOM**: Live form state (canonical on conflicts)
- **VAD**: @ricky0123/vad-web (Silero model) for speech detection
- **Audio**: WebSocket + AudioWorklet (16kHz record, 24kHz playback)

### Backend (Stateless Proxy)
- **Schema storage**: In-memory only, destroyed on disconnect
- **Gemini proxy**: Forwards audio/tool calls to Gemini Live API
- **Validation only**: Checks tool calls, never stores field values
- **WebSocket**: Single connection per session

### AI Integration
- **Model**: `gemini-live-2.5-flash-preview-native-audio-09-2025` (or latest Gemini Live preview)
- **Tool**: `update_form_fields` - batch field updates
- **Tool**: `get_form_status` - query current form state
- **Navigation**: Next field hints embedded in tool responses (token optimization)

---

## Key Metrics

### Performance
- Bundle: 50.25 KB (16.21 KB gzipped)
- VAD latency: <50ms barge-in
- Tool hallucinations: <1%
- Supported field types: 18 HTML5 types

### Quality Targets
- Field accuracy: >99%
- Successful corrections: >95%
- User confidence: High (qualitative)
- Error rate: <1%

---

## Scope

### In Scope
**Field Types**: text, textarea, email, tel, number, date, time, datetime-local, url, password, checkbox, radio, select, combo  
**Features**: Voice input, visual confirmation, error correction, progress tracking, pause/resume  
**Languages**: Multi-language conversation → English form values  
**Environments**: Noisy backgrounds (tested in crowded bar)

### Out of Scope
**Parsing**: Arbitrary web forms, Shadow DOM, iframes, WYSIWYG editors  
**Forms**: Multi-page wizards, conditional logic, file uploads  
**Use Cases**: Non-medical forms (for MVP), batch processing, offline mode

---

## Environment Setup

### Backend Environment Variables

Create `backend/.env` file for local development:

```bash
# Development logging (verbose tool call/response output)
VFF_DEV_LOGGING=true

# Vertex AI users (default): No API key needed!
# Just run: gcloud auth application-default login
# The backend will use your gcloud credentials automatically

# Google AI Studio users (alternative): Need API key
# GEMINI_API_KEY=your-api-key-here

# Optional: Specify GCP project explicitly
# GOOGLE_CLOUD_PROJECT=your-project-id
```

**Authentication Methods**:
- **Vertex AI** (default, `VERTEXAI=true` in config.py): Uses Application Default Credentials from `gcloud auth application-default login` - no API key needed
- **Google AI Studio** (alternative): Set `GEMINI_API_KEY` in `.env` file

**Production Deployment**:
- Never set `VFF_DEV_LOGGING` in production (defaults to `false` for safety)
- Use service account with Vertex AI permissions
- Verify `.env` file is not included in Docker image (in `.gitignore`)

See `backend/ENV_VARIABLES.md` for complete documentation.

### Frontend Environment Variables

### Production
```bash
GOOGLE_CLOUD_PROJECT=your-project  # Use service account
VITE_WS_URL=wss://your-backend.run.app/ws/fill
```

### Development
```bash
GOOGLE_API_KEY=your-key
VITE_API_URL=http://localhost:8000
```

### Demo
- **Entry**: `https://storage.googleapis.com/.../demo/demo.html`
- **Backend**: Cloud Run (WebSocket at `/ws/fill`)
- **CDN**: GCS bucket for static assets

---

## Project Structure

### Planning Documents (Critical Reading)
1. **1_PROJECT_OVERVIEW.md** ← You are here
2. **2_ARCHITECTURE.md** - Stateless design, session lifecycle, VAD details
3. **3_IMPLEMENTATION.md** - Token optimization, production config, security patterns
4. **4_API_AND_TESTING.md** - Gemini API, testing procedures, VAD tuning
5. **5_DEMO_READINESS_IMPLEMENTATION.md** - Demo-specific implementation steps

### Backend (`backend/`)
- `config.py` - System instructions, tool declarations, production settings
- `services/form_filling_service.py` - Core business logic
- `adapters/live_ai_gemini.py` - Gemini Live API integration
- `routes/websocket_routes.py` - WebSocket handlers

### Frontend (`frontend/`)
- `src/demo/` - React demo application (active development)
- `src/bookmarklet/` - DEPRECATED (archived, not maintained)
- `src/lib/webFormConnection.ts` - WebSocket client logic
- `src/lib/audioManager.ts` - Recording/playback with VAD
- `src/webParser/extractFormSchema.ts` - Form schema extraction (for known forms)

---

## Common Issues & Solutions

### No WebSocket Connection
- ✓ Backend running on port 8000?
- ✓ CORS configured correctly?
- ✓ WebSocket URL matches environment?

### No Audio Input/Output
- ✓ GOOGLE_API_KEY set?
- ✓ Microphone permissions granted?
- ✓ Check browser console for Gemini connection errors

### Fields Not Updating
- ✓ Tool call errors in browser console?
- ✓ Field IDs match schema exactly?
- ✓ Check for extra quotes in field IDs (common Gemini error)

### State Mismatch
- Use "Clear Form" button to reset
- Check sessionStorage in DevTools
- Verify DOM matches sessionStorage

### VAD Issues
- ✓ @ricky0123/vad-web dependencies loaded?
- ✓ ONNX model files accessible?
- ✓ Check `baseAssetPath` and `onnxWASMBasePath` config

---

## Development Workflow (Sprint Cycle)

**Every feature follows this cycle**:

1. **Plan**: Read relevant docs, understand requirements, identify risks
2. **Implement**: Write code following security patterns and design principles
3. **Test**: Create unit tests, run manual tests, verify in noisy environment
4. **Document**: Update existing docs (this file, ARCHITECTURE.md, etc.) - never create new summary docs
5. **Commit**: Clean commit message, reference issue/feature

**Before starting any task**:
- Read relevant planning documents (1_PROJECT_OVERVIEW.md minimum)
- Understand stateless architecture (2_ARCHITECTURE.md)
- Review security patterns (3_IMPLEMENTATION.md)
- Verify feature aligns with design principles

**When debugging**:
- Browser console for client errors
- Backend logs for Gemini API issues
- Network tab for WebSocket messages
- Test in noisy environment (VAD is critical)

---

## Critical Development Rules

### Never Do
- ❌ Use `FunctionResponse` with `id` parameter (deprecated Gemini API pattern)
- ❌ Use old model name (`gemini-live-09-2025`) - always use latest preview
- ❌ Modify `.venv` or example files
- ❌ Log field values (log field IDs, counts, timings only)
- ❌ Store PHI anywhere (logs, database, cache)
- ❌ Use `.innerHTML` with user/AI content (XSS risk)
- ❌ Create new "summary" or "status" documents
- ❌ Move forward without testing previous step

### Always Do
- ✅ Read planning docs before coding
- ✅ Update existing docs (don't create new ones)
- ✅ Use latest Gemini model: `gemini-2.0-flash-exp`
- ✅ Create unit tests before making changes
- ✅ Test each piece before moving to next
- ✅ Use `textContent` or `escapeHtml()` for display
- ✅ Log metadata only: `{fieldId, fieldType, filled: boolean, timestamp}`
- ✅ Follow Plan → Implement → Test → Document → Commit

---

## Success Criteria

**Technical**:
- ✅ Works in noisy environments (crowded bar tested)
- ✅ <1% tool call errors
- ✅ <50ms VAD latency
- ✅ Handles 174-field form without crashes

**User Experience**:
- ✅ User feels in control at all times
- ✅ Every field verbally confirmed before proceeding
- ✅ Easy error correction
- ✅ Clear progress indication
- ✅ Works in user's native language

**Business**:
- ✅ HIPAA-compliant architecture
- ✅ Demonstrates medical intake use case
- ✅ Scalable to multiple form types
- ✅ Production-ready demo

---

## Next Steps

1. **System Instructions**: Refine for confirmation-first workflow
2. **Demo Validation**: 10+ end-to-end runs with real users
3. **Documentation**: User guide for medical staff
4. **Form Library**: Pre-map 5-10 common medical intake forms
5. **Pilot Program**: Partner clinic for real-world testing

---

**Philosophy**: We're building a tool that empowers patients to complete forms accurately in their own language, with confidence that their information is captured correctly and securely. Speed is secondary to accuracy and user control.
