# Polyglot PDF Form System - Project Context & Guidelines

**Last Updated**: October 25, 2025
**Purpose**: AI onboarding guide for understanding the project and development practices

---

## What It Is

Comprehensive multilingual form system with voice interaction, PDF generation, and admin UI. A translation and accessibility tool that enables organizations to create custom forms and allows users to complete them in their native language using voice, keyboard, or both.

**Primary Use Cases**:
1. Medical intake forms - Patients complete complex forms in their language
2. Government services - Accessible forms for diverse populations
3. Job applications - Multilingual application process
4. Any multi-page form where voice guidance improves completion rates

**Current Status**: Planning Phase - Major refactor from voice-only web forms to comprehensive PDF-based system with admin UI.

---

## Core Design Principles

### 1. User-First Interaction
- **User-led conversation**: User speaks first to initiate interaction
- **Silent connection**: No AI greeting on connect, reducing anxiety
- **Visual welcome**: Greeting carousel shows friendly prompts without audio pressure
- **Full control**: User decides when to start, pause, and resume
- **Hybrid input**: Seamlessly switch between voice, keyboard, and mouse

### 2. Privacy & HIPAA Compliance
- **Stateless backend**: Server stores ONLY schemas, never user field values
- **Client-side state**: All form data lives in sessionStorage (auto-clears on tab close)
- **Ephemeral processing**: Gemini processes audio in real-time, no persistence
- **Zero PII/PHI storage**: Logs contain session IDs and metrics only, never user data
- **TLS everywhere**: WSS for WebSocket, HTTPS for all connections
- **PDF metadata only**: Embedded schema_name and session_id for validation, no direct user data exposure

### 3. Accuracy Over Speed
- **Confirm every field**: Verbal readback before moving to next field
- **Sanity checking**: Validate logical errors (1800s birthdate, 2-digit phone)
- **No guessing**: AI asks for clarification if uncertain
- **Easy corrections**: Natural language error recovery
- **One field at a time**: No batching (reduces errors)
- **Validation enforcement**: Required fields, format checks, length limits

### 4. User Control & Confidence
- **Transparent operation**: Visual confirmation of every field update
- **Pause/resume**: User controls conversation flow
- **Skip and return**: Can defer difficult fields
- **Clear progress**: "Question 4 of 10 in Section 2 of 12"
- **Session resumption**: Upload previous PDF to continue where you left off
- **No data lock-in**: User owns the PDF with all their data

### 5. Accessibility First
- **Language translation**: Converse in native language, form fills in any language
- **Voice-only operation**: Complete entire form without typing or mouse
- **Background noise handling**: Client-side VAD filters ambient noise
- **Visual + verbal feedback**: Multiple confirmation channels
- **Error tolerance**: Handles accents, speech variations, interruptions
- **Numbered paragraphs**: "Go to paragraph 4" for easier voice navigation

### 6. Organizational Flexibility
- **Non-developer schema creation**: Visual admin UI for building forms
- **No coding required**: Organizations can create forms without developers
- **Section-based organization**: Group related fields logically
- **Token-efficient design**: Smaller sections reduce AI context overhead
- **Schema versioning**: Track changes and maintain backward compatibility

---

## Critical Development Rules

### READ THIS FIRST - These rules govern all development:

1. **Read planning docs before coding** - Understand context before implementing
2. **Follow the implementation plan** - Work through phases systematically with testable deliverables
3. **Test each piece before moving forward** - Unit tests, integration tests, manual verification
4. **Update docs in place** - Never create new summary documents
5. **No code in planning docs** - Schema examples OK, but no implementation code (prevents anchoring)
6. **TECHNICAL_GUIDE.md reflects reality** - Only update after code changes, not before
7. **Create New Branches** For each new feature, first create a new git branch

### Never Do
- ❌ Write implementation code in planning documents
- ❌ Store user data (PII/PHI) in backend - only store schemas and session metadata
- ❌ Log field values (log IDs, types, counts only - NO PII/PHI)
- ❌ Use `.innerHTML` with user/AI content (XSS risk)
- ❌ Create new "summary" or "status" documents - update existing docs in place
- ❌ Modify `.venv` or example files
- ❌ Skip phases or exit criteria in implementation plan

### Always Do
- ✅ Use latest Gemini model: `gemini-live-2.5-flash-preview-native-audio-09-2025`
- ✅ Write tests alongside implementation (not after)
- ✅ Maintain stateless backend (client holds form state, server holds schemas)
- ✅ Prioritize accuracy over speed
- ✅ Use structured logging with metadata only (never PII/PHI in backend logs)
- ✅ Verify all exit criteria before moving to next phase
- ✅ Update TECHNICAL_GUIDE.md after code changes to reflect current state
- ✅ Document technology decisions in implementation plan

---

## Scope Definition

### In Scope - Current Refactor
- **Schema Management**: Admin UI for creating/editing/deleting schemas visually
- **Field Types**: text, textarea, numbered_paragraph (new), checkbox, radio, select, date, time
- **PDF Generation**: Create PDFs with embedded metadata (schema_name, session_id)
- **PDF Upload/Extract**: Parse PDFs to resume sessions
- **Session Management**: Create, validate, track sessions
- **Voice Interaction**: Gemini Live API with 18+ spoken languages
- **Section-Based Forms**: Multi-section forms with progress tracking
- **Hybrid Input**: Voice, keyboard, mouse - all work seamlessly
- **Languages**: 18+ spoken languages for voice, form supports any language
- **Environments**: Works in noisy backgrounds (client-side VAD)

### In Scope - Existing Features (Maintain)
- **Stateless Backend**: No user data storage, only schemas
- **WebSocket Communication**: Real-time voice interaction
- **Field Validation**: Required, format checking, sanity validation
- **Next Field Guidance**: AI knows what to ask next
- **Manual Edit Detection**: AI aware of keyboard input
- **Background Noise Handling**: VAD with tested thresholds

### Out of Scope
- **Complex PDF Parsing**: Only extract from PDFs we generated (known format)
- **File Upload Fields**: Not supported in this version
- **Conditional Logic**: Show/hide fields based on other values (future)
- **Multi-Language Forms**: Labels in multiple languages (future - use separate schemas for now)
- **Offline Mode**: Requires internet for Gemini API
- **Batch Processing**: One session at a time
- **Real-Time Collaboration**: Single user per session
- **Database Backend**: File-based storage for MVP (DB migration later)
- **Advanced Auth**: Simple password/IP whitelist for admin UI (OAuth later)

---

## Key Metrics & Success Criteria

### Performance Targets
- **Voice Interaction**:
  - VAD latency: <50ms barge-in
  - Field accuracy: >99%
  - Tool hallucinations: <1%
  - Successful corrections: >95%
- **PDF Operations**:
  - PDF generation: <3s for 100-field form
  - PDF extraction accuracy: >95%
  - Metadata round-trip: 100% success
- **Admin UI**:
  - Schema operations: <500ms response
  - Form preview: <1s render for 200-field schema
- **Frontend Performance**:
  - Bundle size: <500KB gzipped
  - Lighthouse score: >90

### Technical Success Criteria
- **Voice System** (Maintain existing quality):
  - Works in noisy environments
  - <1% tool call errors
  - Handles 174+ field forms without crashes
  - Clean idle timeout handling (60s)
- **PDF System** (New):
  - Successfully embed and extract metadata
  - PDF survives editing in Adobe, Preview, Chrome, Firefox
  - Round-trip maintains data integrity
  - Invalid PDFs handled gracefully
- **Admin UI** (New):
  - Non-developers can create schemas without assistance
  - Schema validation prevents broken forms
  - Real-time preview shows accurate rendering
- **Testing**:
  - Backend test coverage: >80%
  - Frontend test coverage: >70%
  - Zero critical security vulnerabilities
  - WCAG 2.1 AA compliance

### User Experience Success
- **Form Filling**:
  - User feels in control at all times
  - Every field verbally confirmed (voice mode)
  - Easy error correction via voice or keyboard
  - Works in user's native language
  - Clear progress indication
- **Session Resumption**:
  - Can upload PDF and continue from where they left off
  - No data loss on refresh (sessionStorage)
  - Expired sessions handled gracefully
- **Admin Experience**:
  - Can create 10+ field schema in <5 minutes
  - Preview accurately represents final form
  - Validation errors clearly explained

---

## Development Workflow

### Phased Implementation (Required for Refactor)

**Follow the implementation plan phases systematically**:
1. **Review Phase Plan**: Read all steps, exit criteria, and dependencies in REFACTOR_IMPLEMENTATION_PLAN.md
2. **Complete Each Step**: Work through steps sequentially within a phase
3. **Verify Exit Criteria**: Test all exit criteria before marking step complete
4. **Document Decisions**: Add technology decisions and learnings to implementation plan
5. **Update TECHNICAL_GUIDE.md**: After code changes, update to reflect current state
6. **Phase Review**: Demo to stakeholder, get feedback before next phase

### Step Completion Cycle

For each step in a phase:
1. **Understand**: Read step requirements and exit criteria
2. **Plan**: Identify approach, dependencies, and risks
3. **Implement**: Write code following design principles
4. **Test**: Create unit/integration tests, run manual tests
5. **Verify**: Check all exit criteria are met
6. **Commit**: Clean commit message, reference phase and step
7. **Update Docs**: Keep TECHNICAL_GUIDE.md current

### Before Starting Any Task
- Read this document (PROJECT_CONTEXT.md)
- Review REFACTOR_IMPLEMENTATION_PLAN.md for current phase
- Read TECHNICAL_GUIDE.md to understand current state
- Understand stateless architecture and privacy requirements
- Verify feature aligns with design principles
- Check scope definition (in scope vs out of scope)

### When Debugging
- **Frontend**: Browser console for client errors, Network tab for WebSocket
- **Backend**: Structured logs for API issues, Gemini tool call logs
- **Voice**: Test in noisy environment (VAD is critical)
- **PDF**: Test with different PDF readers (Adobe, Preview, Chrome, Firefox)
- **State**: Check sessionStorage in DevTools
- **Performance**: Use Lighthouse, Chrome DevTools profiler

---

## Common Issues & Solutions

### Voice System Issues

**No WebSocket Connection**
- ✓ Backend running on port 8000?
- ✓ CORS configured correctly?
- ✓ WebSocket URL matches environment?
- ✓ GOOGLE_API_KEY or GEMINI_API_KEY set?

**No Audio Input/Output**
- ✓ GOOGLE_API_KEY or gcloud auth configured?
- ✓ Microphone permissions granted?
- ✓ Check browser console for Gemini connection errors
- ✓ Using HTTPS or localhost (required for getUserMedia)?

**Fields Not Updating**
- ✓ Tool call errors in browser console?
- ✓ Field IDs match schema exactly?
- ✓ Check for extra quotes in field IDs (common Gemini error)
- ✓ WebSocket messages flowing (Network tab → WS)?

**State Mismatch**
- Check sessionStorage in DevTools (Application tab)
- Verify webFormState.ts persistence logic
- Clear sessionStorage and reconnect if corrupted

**VAD Issues**
- ✓ VAD assets downloaded?
- ✓ ONNX model files accessible?
- ✓ Thresholds configured correctly (0.90 speech start, 0.70 speech end)?

### PDF System Issues (New Features)

**PDF Generation Fails**
- ✓ Schema loaded correctly?
- ✓ Form data in sessionStorage?
- ✓ Check backend logs for PDF library errors
- ✓ Special characters causing encoding issues?

**PDF Upload Rejected**
- ✓ File is actually a PDF (check MIME type)?
- ✓ File size under limit (default 10MB)?
- ✓ PDF generated by this system (has metadata)?
- ✓ session_id valid and matches our format?

**PDF Extraction Inaccurate**
- ✓ PDF was generated by this system (not manually created)?
- ✓ PDF not heavily edited after generation?
- ✓ Check logs for parsing errors
- ✓ Encoding issues with multilingual text?

**Metadata Missing or Corrupted**
- ✓ PDF edited in external tool that strips custom properties?
- ✓ Check with different PDF reader (Adobe vs Preview vs Chrome)?
- ✓ Verify metadata format matches expected structure

### Admin UI Issues (New Features)

**Schema Won't Save**
- ✓ All validation errors resolved?
- ✓ Unique schema name?
- ✓ All required fields have labels?
- ✓ Numbered paragraphs have max_length set?
- ✓ At least one section defined?

**Preview Not Updating**
- ✓ Check browser console for React errors
- ✓ Schema JSON valid?
- ✓ Try refreshing the preview panel

**Form Doesn't Match Preview**
- ✓ Schema saved successfully?
- ✓ Using correct schema version?
- ✓ Clear sessionStorage and reload

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

## Project Status & Recent Changes

### October 25, 2025 - Major Refactor Planning
- **Status**: Planning phase for comprehensive system refactor
- **From**: Voice-only web form filler (working, production-ready)
- **To**: Polyglot PDF Form System with admin UI, PDF generation/extraction, session management
- **Approach**: Phased implementation with testable deliverables
- **Documentation**: See REFACTOR_IMPLEMENTATION_PLAN.md for detailed roadmap
- **Preservation**: Maintain all existing voice features and quality while adding new capabilities

### Key Architecture Decisions
- **Numbered Paragraphs**: Limited-length text boxes with numbers for voice navigation
- **PDF Metadata**: Hidden schema_name + session_id for validation and session resumption
- **Section Sizing**: Balance token efficiency with UX - keep related fields together
- **Admin UI**: Enable non-developers to create schemas visually
- **Code Reuse**: Leverage battle-tested existing components where possible
- **Simplicity First**: Avoid over-engineering, keep MVP lean, iterate based on feedback

### Maintained Features (Working System)

The existing voice form filler is fully functional with these capabilities:

**October 24, 2025 - Production Logging Infrastructure**
- Comprehensive structured logging with HIPAA compliance
- Token tracking with TEXT/AUDIO modality breakdown and cost calculation
- Session cumulative metrics for cost visibility
- Zero PHI in backend logs, frontend logs stay client-side only

**October 23, 2025 - Race Condition Fix**
- Messages queued until Gemini session ready
- Section switching and language changes work reliably from first attempt

**October 23, 2025 - Next Field Guidance**
- AI always knows which field to ask about next
- Guidance included in handshake, manual updates, section switches

**October 22, 2025 - VAD Improvements**
- Optimized thresholds (0.90/0.70) for better transcription accuracy
- 700ms pre-buffer reduces missed speech
- Works reliably in noisy environments

**October 22, 2025 - Idle Timeout**
- Clean 60s timeout handling
- Manual reconnect button (no wasted resources)

**Core Capabilities**:
- 18+ spoken languages with real-time switching
- 174-field forms tested and working
- <50ms barge-in latency
- Hybrid voice/keyboard workflow
- Stateless backend (HIPAA compliant)
- WebSocket real-time communication

---

## Philosophy

We're building a tool that empowers people to complete forms accurately in their own language, with confidence that their information is captured correctly and securely.

**Core Values**:
- **Accuracy Over Speed**: Confirm every field, validate inputs, prevent errors
- **User Empowerment**: Users own their data (PDF), control the pace, choose input method
- **Privacy by Design**: Stateless architecture, zero PII/PHI storage, client-side form state
- **Accessibility First**: Voice works in 18+ languages, hybrid input, works in noisy environments
- **Organizational Flexibility**: Non-developers can create and manage forms
- **Transparency**: Users see every change, understand progress, know what data is stored where

**Why PDF-Based?**:
- **User Data Ownership**: Users have ALL their data in a portable format they control
- **Session Resumption**: Upload PDF to continue where you left off (no account required)
- **No Vendor Lock-In**: Data not trapped in proprietary database
- **Universal Format**: PDFs open anywhere, print anywhere, email anywhere
- **Privacy**: No backend storage of sensitive data, just form templates

**Why Admin UI?**:
- **Scale Beyond One Developer**: Organizations need to create forms without engineering resources
- **Iterate Quickly**: Change form structure without code deploys
- **Domain Experts Lead**: Medical staff, HR teams, government workers design their own forms
- **Reduce Bottlenecks**: No waiting for developers to modify schemas

**Why Numbered Paragraphs?**:
- **Voice Navigation**: "Go to paragraph 4" is clearer than "go to field labeled..."
- **Editing Precision**: "Change paragraph 2" vs "change my previous response about..."
- **Token Efficiency**: Shorter field references in prompts
- **User Mental Model**: Numbered items easier to track than unnamed text areas

**Why Sections?**:
- **Cognitive Load**: 5-10 questions at a time vs 120 all at once
- **Progress Clarity**: "Section 2 of 12" shows progress better than percentages
- **Token Efficiency**: Smaller context windows for AI, faster responses
- **Logical Grouping**: Related fields together improves UX and accuracy