# Polyglot PDF - Integration Plan

## Goal
Create a unified web app that combines:
- PDF schema extraction (Python backend)
- Human schema editing (React frontend)
- Persistent storage for work-in-progress schemas

## Target Structure

```
polyglot-pdf/
├── backend/                    # Python FastAPI server
│   ├── api/                    # API endpoints
│   │   ├── __init__.py
│   │   ├── extraction.py       # PDF extraction endpoints
│   │   └── schemas.py          # Schema CRUD endpoints
│   ├── extractor/              # PDF extraction logic (from pdf_schema_extractor)
│   │   ├── gemini_models_v2.py
│   │   ├── gemini_enhancer_v2.py
│   │   ├── schema_merger_v2.py
│   │   ├── form_models.py
│   │   └── ...
│   ├── storage/                # Schema storage
│   │   ├── in_progress/        # WIP schemas
│   │   ├── completed/          # Finalized schemas
│   │   └── uploads/            # Uploaded PDFs
│   ├── main.py                 # FastAPI app
│   ├── requirements.txt
│   └── .env
│
├── frontend/                   # React app (from schema-editor)
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   │   ├── Upload.tsx      # NEW: PDF upload page
│   │   │   └── Editor.tsx      # Existing editor
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
│
├── docker-compose.yml          # Run backend + frontend together
└── README.md
```

## Workflow

1. **Upload PDF** → User drags PDF to frontend
2. **Extract** → Backend runs heuristic + Gemini extraction
3. **Save Draft** → Intermediate schema saved to `storage/in_progress/`
4. **Edit** → User opens schema in editor
5. **Auto-save** → Changes saved periodically to WIP
6. **Finalize** → User marks schema complete → moves to `storage/completed/`

## API Endpoints

### Extraction
- `POST /api/extract/upload` - Upload PDF, start extraction
- `GET /api/extract/status/{job_id}` - Check extraction progress
- `GET /api/extract/result/{job_id}` - Get extracted schema

### Schemas
- `GET /api/schemas` - List all schemas (with status)
- `GET /api/schemas/{id}` - Get specific schema
- `PUT /api/schemas/{id}` - Update schema
- `DELETE /api/schemas/{id}` - Delete schema
- `POST /api/schemas/{id}/finalize` - Mark schema complete

## Implementation Steps

1. ✅ Clean up pdf_schema_extractor
2. ⏳ Create unified structure
3. ⏳ Build FastAPI backend
4. ⏳ Add upload UI to frontend
5. ⏳ Connect frontend to backend
6. ⏳ Test complete workflow
