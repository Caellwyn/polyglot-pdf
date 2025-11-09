# Polyglot PDF Form System - Project Context & Guidelines

**Last Updated**: November 8, 2025
**Purpose**: AI onboarding guide for understanding the project and development practices

---

## What It Is

Voice-driven form-filling application specifically designed for USCIS immigration forms, enabling users to interact with Gemini AI through voice commands to complete complex government forms. Primary focus on serving non-English speakers in immigrant support environments like nonprofit offices.

**Current Implementation Status**:
- **Working**: Voice interaction with Gemini Live API, form field updates, manual edit detection
- **In Progress**: Schema-driven forms with parts-based navigation, voice overlay integration
- **Planned**: Full PDF round-trip (extract → fill → export), admin UI for schema management

**Primary Use Cases**:
1. Immigration forms (I-90, I-589) - Non-English speakers complete forms via voice
2. Nonprofit assistance - Staff help clients in busy office environments  
3. Accessibility - Voice-only operation for users who cannot read/type
4. Any complex form where voice guidance improves completion rates

**Current Forms**:
- **I-90** (Green Card Replacement): v9 schema 100% conformant, 132 fields, 8 parts
- **I-589** (Asylum): Schema extracted, needs conformance
- **Future**: I-485, I-765, N-400 (50+ forms total planned)

---

## System Architecture Evolution

### Current State (November 2025)
The project is transitioning from a demo-based architecture to a schema-driven architecture:

**Legacy System** (Being Deprecated):
- `WebFormStateManager` + `AdultIntakeDemo.tsx`
- Custom section index files
- Working voice integration but not scalable

**New System** (Being Enhanced):
- `SchemaFormStateManager` + Schema-driven forms
- Pydantic model conformance (v1.1.0)
- Parts-based navigation matching PDF structure
- WebSocket integration (40/40 tests passing)

**Migration Status**:
- ✅ State management consolidated (Phase 1)
- ✅ WebSocket layer updated (Phase 2)
- ⏳ Voice overlay integration (Phase 4A - in progress)
- ⏰ Demo deprecation (pending)

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

### 3. Accuracy Over Speed
- **Confirm every field**: Verbal readback before moving to next field
- **Sanity checking**: Validate logical errors (1800s birthdate, 2-digit phone)
- **No guessing**: AI asks for clarification if uncertain
- **Easy corrections**: Natural language error recovery
- **One field at a time**: Planned single-field constraint (reduces errors)

### 4. User Control & Confidence
- **Transparent operation**: Visual confirmation of every field update
- **Pause/resume**: User controls conversation flow via PTT (planned default)
- **Skip and return**: Can defer difficult fields
- **Clear progress**: Parts-based navigation (e.g., "Part 2 of 8")
- **Session persistence**: sessionStorage maintains state across refreshes

### 5. Accessibility First
- **Language support**: 18+ spoken languages via Gemini Live
- **Voice-only operation**: Complete entire form without typing or mouse
- **Noise handling**: Adjustable noise gate (-50dB threshold), PTT mode available
- **Visual + verbal feedback**: Multiple confirmation channels
- **Hardware constraints**: Designed for 8-inch tablets with disposable earbuds

### 6. Technical Robustness
- **Field matching**: Fuzzy search with 52% similarity threshold
- **Message queuing**: Handles race conditions during session startup
- **Idle timeout**: Clean 60s timeout with manual reconnect
- **Error recovery**: Graceful handling of WebSocket disconnections
- **Modular architecture**: 6 specialized backend modules, 48% code reduction

---

## Critical Development Rules

### READ THIS FIRST - These rules govern all development:

1. **Read planning docs before coding** - Understand context before implementing
2. **Follow the implementation plan** - Work through phases systematically with testable deliverables
3. **Test each piece before moving forward** - Unit tests, integration tests, manual verification
4. **Update docs in place** - Never create new summary documents
5. **No code in planning docs** - Schema examples OK, but no implementation code (prevents anchoring)
6. **TECHNICAL_GUIDE.md reflects reality** - Only update after code changes, not before
7. **Create New Branches** - For each new feature, first create a new git branch

### Never Do
- ❌ Store user data (PII/PHI) in backend - only store schemas and session metadata
- ❌ Log field values (log IDs, types, counts only - NO PII/PHI)
- ❌ Use `.innerHTML` with user/AI content (XSS risk)
- ❌ Create new "summary" or "status" documents - update existing docs in place
- ❌ Skip test coverage for new features
- ❌ Mix planning and implementation in same document

### Always Do
- ✅ Use latest Gemini model: `gemini-live-2.5-flash-preview-native-audio-09-2025`
- ✅ Write tests alongside implementation (not after)
- ✅ Maintain stateless backend (client holds form state, server holds schemas)
- ✅ Prioritize accuracy over speed (especially for non-English speakers)
- ✅ Use structured logging with metadata only (never PII/PHI in backend logs)
- ✅ Apply FieldValue unwrapping in all form components
- ✅ Document technology decisions in implementation plan

---

## Current Technical Stack

### Backend
- **Language**: Python 3.11+
- **Framework**: FastAPI with WebSocket support
- **AI Integration**: Gemini Live 2.5 Flash Preview (native audio I/O)
- **PDF Processing**: PyMuPDF for field extraction/filling
- **Validation**: Pydantic models v1.1.0 for schema conformance
- **Testing**: Pytest with 102 tests passing

### Frontend
- **Framework**: React 18.3 + TypeScript
- **State Management**: SchemaFormStateManager (sessionStorage-backed)
- **Audio**: 16kHz/24kHz PCM16 with WebRTC VAD
- **Styling**: Tailwind CSS
- **Build**: Vite
- **Testing**: Vitest with 66+ tests passing

### Infrastructure
- **WebSocket**: Bidirectional communication for audio + tool calls
- **Storage**: File-based schemas (future: database)
- **Deployment**: GCS bucket + Cloud Run (planned)
- **Monitoring**: Structured logging, tool call tracking

---

## Known Issues & Active Work

### Critical Bugs (Blocking)
1. **Bug 2: Radio Buttons Reset Form** ⚠️
   - Impact: Data loss on radio button interaction
   - Status: Fix planned, 1-2 hours estimated

2. **Bug 3: Section Navigation Broken** 🔴
   - Impact: Can only access 1/8 of form
   - Status: Fix planned, 2-3 hours estimated

### In Progress
1. **Voice Overlay Integration** (Phase 4A)
   - Migrating from WebFormStateManager to SchemaFormStateManager
   - 61 code changes identified across 3 files
   - Status: Audit complete, implementation partially done

2. **Token Reduction**
   - Goal: Reduce from 7,400 to <500 initial tokens
   - Strategy: Just-in-time field loading
   - Status: Plan complete, implementation pending

3. **Hallucination Reduction**
   - Multiple strategies: audio filters, PTT default, single-field updates
   - Branch created, partial implementation (noise gate done)
   - Status: Some features complete, others pending

### Planned Features
1. **Conditional Logic System**
   - 26 string conditionals to convert to structured format
   - Bidirectional index for trigger/dependent relationships
   - JavaScript runtime evaluator needed

2. **Multi-Form Conformance**
   - I-90 complete, I-589 needs conformance
   - Additional forms: I-485, I-765, N-400
   - 6-step automated pipeline ready to apply

---

## Key Metrics & Success Criteria

### Current Performance
- **Voice Accuracy**: >99% field accuracy when confirmed
- **Tool Hallucinations**: ~5-10% (target <1% after fixes)
- **Audio Quality**: -50dB noise gate, PTT mode available
- **Session Handling**: 60s idle timeout working correctly
- **Test Coverage**: Backend 102 tests, Frontend 66+ tests

### Target Improvements
- **Token Usage**: <500 initial (from 7,400 current)
- **Hallucination Rate**: <1% (from 5-10% current)
- **Confirmation Rate**: 100% verbal confirmation
- **Form Coverage**: 50+ USCIS forms supported
- **Navigation**: All 8 sections accessible (currently broken)

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

# Test pages:
# Schema-driven: http://localhost:5174/schema-form-demo.html
# Legacy demo: http://localhost:5174/demo.html (deprecated)
```

### Testing
```bash
# Backend tests
pytest backend/tests/unit/ -v

# Frontend tests
cd frontend && npm test -- --run

# Manual testing checklist
1. Load schema-form-demo.html
2. Select I-90 schema from dropdown
3. Click microphone icon
4. Speak "My name is John Smith"
5. Verify field updates with green outline
6. Check all sections are navigable (currently broken)
7. Refresh page → verify state persistence
```

---

## Development Workflow

### For New Features
1. Create feature branch: `git checkout -b feature/description`
2. Read relevant planning documents
3. Write tests first (TDD approach)
4. Implement incrementally with frequent commits
5. Update TECHNICAL_GUIDE.md after feature works
6. Create PR with test results

### For Bug Fixes
1. Create fix branch: `git checkout -b fix/bug-description`
2. Add failing test that reproduces bug
3. Fix bug until test passes
4. Add additional edge case tests
5. Update documentation if behavior changed
6. Create PR with before/after test results

### For Documentation
1. Update existing files in place (no new summaries)
2. Move completed items to "Completed" sections
3. Add dates and status markers
4. Keep planning separate from implementation
5. Technical guide = current reality only

---

## Project Philosophy

We're building a tool that empowers people to complete forms accurately in their own language, with confidence that their information is captured correctly and securely.

**Core Values**:
- **Accuracy Over Speed**: Better to be slow and correct for immigration forms
- **User Empowerment**: Users control pace and input method
- **Privacy by Design**: Stateless architecture, zero backend storage of user data
- **Accessibility First**: Voice works in 18+ languages, handles various accents
- **Progressive Enhancement**: Start with voice, add features incrementally
- **Simplicity**: Avoid over-engineering, keep MVP lean

**Why Voice-Driven?**:
- **Language Barriers**: Non-English speakers can use native language
- **Literacy Issues**: No reading required
- **Physical Limitations**: No typing or mouse needed
- **Efficiency**: Speaking faster than typing for most users
- **Natural Interaction**: Conversational UI reduces anxiety

**Why Immigration Forms?**:
- **High Stakes**: Errors can result in deportation or denial
- **Complex Requirements**: 100+ fields, conditional logic, supplements
- **Underserved Population**: Limited English proficiency common
- **Clear Need**: Nonprofits struggle to help volume of clients
- **Measurable Impact**: Success = approved applications

**Design Decisions**:
- **Parts vs Sections**: Using "parts" to match PDF structure exactly
- **FieldValue Wrapper**: Track AI-filled vs user-filled for accuracy metrics
- **sessionStorage**: Auto-clears on tab close for privacy
- **60s Timeout**: Balance server resources with user needs
- **Manual Reconnect**: Prevent infinite reconnect loops

---

## Contact & Resources

### Key Files
- **Schemas**: `frontend/public/pdf_schema_extractor/test_schemas/`
- **Models**: `backend/models/form_models.py` (v1.1.0)
- **Tests**: `backend/tests/`, `frontend/src/**/*.test.ts`
- **Logs**: `backend/logs/` (dev only, no PHI)

### Documentation
- **Architecture**: TECHNICAL_GUIDE.md (current implementation)
- **Context**: PROJECT_CONTEXT.md (this file)
- **Status**: PROJECT_STATUS.md (feature tracking)
- **Plans**: Various `*_PLAN.md` files (future work)

### Branches
- **Main**: `origin/shared-audio-stream`
- **Fixes**: `fix/critical-bugs-and-token-reduction`
- **Features**: `feature/hallucination-reduction`
- **Migration**: `claude/align-websockets-011CUpAutS2MaBKLNxYFQRQM`

---

**Current Focus**: Fix critical bugs (radio buttons, section navigation), then implement token reduction for efficiency. Voice overlay integration and hallucination reduction features to follow.
