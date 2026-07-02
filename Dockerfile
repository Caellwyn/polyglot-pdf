# Cloud Run backend image -- built from the REPO ROOT context (bd 92qe.3).
#
# Previously this lived at backend/Dockerfile with a backend/-only build
# context, so scripts/ never reached the container. Hosted PDF->schema
# extraction (POST /api/editor/kits/{id}/extract) runs
# scripts/authoring/extract_form.py as a subprocess, so the image now copies
# the extraction pipeline alongside the backend package. deploy-all.sh builds
# with `gcloud builds submit --tag ... "$SCRIPT_DIR"` (the repo root);
# .gcloudignore keeps the Cloud Build upload lean.

FROM python:3.12-slim

WORKDIR /app

# Requirements first (Docker layer caching).
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The backend package (importable as `backend` via PYTHONPATH=/app).
COPY backend /app/backend

# The PDF->schema authoring pipeline the hosted extraction route spawns:
# extract_form.py + the bakeoff modules it sys.path-imports (acroform_dump,
# arm_llm_native, llm_providers, schema_contract, structural_enrich). Copied
# as whole directories so the scripts' relative sys.path layout keeps working
# unchanged (/app is the repo-root analogue).
COPY scripts/authoring /app/scripts/authoring
COPY scripts/bakeoff /app/scripts/bakeoff

ENV PYTHONPATH=/app

# Cloud Run sets PORT; default for local runs.
ENV PORT=8080
EXPOSE 8080

CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}
