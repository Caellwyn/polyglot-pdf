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

# The privileged ADMIN package (bd polyglot-pdf-pnoik). ONE image is built to
# serve TWO Cloud Run services -- polyglot-backend runs backend.main:app and
# polyglot-admin runs admin_backend.main:app -- selected at RUNTIME by
# APP_MODULE (see CMD). deploy-all.sh sets APP_MODULE for every backend
# deploy (defaulting to the public backend.main:app) and deploy-admin.sh
# overrides it to admin_backend.main:app for the admin service -- but the
# admin Cloud Run service itself has not been deployed yet (sprint-22 plan
# bead 1.3 shipped the scripts; running the first deploy is a separate,
# maintainer-gated step).
# Both packages ship in every image; the deployed service account is what
# actually gates the privileged calls, not what is present on disk.
COPY admin_backend /app/admin_backend

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

# Which ASGI app this container serves, chosen at RUNTIME, not at build time
# (bd polyglot-pdf-pnoik). deploy-all.sh builds with
# `gcloud builds submit --tag`, which cannot pass --build-arg, so a BUILD arg
# would need a second, differently-built image per service. APP_MODULE arrives
# through `gcloud run deploy --set-env-vars` instead: one image, two services.
# The default is the public backend, so an existing deploy that sets nothing
# keeps serving exactly what it served before.
#
# NO `ENV APP_MODULE=...` line: the default lives in the `:-` expansion so
# that an unset variable and an EMPTY one both fall back to the public
# backend. An ENV default would satisfy `${APP_MODULE:-...}` with its own
# value, making the fallback dead code and hiding a deploy that passed
# APP_MODULE= (empty), which would otherwise crash the container on start.
#
# Shell form on purpose: ${PORT} and ${APP_MODULE:-...} both need shell
# expansion. Pinned by tests/test_dockerfile_app_module.py.
CMD uvicorn ${APP_MODULE:-backend.main:app} --host 0.0.0.0 --port ${PORT}
