# AI-Powered Voice Form Filler

A multilingual voice-driven medical form filling system using Google Gemini Live API. Enables patients to complete complex medical intake forms in their native language through natural conversation, with emphasis on accuracy, privacy, and user control.

## ✨ Features

### Voice & Language
- 🎤 **Natural Voice Interaction** - Conversational AI guides users field-by-field
- 🌍 **18+ Spoken Languages** - Converse in Spanish, Tagalog, French, Hindi, and more
- 🔄 **Real-Time Language Switching** - Change conversation language mid-session
- 🎯 **Next Field Guidance** - AI always knows which field to ask about next

### Form Intelligence
- 📋 **Section-Based Navigation** - Handle complex multi-section forms (174+ fields tested)
- 🔍 **Smart Field Matching** - Fuzzy matching handles variations in field labels
- ✅ **Type Validation** - Proper handling of text, checkbox, radio, select, date, time fields
- 🔄 **Manual Edit Sync** - AI aware of fields filled manually (hybrid voice/keyboard workflow)
- ⚡ **Real-Time Updates** - See form values populate as you speak

### Privacy & Accuracy
- 🔒 **HIPAA-Compliant** - Zero PHI storage, stateless backend, ephemeral audio processing
- ✔️ **Confirmation Required** - Verbal readback before moving to next field
- 🎓 **Sanity Checking** - Validates logical errors (1800s birthdate, 2-digit phone)
- 🔌 **WebSocket Real-Time** - Low-latency communication with <50ms barge-in

## 📊 Current Status

**Status**: Production Demo Ready ✅
**Last Updated**: October 23, 2025

### Architecture Highlights

- **Stateless Backend** - Client is single source of truth (HIPAA compliance)
- **Message Queuing** - Race condition fix ensures messages sent when Gemini ready
- **Next Field Guidance** - Every message includes hint for next unfilled field
- **Section-Based Flow** - Handles complex multi-section forms with context preservation
- **5 Tool Functions** - `update_form_fields`, `get_form_status`, `get_field_value`, `switch_section`, `complete_section`

### Completed Features

- ✅ Multi-section form support (174-field adult intake form working)
- ✅ 18+ spoken languages with real-time switching
- ✅ Gemini Live API native audio integration
- ✅ WebSocket-based real-time communication with auto-reconnect
- ✅ Manual VAD with <50ms barge-in latency
- ✅ Hybrid voice/keyboard workflow (manual edit detection)
- ✅ Field type detection (text, checkbox, radio, select, date, time, etc.)
- ✅ Fuzzy field matching with 52% similarity threshold
- ✅ Next field guidance in all operations (handshake, section switch, manual updates)
- ✅ Race condition fix for session initialization
- ✅ Comprehensive test coverage (backend + frontend)

## 🚀 Quick Start

### Prerequisites

- **Python 3.12+** with venv support
- **Node.js 18+** with npm
- **Google Gemini API key** (set as environment variable)

### Setup

```bash
# Clone repository (if not already done)
cd web_form_voice_filler

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

### Quick Test

1. Open <http://localhost:5174/test-demo-new.html> (note: port may be 5173 or 5174)
2. Click "Connect to Voice" (grant microphone permission if prompted)
3. Select a language from the dropdown (e.g., "Spanish")
4. Gemini will greet you in that language and ask for the first field
5. Speak naturally: "My ID is 12345" or manually type values
6. Watch fields auto-fill with confirmation!
7. Try switching sections or changing languages mid-session

## 🚢 Production Deployment

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

### Frontend Bookmarklet

```bash
# Build production bookmarklet
cd frontend
npm run build:bookmarklet

# Output: dist/bookmarklet/bookmarklet.bundle.js (50.25 kB / 16.21 kB gzipped)
```

**Deploy to Firebase Hosting or CDN:**
1. Upload `dist/bookmarklet/bookmarklet.bundle.js` to hosting
2. Update bookmarklet URL in `install-bookmarklet-production.html`
3. Deploy install page

**Bookmarklet Installation:**
Users drag the bookmarklet from install page to their browser bookmarks bar.

### Production Checklist

**Backend:**
- [ ] `GOOGLE_API_KEY` set in Cloud Run
- [ ] CORS configured in `backend/cors.json` for production domains
- [ ] Health check endpoint responding
- [ ] Logs configured for monitoring

**Frontend:**
- [ ] Bookmarklet built with `npm run build:bookmarklet`
- [ ] Production backend URL configured (no localhost references)
- [ ] Bundle uploaded to CDN/hosting
- [ ] Install page deployed and tested
- [ ] VAD parameters tuned (MIN_SPEECH_DURATION_MS=45ms for fast barge-in)

**Performance Optimizations (Oct 2025)**:
- ✅ Barge-in latency: 55% faster (100ms → 45ms debounce)
- ✅ Bundle size: 50.25 kB (16.21 kB gzipped), 5% reduction from debug removal
- ✅ Near-instant interruption: User can cut off AI mid-sentence
- ✅ Hallucination prevention: Tool calls rejected within 150ms grace period

**Testing:**
- [ ] Test bookmarklet on real web forms
- [ ] Verify barge-in works (interrupt AI mid-speech)
- [ ] Check microphone permissions flow
- [ ] Validate WebSocket connection stability

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

See `planning_documents/MANUAL_TESTING_GUIDE.md` for detailed testing procedures.

## 📚 Documentation

### Planning Documents (`planning_documents/`)

- **PROJECT_CONTEXT.md** - Project vision, design principles, and recent critical fixes
- **TECHNICAL_GUIDE.md** - Complete technical reference with recent improvements
- **0_gemini_live_documentation.md** - Gemini Live API reference and best practices
- **AI_ONBOARDING.md** - Complete codebase overview for AI assistants and new developers
- **WEB_STATELESS_ARCHITECTURE.md** - Detailed architecture specification
- **MANUAL_TESTING_GUIDE.md** - Step-by-step manual testing procedures

### Key Concepts

**Stateless Architecture:**
- Client holds all form state in sessionStorage
- Backend stores only schema for AI context
- Better scalability and simpler reconnect logic
- See `WEB_STATELESS_ARCHITECTURE.md` for details

**WebSocket Protocol:**
- Mixed binary (audio) and JSON (control) frames
- Schema sent once at handshake
- Audio streaming for voice interaction
- Tool calls for field updates

**Tool Declarations:**
1. `update_form_fields` - Update field values with validation and confirmation
2. `get_form_status` - Get overall form completion status
3. `get_field_value` - Query specific field value (with fuzzy matching)
4. `switch_section` - Navigate to different form section
5. `complete_section` - Mark current section complete and advance

**Recent Improvements (Oct 2025):**
- ✅ **Race Condition Fix** - Messages queued until Gemini session ready (~2s delay)
- ✅ **Next Field Guidance** - All communications include hint for next unfilled field
- ✅ **Language Change Fix** - Corrected `computeNextField()` parameters
- ✅ **Manual Edit Awareness** - Gemini notified when user types manually with next field hint
- ✅ **Fuzzy Field Query** - `get_field_value` with suggestions for misspelled names

## 🏗️ Architecture

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
│  - Function calling (2 tools)                │
│  - Audio responses                           │
└─────────────────────────────────────────────┘
```

## 🛠️ Tech Stack

**Backend:**
- FastAPI 0.117.1 - Modern async web framework
- google-genai 1.38.0 - Gemini Live API integration
- Pydantic - Data validation and settings
- pytest - Testing framework

**Frontend:**
- React 18+ - UI framework
- TypeScript - Type-safe development
- Vite - Fast build tool
- WebSocket API - Real-time communication

**Key Dependencies:**
- librosa 0.10.1 - Audio processing
- soundfile 0.12.1 - Audio I/O
- WebSockets 13-15 - Real-time communication

## 🐛 Troubleshooting

### Common Issues

**Connection Errors:**
- Check `GOOGLE_API_KEY` or `GEMINI_API_KEY` is set
- Verify backend is running on port 8000
- Check for zombie processes (see Quick Start section)

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

**AI Goes Silent After Tool Call:**
- Check model version: Use `gemini-live-2.5-flash-preview-native-audio-09-2025`
- Check backend logs for FunctionResponse format errors
- Verify `next_field_hint` is being sent (check logs for `has_next_hint=True`)

**Language Change Not Working:**
- ✅ **Fixed Oct 23**: `computeNextField()` parameters corrected
- Wait for "Gemini session established" log before changing language
- Check that dropdown selection triggers `changeSpokenLanguage()`

**Section Switching Issues:**
- ✅ **Fixed Oct 23**: Race condition - messages now queued until session ready
- Check backend logs for `📋 CLIENT_CONTENT_QUEUED` and `📤 SENDING_QUEUED_CLIENT_CONTENT`
- Verify `initial_field_hint` included in section switch

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

1. Create feature branch from `main`
2. Make changes with tests
3. Run test suite: `pytest backend/tests -v`
4. Run frontend tests: `npm test -C frontend`
5. Update documentation if needed
6. Submit pull request

### Code Standards

- Python: Follow PEP 8, use type hints
- TypeScript: Follow project ESLint config
- Add tests for new features
- Update planning documents for architectural changes

## 📝 License

[Add your license here]

## 🙏 Acknowledgments

- Google Gemini Live API for voice interaction
- FastAPI framework for backend
- React community for frontend tools

---

**For AI Assistants**: Read `planning_documents/AI_ONBOARDING.md` first before making changes to this codebase.
