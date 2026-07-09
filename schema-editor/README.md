# PDF Schema Editor

Visual editor for PDF form schemas - makes human correction of extracted schemas fast and pleasant!

## Features

✅ **Visual PDF Viewer** - Full PDF rendering with multi-page support and navigation
✅ **Color-Coded Field Overlays** - See field locations with green/yellow/red status borders
✅ **Field List** - Tree view with completion status (complete/review/error)
✅ **Property Editor** - Edit field types, help text, validation, conditional logic
✅ **Real-time Validation** - Instant feedback on schema errors
✅ **Form Selector** - Switch between different PDF/schema pairs
✅ **Progress Tracking** - See completion percentage at a glance
✅ **Page Navigation** - Prev/next buttons, page input, auto-scroll to selected fields
✅ **Zoom Controls** - 50%-200% zoom with +/- buttons
✅ **Hover Tooltips** - See field name and type when hovering over PDF fields
✅ **Auto-save** - Changes tracked, save with Cmd+S

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

1. **Select Form** - Choose a PDF/schema pair from the dropdown
2. **Navigate** - Click fields in the list or PDF viewer
3. **Edit** - Update properties in the right panel:
   - Field type (text, checkbox, radio, etc.)
   - Spoken name (for voice AI)
   - Help text and validation rules
   - Conditional logic (show_if)
4. **Save** - Press Cmd+S to download the edited schema

## Keyboard Shortcuts

- **Cmd+S** / **Ctrl+S** - Save schema (downloads JSON file)

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

The model behind extraction is pluggable -- default is the local `claude` CLI;
set `EXTRACTOR_PROVIDER` to swap it. See EDITOR_GUIDE.md ("Extraction backends").

## Tech Stack

- **React 18** + **TypeScript**
- **Vite** - Fast build tool with ES modules
- **TailwindCSS** - Utility-first styling
- **PDF.js v4.0.379** - Full PDF rendering with canvas
- **Vitest** - Fast unit testing (113 tests passing)

## Development

```bash
npm run dev        # Start dev server
npm run build      # Build for production
npm run preview    # Preview production build
npm run test       # Run tests in watch mode
npm run test:run   # Run tests once
```

## In-app help

The primary contractor-facing guide now lives **inside the editor**: click the
**Help** button in the header to open a sectioned, tier-aware guide (quick start,
getting around, field properties, common tasks, extraction for authors, saving,
and troubleshooting). It is the recommended starting point for new users; this
README and `EDITOR_GUIDE.md` are the developer-facing references.

## Known Limitations

- No keyboard shortcuts for zoom/page navigation yet
- Scroll position not maintained when zooming

## Future Enhancements

- Bulk operations (change type for multiple fields)
- Conditional logic visual graph
- Template system for help text
- Export to multiple formats

## Support

Questions? Check the main project README or open an issue.
