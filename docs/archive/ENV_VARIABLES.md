> **ARCHIVED 2026-06-01 (bd polyglot-pdf-4p0).** Superseded by
> [`../components/config-deployment.md`](../components/config-deployment.md), which
> documents the env vars + feature flags against current code (this file predated
> the `.env.DEV` marker mechanism). Kept verbatim for history only — do not edit or
> cite as current.

# Environment Variables

## Setup

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your actual values:
   ```bash
   GEMINI_API_KEY=your_actual_api_key_here
   VFF_DEV_LOGGING=true
   ```

## Variables

### Required

- **`GEMINI_API_KEY`**: Your Gemini API key from Google AI Studio or Vertex AI

### Optional

- **`VFF_DEV_LOGGING`**: Enable detailed tool call logging
  - `true` - Enables readable, formatted logging of all tool calls and responses (for local development)
  - `false` or unset - Disables dev logging (for production)
  - **Default**: `false` (safe for production)
  
- **`GOOGLE_CLOUD_PROJECT`**: Your Google Cloud project ID (if using Vertex AI)

## Production Deployment

When deploying to Google Cloud Run:

1. **DO NOT** commit `.env` to git (it's already in `.gitignore`)
2. **DO NOT** set `VFF_DEV_LOGGING` (it will default to `false`)
3. Set only required environment variables via Cloud Run console or `gcloud` CLI:
   ```bash
   gcloud run deploy voice-form-filler \
     --set-env-vars GEMINI_API_KEY=your_key_here
   ```

## Security Notes

- Never commit `.env` to version control
- Never log sensitive data (API keys, user data) in production
- The dev logger automatically disables in production (when `VFF_DEV_LOGGING` is not set to `true`)
