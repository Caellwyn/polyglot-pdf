# Polyglot PDF Form System

A comprehensive multilingual form system with voice interaction, PDF generation, and admin UI. Create schemas visually, fill forms via voice or keyboard in 18+ languages, and generate PDFs with embedded metadata for session resumption.

## ✨ Features

### Schema Management
- 🎨 **Visual Schema Builder** - Admin UI for creating forms without code
- 📝 **Numbered Paragraphs** - Limited-length text boxes numbered for easy voice navigation
- 📑 **Section-Based Forms** - Organize related fields together for better UX
- 🔄 **Schema Versioning** - Track changes and maintain compatibility

### Form Filling Experience
- 🎤 **Voice Interaction** - Fill forms naturally in 18+ spoken languages
- ⌨️ **Hybrid Input** - Seamlessly switch between voice, keyboard, and mouse
- 📊 **Smart Progress Tracking** - "Question 4 of 10 in Section 2 of 12"
- 🎯 **Paragraph Navigation** - Say "go to paragraph 4" or "change paragraph 2 to..."
- 🔍 **Section Navigation** - Jump between sections via voice or UI controls

### PDF Integration
- 📄 **PDF Generation** - Professional PDFs with all form data
- 🔐 **Embedded Metadata** - Hidden schema_name and session_id for validation
- 📤 **Upload & Resume** - Upload previous PDF to continue where you left off
- 🔄 **Round-Trip Integrity** - Data preserved through PDF generation/extraction cycle

### Privacy & Accuracy
- 🔒 **HIPAA-Compliant** - Zero PHI storage, stateless backend
- ✔️ **Voice Confirmation** - Verbal readback before moving to next field
- 🎓 **Validation** - Sanity checking for logical errors
- 🌍 **Multilingual** - Converse in native language, form fills in any language

## 🎯 Project Vision

**Transform form-filling into a natural conversation** while maintaining accuracy, privacy, and user control. Enable organizations to create custom forms easily and allow users to complete them in their native language using voice, keyboard, or both.

### Primary Use Cases
1. **Medical Intake Forms** - Patients complete complex forms in their language
2. **Government Services** - Accessible forms for diverse populations
3. **Job Applications** - Multilingual application process
4. **Any Multi-Page Form** - Where voice guidance improves completion rates

### Key Design Principles
- **User-First**: Users control the pace and method (voice/keyboard/both)
- **Privacy**: Zero PII/PHI storage on backend, stateless architecture
- **Accuracy**: Confirmation required, validation enforced
- **Accessibility**: Works in 18+ spoken languages, voice-only operation possible
- **Flexibility**: Admin UI allows non-developers to create forms

## 📊 Current Status

**Status**: Planning Phase - Major Refactor
**Last Updated**: October 25, 2025

### Existing System (Voice Form Filler)
- ✅ Gemini Live API voice integration working
- ✅ 18+ spoken languages with real-time switching
- ✅ 174-field adult intake form tested and working
- ✅ Stateless backend architecture (HIPAA compliant)
- ✅ WebSocket real-time communication with <50ms barge-in
- ✅ Hybrid voice/keyboard workflow
- ✅ Comprehensive test coverage

### Planned Enhancements (In Progress)
- 🔄 Admin UI for schema creation and management
- 🔄 PDF generation with embedded metadata
- 🔄 PDF upload and data extraction for session resumption
- 🔄 Numbered paragraph fields for voice navigation
- 🔄 Enhanced section-based navigation
- 🔄 Session management and validation system

See `planning_documents/REFACTOR_IMPLEMENTATION_PLAN.md` for detailed roadmap.

## 🚀 Quick Start

### Prerequisites

- **Python 3.12+** with venv support
- **Node.js 18+** with npm
- **Google Gemini API key** (set as environment variable)

### Setup

```bash
# Clone repository (if not already done)
cd polyglot-pdf

# Backend setup
python -m venv .venv
source ./.venv/Scripts/activate  # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt

# Frontend setup
npm install -C frontend
```

### Environment Variables

Set one of these:
```bash
export GOOGLE_API_KEY=your_key_here
# or
export GEMINI_API_KEY=your_key_here
```

**Windows PowerShell:**
```powershell
$env:GOOGLE_API_KEY="your_key_here"
```

### Run Development Servers

**Terminal 1 - Backend:**
```bash
source ./.venv/Scripts/activate
uvicorn backend.main:app --reload --port 8000
```
Backend available at: <http://localhost:8000>

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```
Frontend available at: <http://localhost:5173>

### Quick Test (Current Voice System)

1. Open <http://localhost:5173/test-demo-new.html>
2. Click "Connect to Voice" (grant microphone permission if prompted)
3. Select a language from the dropdown (e.g., "Spanish")
4. Gemini will greet you and ask for the first field
5. Speak naturally: "My ID is 12345" or manually type values
6. Watch fields auto-fill with confirmation!
7. Try switching sections or changing languages mid-session

## 🏗️ Architecture

### Current Architecture (Voice Form Filler)

```
┌─────────────────────────────────────────────┐
│           Frontend (React/TS)                │
│  ┌───────────────────────────────────────┐  │
│  │  sessionStorage (Form State)           │  │
│  │  - schema                               │  │
│  │  - current_values (with confirmed flags)│  │
│  └───────────────────────────────────────┘  │
│                    ↕                         │
│  ┌───────────────────────────────────────┐  │
│  │  WebSocket Connection                  │  │
│  │  - Audio streaming (binary)            │  │
│  │  - Control messages (JSON)             │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
                     ↕
┌─────────────────────────────────────────────┐
│        Backend (FastAPI/Python)              │
│  ┌───────────────────────────────────────┐  │
│  │  FormFillingService                    │  │
│  │  - Stores schema only                  │  │
│  │  - Validates tool calls                │  │
│  │  - Proxies to Gemini                   │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
                     ↕
┌─────────────────────────────────────────────┐
│        Gemini Live API                       │
│  - Voice interaction                         │
│  - Function calling (5 tools)                │
│  - Audio responses                           │
└─────────────────────────────────────────────┘
```

### Target Architecture (Polyglot PDF System)

**New Components to be Added:**
- Admin UI for schema creation
- PDF generation service with metadata embedding
- PDF upload and extraction service
- Session management system
- Schema CRUD API
- Enhanced form renderer with numbered paragraphs

See `planning_documents/REFACTOR_IMPLEMENTATION_PLAN.md` for detailed architecture plans.

## 🛠️ Tech Stack

**Backend:**
- FastAPI 0.117.1 - Modern async web framework
- google-genai 1.38.0 - Gemini Live API integration
- Pydantic - Data validation and settings
- pytest - Testing framework
- PDF Library - TBD (ReportLab, WeasyPrint, or similar)

**Frontend:**
- React 18+ - UI framework
- TypeScript - Type-safe development
- Vite - Fast build tool
- WebSocket API - Real-time communication

**Key Dependencies:**
- librosa 0.10.1 - Audio processing
- soundfile 0.12.1 - Audio I/O
- WebSockets 13-15 - Real-time communication

## 🧪 Testing

### Backend Tests
```bash
# All tests
python -m pytest backend/tests -v

# Unit tests only
python -m pytest backend/tests/unit -q

# Contract tests
python -m pytest backend/tests/contract -q
```

### Frontend Tests
```bash
cd frontend
npm test
```

### Manual Testing

See `planning_documents/MANUAL_TESTING_GUIDE.md` for detailed testing procedures (to be updated for new features).

## 📚 Documentation

### Planning Documents (`planning_documents/`)

- **REFACTOR_IMPLEMENTATION_PLAN.md** - Detailed phase-by-phase implementation plan with testable deliverables
- **PROJECT_CONTEXT.md** - Project vision, design principles, and development guidelines
- **TECHNICAL_GUIDE.md** - Complete technical reference (updated after code changes)
- **0_gemini_live_documentation.md** - Gemini Live API reference and best practices
- **5_LOGGING_OVERHAUL_PLAN.md** - Logging infrastructure specification

### Key Concepts

**Stateless Architecture:**
- Client holds all form state in sessionStorage
- Backend stores only schemas (not user data)
- Better scalability and simpler reconnect logic
- HIPAA compliant by design

**PDF Metadata System:**
- Embedded schema_name identifies form structure
- Embedded session_id validates authenticity
- Allows PDF upload to resume sessions
- Metadata hidden from casual users, extractable programmatically

**Numbered Paragraphs:**
- Limited-length text fields with visible numbers
- Voice navigation: "go to paragraph 4"
- Easier editing: "change paragraph 2 to..."
- Concatenated on PDF generation for clean output

**Section-Based Organization:**
- Related fields grouped logically
- Token-efficient for AI processing
- Progress tracking: "Q4 of 10 in Section 2 of 12"
- Reduces user overwhelm

## 🐛 Troubleshooting

### Common Issues

**Connection Errors:**
- Check `GOOGLE_API_KEY` or `GEMINI_API_KEY` is set
- Verify backend is running on port 8000
- Check for zombie processes

**Microphone Not Working:**
- Use HTTPS or localhost (required for getUserMedia)
- Check browser permissions (Settings → Privacy → Microphone)
- Try Chrome or Edge (best MediaRecorder support)

**Fields Not Updating:**
- Open browser DevTools → Network → WS tab
- Check WebSocket messages flowing
- Verify tool calls in backend logs
- Confirm schema was sent at handshake

**State Lost on Refresh:**
- Check sessionStorage in DevTools (Application tab)
- Verify webFormState.ts persistence logic
- Clear sessionStorage and reconnect if corrupted

### Debug Tools

**Backend Logs:**
```bash
# Check tool call interactions
cat .logs/gemini_tool_calls.log

# Watch live
tail -f .logs/gemini_tool_calls.log
```

**Browser Console:**
```javascript
// View stored state
console.log(sessionStorage.getItem('webFormState'))

// Clear state
sessionStorage.clear()
```

**API Documentation:**
- Backend API docs: <http://localhost:8000/docs>
- WebSocket endpoint: `ws://localhost:8000/ws/fill`

## 🤝 Contributing

### Development Workflow

1. Read `planning_documents/PROJECT_CONTEXT.md` first
2. Review `planning_documents/REFACTOR_IMPLEMENTATION_PLAN.md` for current phase
3. Create feature branch from current development branch
4. Make changes with tests
5. Run test suite: `pytest backend/tests -v`
6. Run frontend tests: `npm test -C frontend`
7. Update documentation if needed
8. Submit pull request

### Code Standards

- Python: Follow PEP 8, use type hints
- TypeScript: Follow project ESLint config
- Add tests for new features (target: 80% backend, 70% frontend coverage)
- Update planning documents for architectural changes
- Never log PII/PHI in backend logs
- Use structured logging with metadata only

### Critical Rules

**Never Do:**
- ❌ Store user data (PII/PHI) in backend
- ❌ Log field values (log IDs, types, counts only)
- ❌ Use `.innerHTML` with user/AI content (XSS risk)
- ❌ Create new summary documents (update existing docs in place)
- ❌ Modify `.venv` or example files

**Always Do:**
- ✅ Use latest Gemini model: `gemini-live-2.5-flash-preview-native-audio-09-2025`
- ✅ Create unit tests before making changes
- ✅ Maintain stateless backend (client = source of truth)
- ✅ Update `TECHNICAL_GUIDE.md` after code changes
- ✅ Use `textContent` or `escapeHtml()` for display

## 🚢 Production Deployment

**Note:** Deployment procedures are being updated for the new PDF-based architecture. Current instructions are for the existing voice form filler system.

### Backend (Google Cloud Run)

```bash
# Set your GCP project
export VOICE_PROJECT_NAME=your-project-id

# Deploy backend
cd backend
./deploy-backend.sh
```

**Environment Variables (Cloud Run):**
- `GOOGLE_API_KEY` - Gemini API key (required)
- Set via: `gcloud run services update voice-form-filler --set-env-vars GOOGLE_API_KEY=xxx`

### Production Checklist

**Backend:**
- [ ] `GOOGLE_API_KEY` set in Cloud Run
- [ ] CORS configured in `backend/cors.json` for production domains
- [ ] Health check endpoint responding
- [ ] Structured logging configured
- [ ] Session storage configured (file-based for MVP, DB for production)
- [ ] PDF generation tested on production OS

**Frontend:**
- [ ] Production backend URL configured (no localhost references)
- [ ] Environment-specific configs set
- [ ] Bundle optimized and tested (<500KB gzipped target)
- [ ] VAD parameters tuned (MIN_SPEECH_DURATION_MS=45ms for fast barge-in)

**Testing:**
- [ ] Test form creation via admin UI
- [ ] Test PDF generation with various schemas
- [ ] Test PDF upload/extraction round-trip
- [ ] Verify voice commands work on production
- [ ] Check microphone permissions flow
- [ ] Validate WebSocket connection stability

## 📝 License

[Add your license here]

## 🙏 Acknowledgments

- Google Gemini Live API for voice interaction
- FastAPI framework for backend
- React community for frontend tools

---

**For AI Assistants**: Read `planning_documents/PROJECT_CONTEXT.md` and `planning_documents/REFACTOR_IMPLEMENTATION_PLAN.md` before making changes to this codebase.

**For Developers**: This project is currently in a major refactor phase. The existing voice form filler is functional, and we're building new PDF and admin UI features around it. See the implementation plan for the roadmap.
