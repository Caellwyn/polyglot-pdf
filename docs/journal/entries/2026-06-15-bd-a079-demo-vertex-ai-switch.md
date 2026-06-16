---
date: 2026-06-15
beads: [polyglot-pdf-a079]
pr: TBD
tags: [deployment, voice-ai, ai-models]
---

# a079: switch the demo Gemini backend from AI Studio back to Vertex AI

## Why

The demo was running on AI Studio (the Gemini Developer API, API-key auth) for
one reason only: Gemini 3.1 preview access. As of 2026-06 the 3.1 native-audio
model is available on AI Studio but NOT on Vertex AI (it 1008s "policy
violation" on the Vertex path -- see the `VERTEXAI` note in `backend/config.py`).
We are not using 3.1. Staying on AI Studio therefore bought nothing and cost
data privacy: AI Studio request data is not covered by the Vertex AI data
governance the project wants. Moving back to Vertex keeps request data private.

## What changed

One env flip in `deploy-demo.sh` (the only thing pinning the demo to AI Studio):

```
-    BACKEND_EXTRA_ENV="VERTEXAI=false,USE_PREMIUM_MODEL=false" ...
+    BACKEND_EXTRA_ENV="VERTEXAI=true,USE_PREMIUM_MODEL=false" ...
```

`USE_PREMIUM_MODEL=false` is unchanged -- that selects the 2.5 native-audio
model (`gemini-2.5-flash-native-audio-preview-12-2025`), which runs on Vertex.
The stale "Demo runs on AI Studio" comment block was rewritten to describe the
Vertex path and to record that 3.1 still requires `VERTEXAI=false` until Vertex
ships it.

No code or IAM change was needed. The Vertex path is already the code default
(`VERTEXAI` defaults to `true`) and fully implemented:
`backend/adapters/live_ai_gemini.py` builds
`genai.Client(vertexai=True, project=..., location=...)`, authenticating via
Application Default Credentials (service-account on Cloud Run), no API key.
Preconditions that were already satisfied:

- `GOOGLE_CLOUD_PROJECT` is set in the backend Cloud Run env
  (`deploy-all.sh` `BACKEND_ENV`).
- `aiplatform.googleapis.com` is enabled by the deploy
  (`deploy-all.sh` `gcloud services enable`).
- The demo Cloud Run service account
  (`polyglot-backend-sa@polyglot-demo-aa709.iam.gserviceaccount.com`) already
  holds `roles/aiplatform.user`.

The `GEMINI_API_KEY` secret is still injected via Secret Manager but is unused
on the Vertex path -- left in place (harmless) rather than removed, so a future
3.1 A/B (which needs `VERTEXAI=false`) still has its key.

## Verification

1. Local boot: ran the backend with `VERTEXAI=true USE_PREMIUM_MODEL=false
   GOOGLE_CLOUD_PROJECT=polyglot-demo-aa709`; `/health` returned
   `"vertexai":true` with the 2.5 model, and the boot log showed
   `firebase_admin_initialized method=ADC` (no API-key auth).
2. Real Vertex auth: a standalone `genai.Client(vertexai=True,
   project="polyglot-demo-aa709", location="us-central1")` `generate_content`
   call -- the adapter's exact client construction, ADC-only -- returned "OK".
   This proves ADC -> Vertex authentication works against the demo project.
3. Deployed: `./deploy-demo.sh` ran clean through all stages (Cloud Build
   SUCCESS, Cloud Run revision `polyglot-backend-00061-tm5` serving 100% as
   `polyglot-backend-sa`, frontend + Firestore rules deployed). The LIVE
   deployed backend `/health` reports `"vertexai":true`.

The one gap local verification cannot close is a full live voice form-fill turn
over the WebSocket (the SA invoking Gemini Live on the audio path). `/health`
boot + the standalone Vertex call cover auth and config; the audio round-trip is
a manual/voice-harness test-drive left to the operator.

## Doc-freshness note (closeout prep)

`check_doc_freshness.py` flagged ~12 stale tier-2 docs (auth.md,
context-compression.md, ai-models.md, stateless-architecture.md, etc.). These
are NOT triggered by this change: this branch's diff vs `origin/dev` is only
`deploy-demo.sh` and the regenerated `.firebase` hosting cache. The flags come
from unrelated source-file mtimes dated 2026-06-15 (other in-flight work /
checkout touches), not from anything in this PR. No doc update is warranted by
the Vertex env flip; reviewed and noted here per the checker's "or note the
review in the closeout journal entry" path.

## Out of scope

- Stale `in_progress` beads `polyglot-pdf-hrn` and `polyglot-pdf-jf6w` (flagged
  by `bd stale`) are pre-existing and unrelated; not touched by this PR.
- The obsolete production channel (`polyglot-forms-919f2`,
  `deploy-production.sh`) is being abandoned (no live customers, pre-MVP). The
  earlier prod-deploy-account fix (bd `polyglot-pdf-dwvb`) was reverted and
  closed as moot in the same session.
