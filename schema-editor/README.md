# PDF Schema Editor

Visual editor for PDF form schemas - makes human correction of extracted schemas fast and pleasant!

## Features

✅ **Visual PDF Viewer** - Full PDF rendering with multi-page support and navigation
✅ **Color-Coded Field Overlays** - See field locations with green/yellow/red status borders
✅ **Field List** - Tree view with completion status (complete/review/error)
✅ **Property Editor** - Edit field types, help text, validation, conditional logic
✅ **Real-time Validation** - Instant feedback on schema errors
✅ **Review-Flow Navigation** - "Next to review" / N jumps to the next field needing
   attention (wraps, honors the search filter); arrow keys move selection; Esc deselects
✅ **Undo / Redo** - Full history with Cmd+Z / Cmd+Shift+Z
✅ **Drag-and-Drop Reordering** - Reorder fields within a section; merge checkbox/radio
   groups into a single options field
✅ **Interactive Preview** - Test the form's own logic (radio exclusivity, show_if
   visibility) without leaving the editor
✅ **Progress Tracking** - See completion percentage at a glance
✅ **Page Navigation** - Prev/next buttons, page input, auto-scroll to selected fields
✅ **Zoom Controls** - 50%-200% zoom with +/- buttons
✅ **Hover Tooltips** - See field name and type when hovering over PDF fields
✅ **Two Delivery Modes** - Local folder-based editing, or **hosted mode** for remote
   contractors (see below)

## Quick Start

```bash
# From project root
./scripts/run-schema-editor.sh
```

The editor will open in your browser at http://localhost:3001

## Manual Setup

If the script doesn't work:

```bash
cd schema-editor
npm install
npm run dev
```

## Usage

1. **Open a form** - Local: open your `form-kits/` folder and pick a form from the
   catalogue. Hosted: enter your access code, then pick from the shared catalogue.
2. **Navigate** - Click fields in the list or PDF viewer, or use **Next to review** /
   **N** to jump straight to the next field needing attention.
3. **Edit** - Update properties in the right panel:
   - Field type (text, checkbox, radio, etc.)
   - Spoken name (for voice AI)
   - Help text and validation rules
   - Conditional logic (`show_if` / `controls_fields`)
4. **Save** - Press Cmd+S. Locally this writes back in place (or downloads a copy on
   browsers without the File System Access API); in hosted mode it saves to the shared
   workspace.

## Keyboard Shortcuts

- **Cmd+S** / **Ctrl+S** - Save (Cmd+Shift+S = Save As, local mode)
- **Cmd+Z** / **Cmd+Shift+Z** (or **Cmd+Y**) - Undo / redo
- **N** - Jump to the next field needing review (wraps, respects the search filter)
- **Arrow Up / Arrow Down** - Move selection through the visible field list
- **Esc** - Deselect the current field (shows the form-metadata panel)

Navigation keys are ignored while you are typing in a text box.

## Field Status

- 🟢 **Green** - Complete (all required fields filled)
- 🟡 **Yellow** - Needs review (missing help text or spoken name)
- 🔴 **Red** - Error (missing required properties)

## Hosted mode (contractors)

The editor has a second delivery mode for contractors (bd polyglot-pdf-92qe.2):
built with `npm run build:hosted` (`VITE_DELIVERY_MODE=hosted`, config in
`.env.hosted`), it lists/edits kits from the backend's token-gated
`/api/editor/*` routes (the shared GCS store) instead of a local folder.

- Open the hosted URL, enter the **access code** you were given (remembered per
  browser). The code maps to a tier: **editor** (polish provided forms) or
  **author** (also: upload a blank form PDF to add it to the workspace, and run
  the server-side extraction on it -- both from the catalogue).
- The catalogue shows every kit in the shared workspace, drafts included.
- Cmd/Ctrl+S saves back to the shared store; **Mark complete** flips the kit's
  status (the server validates the schema first -- a broken schema is refused
  with the reason). Completed kits ship with the maintainer's next deploy.
- Save As / Reload-from-file / the folder picker don't exist in hosted mode.

Local dev (`npm run dev`) is unchanged -- the flag defaults off.

## Adding New Forms

The editor is a stand-alone PDF -> schema tool when run locally:

1. Click **Open form-kits folder** and pick your `form-kits/` directory.
2. **Drag-drop an AcroForm PDF** onto the catalogue -- it creates
   `form-kits/<id>/` (status:draft, no schema yet).
3. Click **Run extraction** on the new card. This POSTs to the dev server's
   `/api/extract`, which runs `scripts/authoring/extract_form.py` on the host and
   writes `form-kits/<id>/schema.json` (a validated draft). The kit then becomes
   openable for review.

The "Run extraction" button needs the host-side endpoint that only the dev
server provides, so it appears under `npm run dev` / `run-schema-editor.sh`, not
in a deployed static build. From a terminal, equivalently:

```bash
python scripts/authoring/extract_form.py \
  --pdf form-kits/<id>/form.pdf --out form-kits/<id>/schema.json
```

The model behind extraction is pluggable. **Locally** the default is the `claude`
CLI; set `EXTRACTOR_PROVIDER=gemini` (+ `GEMINI_API_KEY` and a `gemini-*`
`EXTRACTOR_MODEL`) to swap it. **Hosted** extraction runs in the Cloud Run
container, which has no `claude` CLI, so it defaults to `gemini-2.5-pro`. See
EDITOR_GUIDE.md ("Extraction backends") for the full dispatch rules.

## Project Structure

```
schema-editor/
├── src/
│   ├── App.tsx                 # Top-level orchestration: mode routing, save/open,
│   │                           #   keyboard shortcuts, the panel layout
│   ├── components/
│   │   ├── PDFViewer.tsx        # PDF.js rendering + FieldOverlay boxes (PDFPage)
│   │   ├── FieldList.tsx        # Middle pane: sectioned list, search, review nav
│   │   ├── FieldEditor.tsx      # Right pane: per-field property + metadata editor
│   │   ├── PreviewPane.tsx      # Interactive form-logic preview
│   │   ├── ValidationPanel.tsx  # Schema-wide error/warning summary
│   │   ├── FormCatalogue.tsx    # LOCAL folder-based form picker
│   │   ├── RemoteCatalogue.tsx  # HOSTED catalogue over the /api/editor routes
│   │   ├── AccessCodeGate.tsx   # Hosted access-code entry + tier probe
│   │   └── HostedGuide.tsx      # Hosted first-run 3-step guide
│   ├── utils/
│   │   ├── validation.ts        # checkFieldComplete / getCompletionStats (status rules)
│   │   ├── formKitDirectory.ts  # Local File System Access directory scan
│   │   ├── remoteKitStore.ts    # Hosted fetch layer (session/kits/schema/pdf/save)
│   │   ├── fieldGrouping.ts     # Merge/ungroup checkbox+radio fields
│   │   ├── conditionalVisibility.ts  # show_if evaluation for the preview
│   │   └── schemaLoader.ts      # Load/save schema JSON
│   ├── hooks/useSchemaHistory.ts # Undo/redo state
│   └── types/schema.ts          # FormSchema / FormField / section types
├── .env.hosted                 # VITE_DELIVERY_MODE=hosted + backend base URL
└── vite-plugins/               # Dev-only /api/extract endpoint (local extraction)
```

For a deeper walkthrough of every panel and workflow, see
[`EDITOR_GUIDE.md`](./EDITOR_GUIDE.md); for deployment, see
[`../deploy-editor.sh`](../deploy-editor.sh) (one-time setup runbook in its header)
and [`../docs/components/config-deployment.md`](../docs/components/config-deployment.md).

## Tech Stack

- **React 18** + **TypeScript**
- **Vite** - Fast build tool with ES modules (`--mode hosted` produces the contractor build)
- **TailwindCSS** - Utility-first styling
- **PDF.js v4.0.379** - Full PDF rendering with canvas
- **Vitest** - Fast unit testing (jsdom)

## Development

```bash
npm run dev            # Start dev server (local mode, http://localhost:3001)
npm run build          # Type-check + production build (local mode)
npm run build:hosted   # Production build for hosted/contractor delivery
npm run preview        # Preview a production build
npm run test           # Run tests in watch mode
npm run test:run       # Run tests once
npm run test:coverage  # Run tests with coverage
```

## Support

Questions? Check the main project README or open an issue.
