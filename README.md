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

**Status**: Live Demo Available
**Last Updated**: June 2026

> There is **no active production** environment for this project today; the demo
> is the live target. The production-project plumbing below remains wired for
> when one is stood up.

### Live Demo

- **Demo site**: [polyglot-demo-aa709.web.app](https://polyglot-demo-aa709.web.app)
- **Production site (inactive)**: [polyglot-forms-919f2.web.app](https://polyglot-forms-919f2.web.app)

### Working Features
- ✅ Firebase Authentication (Google sign-in + email/password)
- ✅ Authorized-email gating for sign-up (Firestore `authorized_emails` collection)
- ✅ Gemini Live API voice integration (native audio-to-audio); default
  `gemini-2.5-flash-native-audio-preview-12-2025`, with `gemini-3.1-flash-live-preview`
  selectable via `USE_PREMIUM_MODEL`
- ✅ Schema-driven form filling with section navigation
- ✅ 18+ spoken languages with real-time switching
- ✅ Stateless backend architecture (HIPAA compliant)
- ✅ WebSocket real-time communication (`/ws/fill`)
- ✅ Hybrid voice/keyboard workflow
- ✅ GCS-backed form kit storage for deployed environments
- ✅ PDF generation/filling from filled forms (PyMuPDF, `/api/fill-pdf`)
- ✅ Visual schema editor (`schema-editor/`)
- ✅ Dual deployment paths (demo vs production)

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

1. Open <http://localhost:5173/> (the Schema Form Demo SPA)
2. Sign in, then pick a form kit from the schema dropdown
3. Start the voice assistant (grant microphone permission if prompted)
4. Select a language from the dropdown (e.g., "Spanish")
5. Gemini will greet you and ask for the first field
6. Speak naturally: "My ID is 12345" or manually type values
7. Watch fields auto-fill with confirmation!
8. Try switching sections or changing languages mid-session

> The convenience launcher [`scripts/dev-local.ps1`](scripts/dev-local.ps1) (or
> the `/run-local` skill) starts the backend + frontend together; pass
> `-Model premium` to A/B the 3.1 model.

### Form Kit Workflow (Schemas + PDFs)

The repo-level `form-kits/` directory is the single source of truth for every schema/PDF pair. To add or update a kit:

1. Create a folder under `form-kits/<kit-id>/` containing at least `schema.json` and the PDF(s) referenced by that schema.
2. Run `npm run form-kits:prepare` (or any frontend command that triggers it automatically) to copy kits into `frontend/public/form-kits/` and refresh the manifest at `frontend/public/form-kits/index.json`.
3. Launch the frontend; the schema demo dropdown now shows the new kit, and its `kitId` is sent to the backend when filling PDFs.
4. Ensure the backend sees those kits by leaving the default env vars (`FORM_KITS_MODE=local`, `FORM_KITS_LOCAL_ROOT=./form-kits`) or, if serving remotely, configure the remote store vars documented in `backend/config.py` (`FORM_KITS_MODE=gcs`, bucket/base URL, optional prefix, timeout).

This workflow keeps dev and prod aligned: the frontend manifest and the backend `/api/fill-pdf` route both load assets through the same kit IDs, so a single `npm run form-kits:prepare` run guards against mismatched schemas or missing PDFs.

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

### Supporting Surfaces

Beyond the voice form-filler above, the repo ships:
- **Schema editor** (`schema-editor/`) - visual builder for creating/editing form schemas without code
- **PDF filling** (`backend/routes/pdf_fill_routes.py`, PyMuPDF) - renders filled forms to PDF via `/api/fill-pdf`
- **Form kits** (`form-kits/`) - the single source of truth for schema/PDF pairs (see the workflow above)
- **VAD tuning harness** (`frontend/src/vad-tuning/`) and **token monitor** (`token-monitor/`) - dev/observability tooling

See [`docs/INDEX.md`](docs/INDEX.md) for the canonical documentation map and [`docs/technical_guide.md`](docs/technical_guide.md) for the detailed architecture reference.

## 🛠️ Tech Stack

**Backend:**
- FastAPI 0.117.1 - Modern async web framework
- google-genai 2.8.0 - Gemini Live API integration
- Pydantic 2.x - Data validation and settings
- PyMuPDF 1.24.14 - PDF rendering / form filling
- structlog - Structured (metadata-only) logging
- pytest - Testing framework

**Frontend:**
- React 18+ - UI framework
- TypeScript - Type-safe development
- Vite - Fast build tool
- WebSocket API - Real-time communication

**Key Dependencies:**
- librosa 0.10.1 - Audio processing
- soundfile 0.12.1 - Audio I/O
- websockets 13-15 - Real-time communication
- google-cloud-storage / firebase-admin - GCS form-kit storage + auth

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

See [`docs/standards/testing.md`](docs/standards/testing.md) for the testing approach and conventions.

## 📚 Documentation

Documentation follows a 3-tier progressive-discovery system. Start with the tier-1
entry points and follow them on demand:

- **[`CLAUDE.md`](CLAUDE.md)** - Tier-1, always-loaded project guide (architecture
  summary, critical rules, scar tissue) and the entry point for AI assistants.
- **[`docs/INDEX.md`](docs/INDEX.md)** - The canonical documentation map; points at
  every tier-2 / tier-3 doc.
- **[`docs/technical_guide.md`](docs/technical_guide.md)** - Complete technical
  reference.
- **[`docs/components/`](docs/components/)** - Per-surface guides (WebSocket
  routing, voice AI, schema forms, PDF filling).
- **[`docs/standards/`](docs/standards/)** - Cross-cutting rules (HIPAA/PII policy,
  stateless architecture, VAD, AI models, logging).
- **[`docs/genai_docs/`](docs/genai_docs/README.md)** - Vendored `google-genai`
  SDK reference (authoritative for Gemini Live syntax).
- **[`docs/journal/entries/`](docs/journal/entries/)** - The chronological record
  ("why was this built this way?").

> Historical planning material has been archived under `docs/archive/` and
> `planning_documents/archived/`; it is no longer canonical reading.

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
- The client holds all field state under the `schema_form_state` key
- Clear sessionStorage and reconnect if corrupted

### Debug Tools

**Backend Logs:**

Production logs are structured (structlog JSON) and metadata-only — no field
values/PII. For local dev I/O capture, enable the dev file logger via
`backend/.env.DEV`; it writes daily `backend/logs/gemini_<date>.jsonl` files.

```bash
# Watch the day's dev capture (local only)
tail -f backend/logs/gemini_$(date +%F).jsonl
```

**Browser Console:**
```javascript
// View stored state
console.log(sessionStorage.getItem('schema_form_state'))

// Clear state
sessionStorage.clear()
```

**API Documentation:**
- Backend API docs: <http://localhost:8000/docs>
- WebSocket endpoint: `ws://localhost:8000/ws/fill`

## 🤝 Contributing

### Development Workflow

1. Read [`CLAUDE.md`](CLAUDE.md) and [`docs/INDEX.md`](docs/INDEX.md) first
2. Check the issue tracker (beads: `bd ready`) for the next unit of work
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
- Update the relevant docs (tier-2 component/standards docs + a journal entry) for architectural changes
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
- ✅ Use the configured native-audio model (`MODEL_NATIVE`); current default `gemini-2.5-flash-native-audio-preview-12-2025`
- ✅ Create unit tests before making changes
- ✅ Maintain stateless backend (client = source of truth)
- ✅ Update the relevant tier-2 doc + add a journal entry after code changes
- ✅ Use `textContent` or `escapeHtml()` for display

## 🚢 Deployment

Two independent deployment paths exist — demo and production — targeting separate Firebase/GCP projects. Deploy is **local/manual**; there is no active production environment today.

### Top-level deploy scripts (canonical)

```bash
# Deploy to demo (polyglot-demo-aa709)
./deploy-demo.sh

# Deploy to production (polyglot-forms-919f2) — inactive target
./deploy-production.sh
```

These wrap the frontend build (`build:schema:demo` / production Vite build) plus
`firebase deploy`, and also ship the Firestore security rules
(`firebase deploy --only firestore:rules`) on any frontend/full deploy. The demo
build loads `frontend/.env.demo`; production loads `frontend/.env.production`.

> Demo deploys are gated: test the change locally first, get explicit
> per-instance permission, then test-drive the live demo afterward (see
> [`CLAUDE.md`](CLAUDE.md) "Deployment / promotion").

The underlying npm scripts in `frontend/` build then call `firebase deploy`
directly: `npm run deploy:demo` is hosting-only (`--only hosting`), while
`npm run deploy` (production) runs an unscoped `firebase deploy` that ships every
configured target (hosting **and** Firestore rules). Prefer the top-level scripts:
`deploy-demo.sh` runs a separate `firebase deploy --only firestore:rules` step so
the demo path ships rules too (the hosting-only `npm run deploy:demo` would not).

### Backend (Google Cloud Run)

```bash
cd backend

# Deploy to demo project
POLYGLOT_PROJECT_NAME=polyglot-demo-aa709 ./deploy-new.sh polyglot-backend polyglot-demo-aa709

# Deploy to production project
POLYGLOT_PROJECT_NAME=polyglot-forms-919f2 ./deploy-new.sh polyglot-backend polyglot-forms-919f2
```

**Required Cloud Run environment variables** (set via `gcloud run services update --update-env-vars`):

- `GOOGLE_API_KEY` — Gemini API key
- `FORM_KITS_MODE=gcs`
- `FORM_KITS_GCS_BUCKET=<project-id>-form-kits`

### Auth Setup (Firebase Console)

For each project:

1. **Authentication → Sign-in method**: Enable *Google* and *Email/Password*
2. **Firestore → authorized\_emails collection**: Add documents with field `email` (string) for each user allowed to self-register with email/password. Google sign-in is unrestricted.

### Firestore Security Rules

See `firestore.rules` (wired into `firebase.json`) — users can only read/write their own profile document, and the `authorized_emails` collection is readable by unauthenticated users (required for the pre-signup check) but not writable from the client. **`deploy-demo.sh` and `deploy-production.sh` ship these rules** (`firebase deploy --only firestore:rules`) on any frontend/full deploy; a project left on default-deny breaks both email signup and the profile-doc sync.

### Deployment Checklist

- [ ] `GOOGLE_API_KEY` set in Cloud Run for target project
- [ ] `FORM_KITS_MODE` and `FORM_KITS_GCS_BUCKET` set in Cloud Run
- [ ] Firebase Auth sign-in methods enabled (Google + Email/Password)
- [ ] Firestore security rules deployed (shipped automatically by `deploy-demo.sh` / `deploy-production.sh`; standalone: `firebase deploy --only firestore:rules`) — a project on default-deny breaks email signup + profile sync
- [ ] `authorized_emails` collection populated for email sign-up users
- [ ] `.env.demo` / `.env.production` contain correct `VITE_WS_URL` and Firebase config
- [ ] Verify WebSocket connects after deploy (check Cloud Run logs for `ws_connect`)

## 📝 License

[Add your license here]

## 🙏 Acknowledgments

- Google Gemini Live API for voice interaction
- FastAPI framework for backend
- React community for frontend tools

---

**For AI Assistants**: Read [`CLAUDE.md`](CLAUDE.md) and [`docs/INDEX.md`](docs/INDEX.md) before making changes to this codebase.

**For Developers**: The voice form filler, schema editor, and PDF filling are all
functional and deployed to the demo. Work is tracked in beads (`bd ready`); see
[`CLAUDE.md`](CLAUDE.md) and [`docs/INDEX.md`](docs/INDEX.md) for the workflow and
architecture.
