# AI-Powered Web Form Voice Filler

An intelligent web form filling application using Google Gemini Live API for voice-based interaction. Users can fill web forms naturally using voice conversation with an AI assistant that understands form context and guides the process.

## ✨ Features

- 🎤 **Voice-Based Form Filling** - Natural conversation with AI to fill form fields
- 🌐 **Web Form Support** - Works with any HTML form on any webpage
- 🤖 **Intelligent Field Understanding** - AI understands field labels, types, and context
- ⚡ **Real-Time Form Updates** - See form values populate as you speak
- 🔍 **Smart Field Matching** - Fuzzy matching handles variations in field labels
- ✅ **Type Validation** - Proper handling of text, checkbox, radio, and select fields
- 🔌 **WebSocket Real-Time Communication** - Live synchronization between AI and UI
- 💾 **Stateless Architecture** - Client manages all state for better scalability

## 📊 Current Status

**Status**: Production Ready ✅  
**Last Updated**: January 2025

### Architecture Highlights

- **Stateless Backend** - Client is single source of truth for form state
- **WebSocket Proxy** - Backend proxies messages between client and Gemini
- **sessionStorage** - Client state persists across reconnects
- **2 Tools** - `update_form_fields` and `get_form_status`

### Completed Features

- ✅ Web form parsing from live HTML pages
- ✅ Gemini Live API integration with function calling
- ✅ WebSocket-based real-time communication
- ✅ Voice interaction with AI assistant
- ✅ Stateless client-side state management
- ✅ Field type detection (text, checkbox, radio, select)
- ✅ Fuzzy field matching for robust label recognition
- ✅ Comprehensive test coverage (9/9 core tests passing)
- ✅ Auto-reconnect with state preservation

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

1. Open <http://localhost:5173/test-demo.html>
2. Click "Connect" (grant microphone permission)
3. Click "Start Recording"
4. Say: "My name is John Doe, email john@example.com"
5. Watch fields auto-fill!

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

- **AI_ONBOARDING.md** - Complete codebase overview for AI assistants and new developers
- **WEB_STATELESS_ARCHITECTURE.md** - Detailed architecture specification
- **live_api_best_practices.md** - Gemini Live API guidelines and best practices
- **MANUAL_TESTING_GUIDE.md** - Step-by-step manual testing procedures
- **function_calling_live_api_example_code.py** - Code examples for Gemini function calling
- **tool_declaration_example.py** - Tool declaration reference

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
1. `update_form_fields` - Update field values (AI validates against schema)
2. `get_form_status` - Get form schema structure for AI context

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
