# Voice Form Filler Demo

Professional demo of voice-powered form filling using the Adult Intake form.

## Quick Start

### Development
```bash
cd frontend
npm run dev:demo
```

This will:
1. Build the audio worklet processor
2. Start Vite dev server on http://localhost:5174
3. Auto-open `/demo.html`

### Production Build
```bash
npm run build:demo
```

Output: `dist/demo/` - ready for deployment to GCS or Cloud Run

## Architecture

```
demo.html                           # Entry point
└── src/demo/main.tsx              # React app entry
    └── AdultIntakeDemo.tsx        # Loads form + auto-initializes voice
        └── adult_intake_demo.html  # Full form (from public/)
```

### How It Works

1. **HTML loads**: `demo.html` loads the React application
2. **React mounts**: `AdultIntakeDemo` component renders
3. **Form loads**: Fetches `adult_intake_demo.html` and `adult_intake_demo_schema.json`
4. **User clicks "Connect"**: Initializes voice connection
5. **Overlay appears**: Voice control panel ready to use
6. **Voice fills form**: AI listens and populates fields

## Deployment

### GCS Bucket (Recommended)

```bash
# Build
npm run build:demo

# Upload to GCS
gsutil -m cp -r dist/demo/* gs://your-bucket-name/

# Make public
gsutil iam ch allUsers:objectViewer gs://your-bucket-name

# Access at:
# https://storage.googleapis.com/your-bucket-name/demo.html
```

### Custom Domain (GCS + Cloud CDN)

```bash
# 1. Create bucket with domain name
gsutil mb gs://demo.yourdomain.com

# 2. Upload files
gsutil -m cp -r dist/demo/* gs://demo.yourdomain.com/

# 3. Make public
gsutil iam ch allUsers:objectViewer gs://demo.yourdomain.com

# 4. Set up Load Balancer + Cloud CDN
# Follow: https://cloud.google.com/storage/docs/hosting-static-website

# 5. Point DNS to Load Balancer IP
# demo.yourdomain.com A 203.0.113.1
```

### Cloud Run (Alternative)

Serve static files from the same backend:

```python
# backend/main.py
from fastapi.staticfiles import StaticFiles

app.mount("/demo", StaticFiles(directory="frontend/dist/demo", html=True), name="demo")
```

Deploy backend, access at:
```
https://your-backend-xyz.run.app/demo/demo.html
```

## Configuration

### WebSocket URL

**Development**: `ws://localhost:8000/ws/fill` (auto-configured)

**Production**: Update `AdultIntakeDemo.tsx`:
```typescript
const wsUrl = import.meta.env.VITE_WS_URL || 'wss://your-backend.run.app/ws/fill'
```

Or set environment variable during build:
```bash
VITE_WS_URL=wss://your-backend.run.app/ws/fill npm run build:demo
```

## File Structure

```
frontend/
├── demo.html                      # Demo entry HTML
├── vite.config.demo.ts           # Demo build config
├── public/
│   ├── adult_intake_demo.html    # Form HTML
│   └── adult_intake_demo_schema.json  # Form schema
├── src/
│   ├── shared/                   # Shared voice modules
│   │   ├── connection.ts         # WebSocket connection
│   │   ├── audioManager.ts       # Audio recording/playback
│   │   ├── fieldManager.ts       # Form field updates
│   │   ├── config.ts             # Configuration
│   │   └── languages.ts          # Supported languages
│   └── demo/
│       ├── main.tsx              # React entry point
│       ├── AdultIntakeDemo.tsx   # Main demo component
│       ├── VoiceOverlay.tsx      # Desktop voice UI
│       ├── VoiceOverlayMobile.tsx # Mobile voice UI
│       └── useDemoVAD.ts         # Voice activity detection
└── dist/demo/                    # Production build output
```

## Development Workflow

1. **Edit form**: Modify `public/adult_intake_demo.html`
2. **Hot reload**: Changes appear instantly in browser

3. **Edit voice logic**: Modify source in `src/shared/` or `src/demo/`
4. **Auto-rebuild**: Vite watches and rebuilds automatically

## Testing Checklist

- [ ] Form renders correctly
- [ ] Click "Connect" opens WebSocket
- [ ] Overlay shows field count
- [ ] Speaking fills fields
- [ ] Manual edits sync to AI
- [ ] Mobile responsive (320px, 768px)
- [ ] Production build works: `npm run build:demo && npx serve dist/demo`

## Troubleshooting

**Overlay doesn't appear**
- Check browser console for errors
- Check network tab for failed requests
- Verify schema loaded correctly

**WebSocket won't connect**
- Backend running on port 8000?
- Check CORS settings in `backend/config.py`
- Verify URL in browser console logs

**Form doesn't load**
- Check `public/adult_intake_demo.html` exists
- Check browser network tab for 404
- Look for fetch errors in console

**Build fails**
- Check Node version (need 18+)
- Clear `node_modules` and reinstall
- Ensure `npm run build:worklet` completes successfully


## Next Steps (Step 3-6)

With demo working:
- **Step 3**: Test table & grouped fields
- **Step 4**: VAD tuning for long sessions
- **Step 5**: Lock in personality/instructions
- **Step 6**: End-to-end validation

See `planning_documents/5_DEMO_READINESS_IMPLEMENTATION.md`
