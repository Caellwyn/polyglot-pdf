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
- 🔒 **Zero PII/PHI Storage** - Stateless backend, all sensitive data stays client-side (HIPAA-compliant by design; matters as much for immigration data as medical)
- ✔️ **Voice Confirmation** - Verbal readback before moving to next field
- 🎓 **Validation** - Sanity checking for logical errors
- 🌍 **Multilingual** - Converse in native language, form fills in any language

## 🎯 Project Vision

**Immigration is our first stop.** The initial focus is complex U.S. immigration and
legal-intake forms (e.g. USCIS I-90, IRS W-7) — long, high-stakes, multi-page
government PDFs that applicants routinely fill out in a non-native language.

The broader goal: **transform form-filling into a natural conversation** while
maintaining accuracy, privacy, and user control — enabling organizations to create
custom forms easily and letting users complete them in their native language using
voice, keyboard, or both. The architecture is form-agnostic (any schema/PDF kit
works), so the same system generalizes to other domains over time; immigration is
where we prove it first.

### Primary Use Cases
1. **Immigration & Legal Intake** *(first target)* - Applicants complete complex USCIS/IRS forms (I-90, W-7, ...) accurately in their native language
2. **Government Services** - Accessible forms for diverse populations
3. **Medical Intake Forms** - Patients complete complex forms in their language
4. **Any Multi-Page Form** - Where voice guidance improves completion rates

### Key Design Principles
- **User-First**: Users control the pace and method (voice/keyboard/both)
- **Privacy**: Zero PII/PHI storage on backend, stateless architecture
- **Accuracy**: Confirmation required, validation enforced
- **Accessibility**: Works in 18+ spoken languages, voice-only operation possible
- **Flexibility**: Admin UI allows non-developers to create forms

## 📊 Current Status

**Status**: Live Demo Available
**Last Updated**: July 2026

> There is **no active production** environment for this project today; the demo
> is the live target. The production-project plumbing below remains wired for
> when one is stood up.

### Live Demo

- **Demo site**: [polyglot-demo-aa709.web.app](https://polyglot-demo-aa709.web.app)
- **Production site (inactive)**: [polyglot-forms-919f2.web.app](https://polyglot-forms-919f2.web.app)

### Working Features
- ✅ Firebase Authentication (Google sign-in + email/password)
- ✅ Authorized-email gating for sign-up (Firestore `authorized_emails` collection)
- ✅ Gemini Live API voice integration (native audio-to-audio); default 2.5
  native-audio (backend-aware id: `gemini-live-2.5-flash-native-audio` on Vertex,
  `gemini-2.5-flash-native-audio-preview-12-2025` on AI Studio), with
  `gemini-3.1-flash-live-preview` selectable via `USE_PREMIUM_MODEL` (AI Studio only)
- ✅ Schema-driven form filling; continuous single-session flow is the default
  (`CONTINUOUS_SESSION` + `USE_DTI`), with the legacy per-section reset flow kept
  as an env-flippable fallback
- ✅ 18+ spoken languages with real-time switching
- ✅ Stateless backend architecture (HIPAA compliant)
- ✅ WebSocket real-time communication (`/ws/fill`)
- ✅ Voice tool-call loop with 7 tools (fill, confirm, form status, skip,
  field/section navigation, and the cheap-text-model "secretary" for recall)
- ✅ Hybrid voice/keyboard workflow
- ✅ GCS-backed form kit storage for deployed environments
- ✅ PDF generation/filling from filled forms (PyMuPDF, `/api/fill-pdf`)
- ✅ Visual schema editor (`schema-editor/`, hosted via `deploy-editor.sh`)
- ✅ Dual deployment paths (demo vs production)

## 🚀 Quick Start

### Prerequisites

- **Python 3.12+** with venv support
- **Node.js 18+** with npm
- **Gemini access** — either a Google Cloud project with Vertex AI + ADC (the
  default), or a Gemini Developer API key for the AI Studio path (see
  [Environment Variables](#environment-variables))

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

The backend talks to Gemini through **Vertex AI by default** (`VERTEXAI=true`),
which uses Application Default Credentials plus `GOOGLE_CLOUD_PROJECT` rather than
an API key — this is the compliance-friendly path and required for production. For
local dev, authenticate ADC (`gcloud auth application-default login`) and point at
your project:

```bash
export GOOGLE_CLOUD_PROJECT=your_gcp_project
```

To use the **Gemini Developer API (AI Studio)** instead — e.g. to run the premium
`gemini-3.1-flash-live-preview` model, which is not yet on Vertex — set
`VERTEXAI=false` and provide an API key:

```bash
export VERTEXAI=false
export GEMINI_API_KEY=your_key_here
```

Use `GEMINI_API_KEY` specifically — the backend reads that variable, and `/health`
and the startup diagnostics key off it. (The underlying SDK will also pick up
`GOOGLE_API_KEY` as an implicit fallback, but the app's own health check reports it
as missing, so it makes for confusing debugging.)

**Windows PowerShell:**
```powershell
$env:GOOGLE_CLOUD_PROJECT="your_gcp_project"
# or, for AI Studio:
$env:VERTEXAI="false"; $env:GEMINI_API_KEY="your_key_here"
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
│  - Function calling (7 tools)                │
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
- On the default Vertex path, check ADC is authenticated and `GOOGLE_CLOUD_PROJECT` is set (`gcloud auth application-default login`); on the AI Studio path (`VERTEXAI=false`), check `GEMINI_API_KEY` is set (that is the variable `/health` reports on)
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
- ✅ Use the configured native-audio model (`MODEL_NATIVE`); default is the 2.5 native-audio tier, resolved backend-aware (`gemini-live-2.5-flash-native-audio` on Vertex, `gemini-2.5-flash-native-audio-preview-12-2025` on AI Studio)
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
directly, pinned to the voice-app hosting target (`hosting` is an array of named
targets since the hosted schema editor got its own site -- bd 92qe.4):
`npm run deploy:demo` ships `--only hosting:app`, and `npm run deploy`
(production) ships `--only firestore:rules,hosting:app`. Neither touches the
editor site (that ships only via `deploy-editor.sh`). Prefer the top-level
scripts: `deploy-demo.sh` runs a separate `firebase deploy --only
firestore:rules` step so the demo path ships rules too (the app-only
`npm run deploy:demo` would not).

### Backend (Google Cloud Run)

```bash
cd backend

# Deploy to demo project
POLYGLOT_PROJECT_NAME=polyglot-demo-aa709 ./deploy-new.sh polyglot-backend polyglot-demo-aa709

# Deploy to production project
POLYGLOT_PROJECT_NAME=polyglot-forms-919f2 ./deploy-new.sh polyglot-backend polyglot-forms-919f2
```

`deploy-new.sh` builds from the repo root and sets `GOOGLE_CLOUD_PROJECT` on the
service (the Vertex/ADC path — Cloud Run's service account authenticates to Gemini
via Vertex, so no API key is needed). The form-kit storage vars are **not** set by
the script and must be configured separately (via
`gcloud run services update --update-env-vars`):

- `FORM_KITS_MODE=gcs`
- `FORM_KITS_GCS_BUCKET=<project-id>-form-kits`

Only if you deliberately run the AI Studio backend instead of Vertex
(`VERTEXAI=false`, e.g. for the premium 3.1 model) do you also need
`GEMINI_API_KEY` set on the service.

### Auth Setup (Firebase Console)

For each project:

1. **Authentication → Sign-in method**: Enable *Google* and *Email/Password*
2. **Firestore → authorized\_emails collection**: Add documents with field `email` (string) for each user allowed to self-register with email/password. Google sign-in is unrestricted.

### Firestore Security Rules

See `firestore.rules` (wired into `firebase.json`) — users can only read/write their own profile document, and the `authorized_emails` collection is readable by unauthenticated users (required for the pre-signup check) but not writable from the client. **`deploy-demo.sh` and `deploy-production.sh` ship these rules** (`firebase deploy --only firestore:rules`) on any frontend/full deploy; a project left on default-deny breaks both email signup and the profile-doc sync.

### Deployment Checklist

- [ ] `GOOGLE_CLOUD_PROJECT` set in Cloud Run (done by `deploy-new.sh`); for the AI Studio path (`VERTEXAI=false`) set `GEMINI_API_KEY` instead
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
