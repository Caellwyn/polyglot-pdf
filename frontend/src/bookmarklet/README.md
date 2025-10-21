# Voice Form Filler Bookmarklet

**Phase 2 Implementation** - Bookmarklet injection system for one-click form filling on any website.

## Architecture

### Entry Point: `index.ts`
Exposes the global API on `window.VoiceFormFiller`:
- `inject(options?)` - Start voice form filling session
- `destroy()` - Clean teardown
- `getVersion()` - Get version info
- `isActive()` - Check if currently active

### Core Modules

1. **inject.ts** - Injection logic (Step S2)
   - Idempotent injection with mutex pattern
   - CSP detection before injection
   - Container creation and DOM attachment

2. **lifecycle.ts** - Resource management
   - Clean teardown of all resources
   - WebSocket, AudioContext, MediaStream cleanup
   - Event listener and timer tracking

3. **overlay.ts** - UI overlay (Step S3)
   - Shadow DOM for style isolation
   - Draggable floating panel
   - Status indicators and controls

4. **csp-detection.ts** - Security checks (Step S7)
   - Proactive CSP detection
   - User-friendly error messages

5. **version.ts** - Version tracking
   - Build versioning
   - Release metadata

## Build Process

```bash
# Build the bookmarklet bundle
npm run build:bookmarklet
```

Output: `dist/bookmarklet/bookmarklet.bundle.js`

### Build Configuration

- **Format**: IIFE (Immediately Invoked Function Expression)
- **Global**: `window.VoiceFormFiller`
- **Target**: ES2020 (Chrome 114+)
- **Minification**: Terser with compression
- **Size Budget**: ≤200KB gzipped
- **Single File**: All imports inlined

## Design Decisions (from Phase 2 Guide)

### DOM Strategy
- **Overlay Panel**: Shadow DOM (style isolation)
- **Field Decorations**: Page DOM (need access for checkmarks)

### Security
- **CSP Detection**: Proactive test before injection
- **XSS Prevention**: `escapeHtml()` for all user-visible strings
- **No innerHTML**: Never use `.innerHTML` with user/AI content

### Idempotency
- **Mutex**: `window.__VFF_ACTIVE__` prevents double-injection
- **Safe Retry**: Multiple `inject()` calls are no-ops when active
- **Clean Teardown**: `destroy()` safe to call even if not active

### Resource Management
- Track all resources (WebSocket, AudioContext, MediaStream, timers, listeners)
- Guarantee cleanup on `destroy()`
- Leave page form fields untouched after teardown

## Next Steps (Remaining Phase 2 Steps)

- [ ] **S4**: DOM Parser integration
- [ ] **S5**: Warmup → Upgrade connection flow
- [ ] **S6**: Manual edit handling & XSS utilities
- [ ] **S7**: Complete error catalog
- [ ] **S8**: Hosting & bookmarklet loader
- [ ] **S9-S13**: Security, performance, testing, docs

## Testing

```bash
# Build and test
npm run build:bookmarklet

# Check bundle size
ls -lh dist/bookmarklet/bookmarklet.bundle.js

# Test injection on local HTML
# 1. Build bundle
# 2. Open test-demo.html in Chrome
# 3. Run in console: 
#    const script = document.createElement('script');
#    script.src = '/dist/bookmarklet/bookmarklet.bundle.js';
#    document.head.appendChild(script);
#    VoiceFormFiller.inject();
```

## Acceptance Criteria (Step S1)

- [x] Vite library mode configured (IIFE format)
- [x] Entry point exposes `window.VoiceFormFiller.inject()` and `.destroy()`
- [x] Version banner embedded
- [ ] Gzipped ≤ 200KB (verify after build)
- [ ] Bundle analyzer shows no hidden deps
- [ ] SHA-256 checksum generated

## File Structure

```
bookmarklet/
├── index.ts              # Entry point & public API
├── inject.ts             # Injection logic (S2)
├── lifecycle.ts          # Teardown & resource tracking
├── overlay.ts            # UI overlay with Shadow DOM (S3)
├── csp-detection.ts      # CSP detection (S7)
├── version.ts            # Version metadata
└── README.md            # This file
```
