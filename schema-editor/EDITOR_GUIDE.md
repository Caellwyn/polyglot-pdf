# PDF Schema Editor - Complete Guide

**Visual editor for PDF form schemas - built for human-in-the-loop schema extraction**

Version: 1.0.0  
Last Updated: November 5, 2025  
Status: Production Ready - All 5 phases complete (see the test suites under
`src/` for current coverage; run `npm run test:run` for the live count)

---

## Table of Contents

1. [User Guide](#user-guide)
   - [Quick Start](#quick-start)
   - [Interface Overview](#interface-overview)
   - [Common Tasks](#common-tasks)
   - [Tips & Best Practices](#tips--best-practices)
   - [Troubleshooting](#troubleshooting)
2. [Technical Architecture](#technical-architecture)
   - [System Overview](#system-overview)
   - [Component Architecture](#component-architecture)
   - [Data Flow](#data-flow)
   - [PDF Rendering Pipeline](#pdf-rendering-pipeline)
   - [State Management](#state-management)
   - [Type System](#type-system)
3. [Development Phases](#development-phases)
   - [Phase 1: PDF.js Core Setup](#phase-1-pdfjs-core-setup)
   - [Phase 2: Multi-Page Support](#phase-2-multi-page-support)
   - [Phase 3: Field Overlays](#phase-3-field-overlays)
   - [Phase 4: Click Interactions](#phase-4-click-interactions)
   - [Phase 5: Zoom Presets](#phase-5-zoom-presets)
4. [API Reference](#api-reference)

---

# User Guide

> **New here?** The fastest orientation is the **in-app guide**: open the editor
> and click the **Help** button in the header. It walks through quick start,
> navigation, field properties (including what Instructions and Format Hint do),
> common tasks, extraction (author tier), saving, and troubleshooting -- in plain
> language, with the exact on-screen labels. This document is the fuller
> developer-facing reference.

## Why This Exists

Manual JSON editing of PDF schemas is **painful and error-prone**. With 50+ forms to extract and 132+ fields per form, we needed a tool that makes human correction:
- **Fast** (~30 min vs 2-4 hours per form)
- **Visual** (see the PDF + fields side-by-side)
- **Safe** (real-time validation catches errors)
- **Pleasant** (no more scrolling through JSON)

## The Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                    EXTRACTION PIPELINE                       │
└─────────────────────────────────────────────────────────────┘

1. ONBOARD + EXTRACT (in the editor, when run locally)
   ├─→ drag-drop an AcroForm PDF onto the catalogue (creates form-kits/<id>/)
   ├─→ click "Run extraction" on the new kit's card
   └─→ Output: form-kits/<id>/schema.json (a validated draft)

   The button POSTs to the dev server's /api/extract, which runs
   scripts/authoring/extract_form.py on the host (the browser can't spawn the
   model itself). The LLM out-call is behind a provider seam (default: the local
   `claude` CLI, free in-env; swappable by env -- see "Extraction backends"
   below). It is DEV/LOCAL only: a deployed static editor shows the manual step
   instead.

   NOTE: the folder you opened must be the SAME form-kits/ the dev server uses.
   Extraction writes schema.json under the server's own root (FORM_KITS_ROOT,
   default the repo's form-kits/), so opening a copy elsewhere is refused rather
   than silently rewriting the server's copy of the kit (bd polyglot-pdf-ball).
   To work from a folder elsewhere, put BOTH variables on the launcher -- it
   starts two servers that resolve kit ids independently, and setting only one
   unblocks that half while the other keeps refusing (FORM_KITS_ROOT is the Vite
   host / extraction; FORM_KITS_LOCAL_ROOT is the backend / Repair + Regenerate +
   the widget picker). Both are read once at server start, so a restart is needed:
   FORM_KITS_ROOT=/path/to/fk FORM_KITS_LOCAL_ROOT=/path/to/fk ./scripts/run-schema-editor.sh

   You can always run it from a terminal:
   python scripts/authoring/extract_form.py --pdf form-kits/<id>/form.pdf \
       --out form-kits/<id>/schema.json

2. EDIT (Human Review - 20-30 min)
   ├─→ click the now-openable kit card
   ├─→ Fix field types (radio/checkbox/text)
   ├─→ Add help text + validation
   ├─→ Define conditional logic
   └─→ Save (Cmd/Ctrl+S)

3. MARK COMPLETE
   └─→ "Mark complete" on the card -> eligible for deploy (status gate)
```

## Quick Start

### Launch the Editor

```bash
# From project root
./scripts/run-schema-editor.sh
```

Opens at http://localhost:3001

### Hosted mode (the contractor workspace)

A hosted build (`npm run build:hosted`, `VITE_DELIVERY_MODE=hosted` from
`.env.hosted`) swaps the local-folder front door for the backend's token-gated
`/api/editor/*` routes over the shared form-kits store (bd polyglot-pdf-92qe.2):

1. Open the hosted URL and enter your **access code** (asked once per browser).
   The code determines your tier: *editor* (review/polish the provided forms)
   or *author* (additionally: **Add a form (PDF)** uploads a blank AcroForm PDF
   into the shared workspace, and **Run extraction** on a schemaless card runs
   the PDF -> schema pipeline on the server -- takes a few minutes, with an
   elapsed counter; optionally attach the form's official instructions PDF
   first to enrich the per-field help text).
2. The catalogue lists every kit in the shared workspace -- drafts included
   (drafts ARE the work list). Open a card, edit exactly as in local mode.
3. **Cmd/Ctrl+S** saves back to the shared store (watch for the `Saving...` ->
   `Saved` header state). **Mark complete** promotes the kit; the server
   validates the schema against the form contract first and refuses with the
   reason if it's broken. Completed kits reach the voice app on the
   maintainer's next deploy.
4. If your code stops working (rotated), the editor drops back to the code
   screen -- enter the new one. Your unsaved edits survive the round trip.

Maintainer note on codes: hand codes out via the entry prompt, never by baking
`VITE_EDITOR_TOKEN` into a build -- any baked value (from `.env.hosted` or the
shell env) is compiled in plaintext into the served JS bundle, readable by
anyone who opens the site. Rotate a code by updating the backend secret; every
open session drops to the code screen on its next request.

Maintainer runbook (sharing + publishing, bd 92qe.4):

1. **Deploy the editor site**: `./deploy-editor.sh` (one-time setup -- site
   create, target mapping, the two token secrets, the bucket write grant -- is
   documented in that script's header). The voice-app deploy never touches the
   editor site (`deploy-all.sh` is pinned to `hosting:app`).
2. **Share access**: send a contractor the editor URL plus ONE code --
   the *editor* code for polish-only work, the *author* code to also upload
   PDFs and run extraction. Codes live in Secret Manager
   (`schema-editor-token` / `schema-author-token`); rotate by updating the
   secret and redeploying the backend.
3. **Publish contractor work**: `./scripts/pull-form-kits.sh` syncs the shared
   bucket DOWN into your local `form-kits/` (local-only kits are preserved);
   review the diff in git, then run the normal deploy -- only
   `status: complete` kits ship to the voice app. Without the pull, a kit that
   exists only in the bucket drops off the served list on your next deploy.

Local mode (everything below) is unchanged; the two modes never mix in one
build.

### Open a Form (the catalogue)

The front door is the **form catalogue** -- it reads your local `form-kits/`
directory directly (File System Access API; Chrome/Edge):

1. Click **Open form-kits folder** and pick your `form-kits/` directory.
2. The catalogue lists every kit as a card, showing its status badge
   (draft / complete), a **review-progress %** bar (how much of the human review
   is done), and an aggregate overview ("N forms - X complete - Y in progress").
3. Click a card to open that kit -- PDF on the left, fields in the center,
   properties on the right, validation panel at the bottom.
4. To onboard a NEW form, **drag-drop an AcroForm PDF** onto the catalogue; it
   creates a `form-kits/<id>/` (status:draft) with no schema yet.
5. On the new (schemaless) card, click **Run extraction** to produce its
   `schema.json` in place, then open it to review. (The button appears only when
   the editor is run locally via `npm run dev` / `run-schema-editor.sh`, which
   provides the host-side extraction endpoint; a deployed static editor shows a
   "run the extractor" hint instead -- run the terminal command above.)

(If the browser lacks the directory API, a legacy hardcoded form dropdown shows
as a fallback.)

### Extraction backends (the provider seam)

The PDF -> schema model call is selected behind a provider seam
(`scripts/bakeoff/llm_providers.py`):

- **Default:** the local `claude` CLI (free in the maintainer's environment).
- **`EXTRACTOR_PROVIDER=gemini`** routes to the paid google-genai SDK on
  **Vertex** (ADC + `GOOGLE_CLOUD_PROJECT`, so the spend lands on the tracked
  billing project). There is no AI Studio / `GEMINI_API_KEY` path -- that gate
  is closed (bd `polyglot-pdf-f3lm`). **You MUST also set `EXTRACTOR_MODEL` to a
  `gemini-*` model** (e.g. `EXTRACTOR_MODEL=gemini-2.5-flash`) -- otherwise the
  default `claude-opus-5` would be sent to Gemini and rejected. The button
  forwards `EXTRACTOR_MODEL` to the extractor's `--model`.
- Otherwise the model name dispatches (`gemini*` -> Gemini; everything else ->
  the CLI).

Other env knobs the button honors:
- **`EXTRACTOR_MODEL`** -- forwarded to `extract_form.py --model` (provider swap).
- **`EXTRACTOR_PYTHON`** -- explicit interpreter path (else the repo's
  `backend/.venv` is auto-resolved, incl. from a git worktree via the main
  checkout, since the venv lives only in the main repo).

The seam is the swap point for a remote/hosted or better model later (register a
provider, select it by env) -- no edit to `extract_form.py` or its callers. The
in-editor button stays dev/local regardless; a hosted extraction service is
separate, future work.

### Edit Fields

**Click any field** in the list or on the PDF to edit:

- **Field Type** - Change text/radio/checkbox/etc.
- **Spoken Name** - User-friendly name for voice AI
- **Help Text** - Instructions for users
- **Validation** - Patterns, formats, constraints
- **Conditional Logic** - `show_if` (conditional visibility) and `require_if` (conditionally required)

### Move Through the Fields Fast

The review loop has its own navigation (works in local and hosted mode):

- **Next to review** (button above the field list) or **N** -- jump to the
  next field whose icon is yellow/red, wrapping past the end; a search filter
  narrows what it cycles through.
- **Arrow Up / Arrow Down** -- step through the visible field list.
- **Esc** -- deselect (shows the form-level metadata panel).
- None of these fire while you are typing in a text box.

A save/reload failure shows as a red banner above the editor -- your work and
the open form stay untouched; fix the issue (or dismiss) and save again.
Hosted sessions also get a one-time 3-step guide; reopen it any time with the
header's **Help** button.

### Save Your Work

- **Cmd+S** (Mac) or **Ctrl+S** (Windows/Linux)
- Saves **in place** to the open kit's own `schema.json` (File System Access; no
  re-prompt after the first grant). **Save As...** writes to a picked file instead.
- A kit opened via the legacy fallback (no directory API) downloads
  `{form}_edited.json` to copy into place manually.

## Interface Overview

### Layout

```
┌──────────────────────────────────────────────────────────────┐
│ Header: Form Selector | Save Button                          │
├─────────────┬─────────────┬──────────────────────────────────┤
│             │             │                                  │
│ PDF VIEWER  │ FIELD LIST  │   FIELD EDITOR                   │
│             │             │                                  │
│ • Zoom      │ ⊞ Part 1    │   Field Type: [text ▼]          │
│ • Navigate  │   🟢 field1 │   Spoken Name: ___________      │
│ • Overlays  │   🟡 field2 │   Section: [Part 1 ▼]          │
│             │   🔴 field3 │   ☐ Required ☐ Read Only       │
│             │             │                                  │
│             │ ⊞ Part 2    │   Help Text:                     │
│             │   ...       │   ┌──────────────────────┐       │
│             │             │   │                      │       │
│             │             │   └──────────────────────┘       │
│             │             │                                  │
│             │             │   Validation:                    │
│             │             │   Pattern: ^\d{7,9}$            │
│             │             │                                  │
├─────────────┴─────────────┴──────────────────────────────────┤
│ VALIDATION PANEL                                             │
│ Progress: 67% | 89 complete, 43 review, 132 total           │
│ ▓▓▓▓▓▓▓▓▓▓░░░░░░                                            │
└──────────────────────────────────────────────────────────────┘
```

### PDF Viewer Controls

**Toolbar** (top of PDF viewer):
```
┌─────────────────────────────────────────────────────────────┐
│ ← → | Page [1] of 9 | 3 fields | Zoom: 100% [Fit W][Fit P][-][+] │
└─────────────────────────────────────────────────────────────┘
```

- **← →** - Navigate between pages
- **Page input** - Jump to specific page (type page number)
- **Field count** - Number of fields with PDF positions
- **Zoom percentage** - Current zoom level (50% - 200%)
- **Fit Width** - Scale page to fit container width
- **Fit Page** - Scale entire page to fit viewport
- **- / +** - Zoom out/in by 25%

**Field Overlays on PDF**:
- 🟢 **Green border** - Complete (all required info filled)
- 🟡 **Yellow border** - Needs review (missing help text or spoken name)
- 🔴 **Red border** - Has errors (missing required properties)
- **Thick border** - Currently selected field (3px vs 2px)
- **Hover** - Shows tooltip with field name and type
- **Click** - Selects field for editing

### Field List

**Search / filter** (top of the list):
- Type any part of a field's **id**, **spoken name**, or **PDF field name** to
  filter the tree to matches (case-insensitive substring).
- Section grouping is preserved while filtering; sections with no match are hidden
  and matching sections auto-expand. The "x" (or clearing the box) restores the
  full list.

**Section grouping**:
- Click section header to expand/collapse
- Fields grouped by form sections
- Icons show field status (🟢🟡🔴)
- The count badge shows `matches/total` while filtering, `total` otherwise

**Field selection**:
- Click field to select
- Selected field highlighted
- PDF auto-scrolls to field's page
- PDF overlay shows with thick border

### Field Editor

**Properties displayed**:
- Basic info (type, section, required, read-only)
- Spoken name (for voice AI)
- Help text (instructions + format hint)
- Validation rules (pattern, format preset)
- Options (for select/radio fields)
- Conditional logic (show_if rules)

**All changes auto-tracked** - unsaved changes warning appears

### Validation Panel

**Progress tracking**:
- Progress bar (% complete)
- Status counts (complete / review / total)
- Validation errors (schema issues)
- Reference warnings (broken field references)

### Field Status Icons

- 🟢 **Complete** - All required info filled
- 🟡 **Needs Review** - Missing help text or spoken name
- 🔴 **Error** - Missing required properties

### Keyboard Shortcuts

- **Cmd/Ctrl + S** - Save schema
- **Cmd/Ctrl + Z** / **Cmd/Ctrl + Shift + Z** - Undo / redo
- **N** - Jump to the next field needing review
- **Arrow Up / Arrow Down** - Step through the visible field list
- **Escape** - Deselect the current field

## Common Tasks

### Fix Field Types

Many fields are initially detected incorrectly:

1. Select field in list (or click overlay on PDF)
2. Change "Field Type" dropdown
3. Check if options appear (for radio/select)
4. Save

**Common Fixes:**
- `signature` → `text` (most signature fields are actually text)
- Individual checkboxes → `radio` (mutually exclusive groups)
- `text` → `date` (date fields not caught by pattern)

### Add Help Text

All extracted schemas have placeholder help text:

1. Select field
2. Scroll to "Help & Guidance"
3. Fill in "Instructions" (what to enter)
4. Add "Format Hint" (e.g., "MM/DD/YYYY")

**Good Example:**
> "Your alien registration number (A-Number) is a 7-9 digit number found on your green card. It begins with an 'A'."

**Bad Example:**
> "[TODO: Add help text for alien registration number]"

### Define Conditional Logic

For fields that only show based on another field:

1. Select the dependent field
2. Scroll to "Conditional Logic"
3. Click "+ Add Conditional Logic"
4. Select trigger field from dropdown
5. Choose operator (equals, is_checked, etc.)
6. Enter expected value

**Example:** "Family name on card" only shows if "Name changed" = Yes

### Find a Field

On a large form, use the **search box** at the top of the field list rather than
scrolling: type part of the field's id, spoken name, or PDF field name. The list
filters to matches (grouping preserved); selecting a result selects that field
across the PDF, list, and editor. Clear the box to restore the full list.

### Mark a Form Complete (deploy gating)

A kit is **draft** until you promote it. On each catalogue card:
- **Mark complete** -- sets `metadata.json` status to `complete`. Only complete
  kits are uploaded by the deploy scripts (the draft-leak gate); a draft stays
  local and git-backed.
- **Revert to draft** -- the inverse, on a complete kit.

Promote a form only after its review % is where you want it -- once complete, the
next deploy ships it to the voice app.

### Navigate Large Forms

**Using PDF Viewer**:
- Scroll vertically to view all pages
- Use ← → buttons to navigate by page
- Type page number to jump directly
- Click "Fit Width" for optimal reading width
- Click "Fit Page" to see entire page at once

**Using Field List**:
- **Search** to jump straight to a field by name (see "Find a Field" above)
- Click any field → PDF auto-scrolls to that page
- Collapse sections to reduce clutter
- Status icons show completion at a glance

### Zoom and Fit

**Manual Zoom**:
- Click **+** to zoom in (25% increments)
- Click **-** to zoom out (25% increments)
- Range: 50% - 200%

**Fit Presets**:
- **Fit Width** - Scales page to fill horizontal space (~120% typical)
- **Fit Page** - Scales entire page to fit viewport (~90% typical)
- Both presets respect 50% - 200% bounds

**Use Cases**:
- Start with **Fit Width** for comfortable reading
- Use **Fit Page** to see entire page layout
- Zoom in to **150-200%** for detailed inspection
- Zoom out to **50-75%** for overview of multi-page sections

### Consolidate Checkbox Groups

Some forms have checkbox groups that should be radio buttons:

**Manual Method (for now):**
1. Note all checkboxes in group (e.g., P2_checkbox1[0-2])
2. Delete extra checkboxes
3. Change remaining to type: radio
4. Add options manually

**In the field list (shipped):** tick two or more checkbox/radio fields in the
same section, then click **Merge (several)** for a multi-select checkbox group or
**Merge (exactly one)** for a single-choice radio. Select the resulting group and
click **Ungroup** in the editor to split it back.

## Tips & Best Practices

### Efficient Editing

1. **Sort by status** - Fix errors first, then reviews, then complete
2. **Use templates** - Copy help text from similar fields (coming soon)
3. **Batch edits** - Group similar fields, edit properties together (coming soon)
4. **Save often** - Cmd+S is your friend

### Help Text Guidelines

**Be specific and helpful**:
- Explain what the field is for
- Give examples where appropriate
- Mention where to find the information
- Include format hints for structured data

**Common patterns**:
- Identification numbers: Explain format, give example, mention where to find it
- Dates: Specify exact format (MM/DD/YYYY vs DD/MM/YYYY)
- Names: Clarify which name (legal, maiden, current, etc.)
- Addresses: Specify if current or previous, US or international

### Validation Patterns

Common regex patterns:
- **A-Number:** `^\d{7,9}$`
- **SSN:** `^\d{3}-?\d{2}-?\d{4}$`
- **Date:** Use `format_preset` instead of pattern
- **Email:** Built-in browser validation
- **Phone:** `^\d{10}$` or `^\(\d{3}\) \d{3}-\d{4}$`

### Conditional Logic

Keep it simple:
- **One trigger per field** - Multiple triggers get complex fast
- **Test your logic** - Fill out a form to verify show_if works
- **Document edge cases** - Add notes in help text

### Visual Inspection

**Use the PDF overlays**:
- Green borders = fields ready for production
- Yellow borders = need your attention
- Red borders = must fix before deploying
- Click overlays to select fields instantly
- Hover to see field names without selecting

## Troubleshooting

### Editor Won't Start - PostCSS/Module Errors

If you see errors about `module is not defined` or PostCSS config:

```bash
cd schema-editor
# Ensure postcss.config.js uses ES module syntax:
# export default { ... } not module.exports = { ... }
```

The `package.json` has `"type": "module"`, so all `.js` files must use ES module syntax.

### Editor Won't Start - Tailwind Class Errors

If you see errors about missing Tailwind classes (e.g., `border-primary-400`):

1. Check `tailwind.config.js` has all color shades defined (50, 100, 400, 500, 600, 700)
2. Ensure the class is using standard Tailwind naming
3. For custom classes, define them in `@layer` directives

### Schemas Won't Load - 404 or HTML Response

If schemas fail to load with "Unexpected token '<', is not valid JSON":

1. Ensure schema files are in `schema-editor/public/schemas/` folder
2. Check paths in `schemaLoader.ts` use `/schemas/...` not `../...`
3. Restart the dev server after copying files

### PDF Won't Load

If PDF doesn't render:

1. Check browser console for PDF.js errors
2. Verify PDF file exists in `public/schemas/{form}/` folder
3. Check PDF path in `schemaLoader.ts` is correct
4. Try refreshing the page

### Field Overlays Not Appearing

If overlays don't show on PDF:

1. Check that fields have `pdf_position` data with page numbers
2. Verify page dimensions have loaded (may take 1-2 seconds on first render)
3. Check browser console for coordinate transformation errors
4. Try zooming - overlays update with zoom changes

### Changes Not Saving

- Check browser console for errors
- Verify you clicked "Save" or pressed Cmd+S
- Check Downloads folder for `_edited.json` file
- Ensure browser allows downloads

### Validation Errors

Red errors in validation panel indicate schema issues:
- **Duplicate IDs** - Field IDs must be unique
- **Missing sections** - Field references non-existent section
- **Broken references** - show_if or require_if reference a missing field

Fix by:
1. Click on error to see field ID
2. Find field in list
3. Fix the property causing issue

---

# Technical Architecture

## System Overview

The PDF Schema Editor is a single-page React application built with TypeScript and Vite. It provides a visual interface for editing PDF form schemas extracted by the automated extraction pipeline.

**Technology Stack**:
- **React 18.3** - UI framework with hooks
- **TypeScript 5.5** - Type safety and tooling
- **Vite 5.4** - Fast dev server and build tool
- **PDF.js 4.0.379** - PDF rendering engine
- **TailwindCSS 3.4** - Utility-first styling
- **Vitest 4.0** - Unit and integration testing

**Browser Compatibility**:
- Chrome/Edge (Chromium) - Primary target
- Firefox - Supported
- Safari - Supported
- Mobile browsers - Not optimized

## Component Architecture

### Component Hierarchy

```
App (Root)
├── FormSelector
│   └── Dropdown to choose form
├── PDFViewer
│   ├── usePDFDocument (hook)
│   ├── PDFPage (renders each page)
│   │   └── Canvas element
│   └── FieldOverlay (one per field)
│       └── Colored border + tooltip
├── FieldList
│   └── Nested sections and fields
├── FieldEditor
│   └── Property inputs for selected field
└── ValidationPanel
    └── Progress + errors
```

### Component Details

#### `App.tsx` (Root Component)

**Responsibilities**:
- Top-level state management (schema, selectedFieldId, selectedForm)
- Loading and saving schemas
- Keyboard shortcuts (Cmd+S)
- Unsaved changes warning
- Coordinating child components

**State**:
```typescript
const [selectedForm, setSelectedForm] = useState<FormConfig | null>(null);
const [schema, setSchema] = useState<FormSchema | null>(null);
const [selectedFieldId, setSelectedFieldId] = useState<string | null>(null);
const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
```

**Key Methods**:
- `handleSelectForm()` - Load schema from file
- `handleUpdateField()` - Update single field in schema
- `handleSave()` - Download edited schema as JSON

#### `FormSelector.tsx`

**Responsibilities**:
- Dropdown menu to choose form
- Displays form metadata (number, title, edition date)
- Triggers schema loading

**Props**:
```typescript
interface FormSelectorProps {
  onSelectForm: (form: FormConfig) => void;
}
```

**Data Source**: `AVAILABLE_FORMS` from `schemaLoader.ts`

#### `PDFViewer.tsx`

**Responsibilities**:
- Load and render PDF document
- Manage zoom and navigation
- Render field overlays
- Handle field selection from PDF clicks

**Props**:
```typescript
interface PDFViewerProps {
  pdfPath: string;
  schema: FormSchema;
  selectedFieldId: string | null;
  onSelectField: (fieldId: string) => void;
}
```

**State**:
```typescript
const [scale, setScale] = useState(1.0);          // 0.5 - 2.0
const [currentPage, setCurrentPage] = useState(1); // 1 - numPages
const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());
const pageDimensions = useRef<Map<number, { width, height }>>(new Map());
```

**Key Features**:
- Multi-page vertical scrolling layout
- Zoom controls (50% - 200%)
- Fit Width / Fit Page presets
- Page navigation (prev/next, jump to page)
- Auto-scroll to field's page when selected
- Field overlays with color-coded borders
- Hover tooltips on overlays
- Click-to-select fields

#### `PDFPage.tsx`

**Responsibilities**:
- Render single PDF page to canvas
- Handle page loading and dimension tracking
- Cancel in-flight renders on scale changes

**Props**:
```typescript
interface PDFPageProps {
  document: PDFDocumentProxy;
  pageNumber: number;
  scale: number;
  onPageLoad?: (page: PDFPageProxy) => void;
}
```

**Rendering Process**:
1. Get page from document
2. Calculate viewport at current scale
3. Set canvas dimensions
4. Render page to canvas context
5. Call `onPageLoad` callback with page

#### `FieldOverlay.tsx`

**Responsibilities**:
- Render colored border over PDF field
- Show tooltip on hover
- Handle click to select field
- Transform PDF coordinates to screen coordinates

**Props**:
```typescript
interface FieldOverlayProps {
  field: FormField;
  pageHeight: number;
  scale: number;
  isSelected: boolean;
  onClick: () => void;
}
```

**Color Logic**:
```typescript
const status = checkFieldComplete(field);
if (status.isComplete) {
  // Green border
} else if (status.needsReview) {
  // Yellow border
} else {
  // Red border (has errors)
}
```

**Border Styles**:
- Normal: 2px border
- Selected: 3px border (thicker)
- Z-index: 10 (normal), 20 (selected)

#### `FieldList.tsx`

**Responsibilities**:
- Display fields grouped by section
- Show field status icons (🟢🟡🔴)
- Handle field selection
- Expand/collapse sections

**Props**:
```typescript
interface FieldListProps {
  schema: FormSchema;
  selectedFieldId: string | null;
  onSelectField: (fieldId: string) => void;
}
```

**State**:
```typescript
const [expandedSections, setExpandedSections] = useState<Set<string>>();
```

**Rendering Logic**:
1. Group fields by `section_id`
2. Render sections with expand/collapse toggle
3. Render fields within each section
4. Show status icon based on `checkFieldComplete()`

#### `FieldEditor.tsx`

**Responsibilities**:
- Display and edit properties of selected field
- Handle all field types
- Update schema on changes
- Validate inputs

**Props**:
```typescript
interface FieldEditorProps {
  field: FormField | null;
  schema: FormSchema;
  onUpdateField: (field: FormField) => void;
}
```

**Sections**:
- Basic Info (type, section, required, read-only)
- Display (spoken name, label)
- Help & Guidance (instructions, format hint)
- Validation Rules (pattern, format preset)
- Options (for select/radio fields)
- Conditional Logic (show_if rules)

#### `ValidationPanel.tsx`

**Responsibilities**:
- Show completion progress
- Display validation errors
- Track field statuses

**Props**:
```typescript
interface ValidationPanelProps {
  schema: FormSchema;
  selectedFieldId: string | null;
}
```

**Metrics Displayed**:
- Progress percentage
- Complete count
- Needs review count
- Total field count
- Validation errors

## Data Flow

### Schema Loading Flow

```
User selects form
  ↓
FormSelector.onSelectForm(form)
  ↓
App.handleSelectForm(form)
  ↓
loadSchema(form.schemaPath) ← Fetch JSON from public/
  ↓
setSchema(loadedSchema)
  ↓
Re-render with loaded schema
  ↓
PDFViewer loads PDF from form.pdfPath
FieldList displays fields
ValidationPanel calculates progress
```

### Field Selection Flow

**From Field List**:
```
User clicks field in list
  ↓
FieldList.onSelectField(fieldId)
  ↓
App.setSelectedFieldId(fieldId)
  ↓
Re-render with selection:
  - PDFViewer scrolls to field's page
  - FieldOverlay shows thick border
  - FieldEditor displays field properties
```

**From PDF Overlay**:
```
User clicks overlay on PDF
  ↓
FieldOverlay.onClick()
  ↓
PDFViewer.onSelectField(fieldId)
  ↓
App.setSelectedFieldId(fieldId)
  ↓
Re-render with selection:
  - FieldList highlights field
  - FieldOverlay shows thick border
  - FieldEditor displays field properties
```

### Field Update Flow

```
User edits property in FieldEditor
  ↓
Input onChange event
  ↓
FieldEditor updates local copy
  ↓
FieldEditor.onUpdateField(updatedField)
  ↓
App.handleUpdateField(updatedField)
  ↓
setSchema with field replaced
setHasUnsavedChanges(true)
  ↓
Re-render with updated field:
  - FieldList updates icon if status changed
  - FieldOverlay updates color if status changed
  - ValidationPanel recalculates progress
```

### Save Flow

```
User presses Cmd+S or clicks Save
  ↓
App.handleSave()
  ↓
saveSchema(schema, filename)
  ↓
JSON.stringify(schema, null, 2)
Create Blob
Create download link
Trigger download
  ↓
setHasUnsavedChanges(false)
Show success alert
```

## PDF Rendering Pipeline

### Phase 1: PDF.js Initialization

**Worker Setup** (`pdfWorker.ts`):
```typescript
import * as pdfjsLib from 'pdfjs-dist';

export const initPDFWorker = () => {
  if (!pdfjsLib.GlobalWorkerOptions.workerSrc) {
    pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
      'pdfjs-dist/build/pdf.worker.mjs',
      import.meta.url
    ).toString();
  }
};
```

**Why this works**:
- Vite handles `import.meta.url` correctly in dev and production
- Worker loads from `node_modules` in dev
- Worker bundles separately in production

### Phase 2: Document Loading

**usePDFDocument Hook** (`usePDFDocument.ts`):
```typescript
const usePDFDocument = (pdfUrl: string | null) => {
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!pdfUrl) return;

    let cancelled = false;
    setIsLoading(true);
    initPDFWorker();

    getDocument(pdfUrl)
      .promise.then((pdf) => {
        if (!cancelled) {
          setDocument(pdf);
          setNumPages(pdf.numPages);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
      document?.destroy();
    };
  }, [pdfUrl]);

  return { document, numPages, isLoading, error };
};
```

**Lifecycle**:
1. Component mounts → Effect runs
2. `initPDFWorker()` sets up worker
3. `getDocument()` loads PDF
4. Promise resolves → `setDocument(pdf)`
5. Component unmounts → `document.destroy()`

### Phase 3: Page Rendering

**PDFPage Component** (`PDFPage.tsx`):
```typescript
const PDFPage: React.FC<PDFPageProps> = ({ document, pageNumber, scale, onPageLoad }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let renderTask: RenderTask | null = null;

    document.getPage(pageNumber).then((page) => {
      // Call onPageLoad callback
      onPageLoad?.(page);

      const viewport = page.getViewport({ scale });
      const canvas = canvasRef.current;
      if (!canvas) return;

      canvas.width = viewport.width;
      canvas.height = viewport.height;

      const context = canvas.getContext('2d');
      if (!context) return;

      renderTask = page.render({ canvasContext: context, viewport });

      return renderTask.promise;
    });

    return () => {
      renderTask?.cancel();
    };
  }, [document, pageNumber, scale, onPageLoad]);

  return <canvas ref={canvasRef} className="shadow-lg" />;
};
```

**Rendering Steps**:
1. Get page from document
2. Calculate viewport (width, height at scale)
3. Set canvas dimensions to match viewport
4. Get 2D context
5. Render page to context
6. Return cleanup function to cancel in-flight renders

### Phase 4: Coordinate Transformation

**PDF vs Screen Coordinates** (`pdfCoordinates.ts`):

```
PDF Coordinates:        Screen Coordinates:
┌──────────────────┐   ┌──────────────────┐
│ y=792 (top)     │   │ y=0 (top)        │
│                  │   │                  │
│  ┌────┐ Field   │   │  ┌────┐ Field   │
│  │    │ y=700   │   │  │    │ y=62    │
│  └────┘ h=30    │   │  └────┘ h=30    │
│                  │   │                  │
│ y=0 (bottom)    │   │ y=792 (bottom)  │
└──────────────────┘   └──────────────────┘
```

**Transformation Function**:
```typescript
export const pdfToScreenCoords = (
  pdfRect: { x: number; y: number; width: number; height: number },
  pageHeight: number,
  scale: number = 1.0
) => {
  return {
    x: pdfRect.x * scale,
    y: (pageHeight - pdfRect.y - pdfRect.height) * scale,
    width: pdfRect.width * scale,
    height: pdfRect.height * scale,
  };
};
```

**Why Y-axis inversion**:
- PDF measures from bottom-left origin
- Browser measures from top-left origin
- Formula: `screenY = pageHeight - pdfY - fieldHeight`
- Then multiply by scale for zoom

### Phase 5: Overlay Rendering

**FieldOverlay Positioning**:
```typescript
const FieldOverlay: React.FC<FieldOverlayProps> = ({ field, pageHeight, scale, isSelected, onClick }) => {
  if (!field.pdf_position || !hasValidCoordinates(field.pdf_position)) {
    return null;
  }

  const screenPos = pdfToScreenCoords(
    {
      x: field.pdf_position.x || 0,
      y: field.pdf_position.y || 0,
      width: field.pdf_position.width || 0,
      height: field.pdf_position.height || 0,
    },
    pageHeight,
    scale
  );

  return (
    <div
      style={{
        position: 'absolute',
        left: `${screenPos.x}px`,
        top: `${screenPos.y}px`,
        width: `${screenPos.width}px`,
        height: `${screenPos.height}px`,
        border: `${isSelected ? 3 : 2}px solid ${borderColor}`,
        zIndex: isSelected ? 20 : 10,
        pointerEvents: 'auto',
        cursor: 'pointer',
      }}
      onClick={onClick}
    />
  );
};
```

**Container Layout**:
```tsx
{/* For each page */}
<div className="relative">
  {/* PDF Canvas */}
  <PDFPage ... />

  {/* Overlay Container */}
  <div className="absolute top-0 left-0 w-full h-full pointer-events-none">
    {/* Individual Overlays */}
    {fieldsOnThisPage.map(field => (
      <FieldOverlay field={field} ... />
    ))}
  </div>
</div>
```

**Why `pointer-events-none` on container**:
- Allows clicks to pass through to PDF canvas
- Individual overlays set `pointer-events: auto`
- Only overlay rectangles are clickable

## State Management

### App-Level State

**Schema State**:
```typescript
const [schema, setSchema] = useState<FormSchema | null>(null);
```
- Loaded from JSON file
- Updated immutably on field changes
- Saved to file on Cmd+S

**Selection State**:
```typescript
const [selectedFieldId, setSelectedFieldId] = useState<string | null>(null);
```
- Tracks currently selected field
- Drives highlighting in FieldList and PDFViewer
- Determines what FieldEditor displays

**UI State**:
```typescript
const [selectedForm, setSelectedForm] = useState<FormConfig | null>(null);
const [loading, setLoading] = useState(false);
const [error, setError] = useState<string | null>(null);
const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
```

### Component-Level State

**PDFViewer State**:
```typescript
const [scale, setScale] = useState(1.0);          // Zoom level
const [currentPage, setCurrentPage] = useState(1); // Current page
const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map()); // Page elements
const pageDimensions = useRef<Map<number, { width, height }>>(new Map()); // Page sizes
```

**FieldList State**:
```typescript
const [expandedSections, setExpandedSections] = useState<Set<string>>();
```

**FieldOverlay State**:
```typescript
const [isHovered, setIsHovered] = useState(false);
```

### State Flow Patterns

**Lifting State Up**:
- `selectedFieldId` lives in App
- Passed down to PDFViewer, FieldList, FieldEditor
- Updated via callback props

**Derived State**:
- `selectedField` computed from `schema` and `selectedFieldId`
- `sectionedFields` computed from `schema.sections` and `schema.fields`
- `validationErrors` computed from `schema` in ValidationPanel

**Ref Storage**:
- `pageRefs` - DOM elements (can't be in state)
- `pageDimensions` - Stable values that don't trigger re-renders
- `canvasRef` - Canvas element for rendering

## Type System

### Core Schema Types

**FormSchema** (Root):
```typescript
interface FormSchema {
  source: 'pdf';
  form_metadata: FormMetadata;
  parts: FormPart[];
  sections: FormSection[];
  fields: FormField[];
  extraction_notes?: any;
}
```

**FormField** (Primary Entity):
```typescript
interface FormField {
  id: string;                      // Unique identifier
  name: string;                    // PDF field name (legacy)
  type: FieldType;                 // text | radio | checkbox | etc.
  section_id?: string;             // Parent section
  pdf_field_name: string;          // Actual PDF widget name
  consolidated_widgets?: string[]; // For merged fields
  label?: string;                  // Display label
  read_only: boolean;
  required: boolean;
  spoken_name?: string;            // For voice AI
  help?: FieldHelp;                // Instructions + format hint
  validation?: ValidationRules;    // Patterns and constraints
  options?: FieldOption[];         // For select/radio
  show_if?: FieldCondition;        // Show this field only when the condition holds
  require_if?: FieldCondition;     // Make this field required when the condition holds
  pdf_position?: PDFPosition;      // Coordinates on PDF
  question_number?: string;        // Order in form
  // ... other properties
}
```

**PDFPosition** (Coordinates):
```typescript
interface PDFPosition {
  page: number;    // 1-indexed page number
  x?: number;      // Left edge (PDF points)
  y?: number;      // Bottom edge (PDF points)
  width?: number;  // Width (PDF points)
  height?: number; // Height (PDF points)
}
```

**FieldCondition** (`show_if` / `require_if`):
```typescript
// A field's show_if / require_if is TARGET-SIDE: the dependent field itself
// carries the condition, not the controlling field. Two shapes are accepted:
// a single atom, OR a one-level composite of all_of/any_of/none_of.
type FieldCondition = ConditionalDisplay | CompositeConditionalDisplay;

interface ConditionalDisplay {          // a single atomic condition
  field: string;                        // id of the controlling field
  operator: ConditionalOperator;        // see below
  value?: string | number | boolean | Array<string | number | boolean>;
}

interface CompositeConditionalDisplay { // "(A AND B) AND NOT C"
  all_of?: ConditionalDisplay[];        // every atom must hold
  any_of?: ConditionalDisplay[];        // at least one must hold
  none_of?: ConditionalDisplay[];       // none may hold
}

// operators: equals | not_equals | contains | greater_than | less_than |
//   is_checked | is_empty | is_not_empty | in | not_in |
//   includes | not_includes   (the last two test membership in a
//   checkbox_group's selected set)
```

**Authoring conditions (v2).** There is no trigger-side "this field controls those
fields" mechanism -- express dependencies on the DEPENDENT field via `show_if`
(visibility) or `require_if` (make required). Both use the identical shape and
evaluator. A field is `show_if`-hidden until its condition holds; a field is
required when its `require_if` holds. To make a read-only field editable once its
condition reveals it, give it `conditional_behavior.unlock_method:
"flip_readonly_bit"` (a read-only field shown by a condition with no unlock stays
greyed-out -- the editor's lint flags that as `readonly-conditional-no-unlock`).

```json
// "Representative name" is required only when "Filing for someone else?" is Yes:
"require_if": { "field": "filing_for_other", "operator": "equals", "value": "yes" }

// A checkbox_group trigger uses membership (includes), and composites combine atoms:
"show_if": {
  "all_of": [
    { "field": "reason", "operator": "includes", "value": "name_change" },
    { "field": "has_prior_name", "operator": "is_checked" }
  ]
}
```

Here `field` is the controlling field's id and `value` is the value to match under
`operator` (an option `value`/slug, `"Yes"`, `"true"`, etc. -- never a target field
id). Every `field` referenced must be a real field id in the schema -- the editor's
validator flags a dangling reference (a `show_if references non-existent field`
warning), checking composite atoms too and tolerating forward references (a field
declared later in `fields`).

### Validation Types

**FieldStatus** (Computed):
```typescript
interface FieldStatus {
  isComplete: boolean;   // All required info filled
  needsReview: boolean;  // Missing optional but recommended info
  errors: string[];      // Validation error messages
}
```

**Validation Rules**:
```typescript
interface ValidationRules {
  pattern?: string;         // Regex pattern
  format_preset?: string;   // Named format (email, date, etc.)
  min_length?: number;
  max_length?: number;
}
```

### UI Types

**FormConfig** (Dropdown Options):
```typescript
interface FormConfig {
  name: string;        // Display name
  pdfPath: string;     // URL to PDF
  schemaPath: string;  // URL to JSON schema
}
```

**Component Props**:
- All component props are explicitly typed
- No `any` types in public APIs
- Props interfaces co-located with components

### Type Safety Benefits

1. **Autocomplete** - IDE suggests field properties
2. **Refactoring** - Rename detection across codebase
3. **Error Prevention** - Catch typos at compile time
4. **Documentation** - Types serve as inline docs
5. **Testing** - Type-safe mocks and assertions

---

# Development Phases

## Phase 1: PDF.js Core Setup

**Completion Date:** November 5, 2025  
**Duration:** ~2.5 hours  
**Status:** ✅ Complete (19/19 tests passing)

### Objectives

- ✅ PDF.js Worker Configuration
- ✅ PDF Document Loading Hook
- ✅ PDF Page Rendering Component
- ✅ Updated PDFViewer Component
- ✅ Comprehensive Testing

### Implementation

**PDF.js Worker** (`pdfWorker.ts`):
- Uses `new URL(..., import.meta.url)` for Vite compatibility
- Works in both dev and production builds
- Idempotent (safe to call multiple times)

**usePDFDocument Hook** (`usePDFDocument.ts`):
- Manages PDF document lifecycle
- Handles loading states and errors
- Automatic cleanup on unmount

**PDFPage Component** (`PDFPage.tsx`):
- Canvas-based rendering
- Dynamic scaling support
- Cancels in-flight renders on scale changes

**Test Coverage** (19 tests):
- Worker initialization (5 tests)
- Document loading hook (6 tests)
- PDFViewer integration (8 tests)

### Technical Decisions

1. **Worker Configuration**: `import.meta.url` works better with Vite than manual paths
2. **Hook-Based Architecture**: Separation of concerns enables reusability and testing
3. **Static Toolbar**: Fixed position for always-accessible controls
4. **Canvas Rendering**: Native browser support, high quality, efficient performance

### Files Created

- `src/utils/pdfWorker.ts` (47 lines)
- `src/hooks/usePDFDocument.ts` (85 lines)
- `src/components/PDFPage.tsx` (105 lines)
- `src/utils/pdfWorker.test.ts` (59 lines)
- `src/hooks/usePDFDocument.test.ts` (105 lines)
- `src/components/PDFViewer.test.tsx` (225 lines)

## Phase 2: Multi-Page Support

**Completion Date:** November 5, 2025  
**Duration:** ~2 hours  
**Status:** ✅ Complete (34/34 tests passing)

### Objectives

- ✅ Multi-Page Rendering (all pages vertically)
- ✅ Page Navigation Controls (prev/next, jump to page)
- ✅ Auto-Scroll to Field's Page
- ✅ Page Tracking (scroll-based)

### Implementation

**Multi-Page Layout**:
```tsx
{Array.from({ length: numPages }, (_, i) => i + 1).map((pageNum) => (
  <div key={pageNum} ref={(el) => pageRefs.current.set(pageNum, el)}>
    <PDFPage document={document} pageNumber={pageNum} scale={scale} />
    <div className="page-number-label">Page {pageNum}</div>
  </div>
))}
```

**Page Navigation**:
- ← → buttons for prev/next
- Page number input with validation
- "Page X of Y" indicator
- Disabled states at bounds

**Auto-Scroll**:
```typescript
useEffect(() => {
  const field = schema.fields.find(f => f.id === selectedFieldId);
  if (field?.pdf_position?.page) {
    scrollToPage(field.pdf_position.page);
  }
}, [selectedFieldId]);
```

**Scroll Tracking**:
- Monitors scroll events with passive listener
- Calculates which page is most visible
- Updates currentPage state

**Test Coverage** (15 new tests):
- Page navigation controls (7 tests)
- Multi-page rendering (3 tests)
- Auto-scroll to field page (3 tests)
- Page counter display (2 tests)

### Technical Decisions

1. **Ref Management**: `Map<number, HTMLDivElement>` for O(1) lookup by page number
2. **Scroll Optimization**: Passive event listeners for better performance
3. **Smooth Scrolling**: `scrollIntoView({ behavior: 'smooth' })`
4. **Page Tracking**: Visibility-based tracking feels more natural than button-based

### Files Modified

- `src/components/PDFViewer.tsx` (+105 lines)
- `src/components/PDFViewer.phase2.test.tsx` (NEW, 330 lines)

## Phase 3: Field Overlays

**Completion Date:** November 5, 2025  
**Duration:** ~2.5 hours  
**Status:** ✅ Complete (73/73 tests passing)

### Objectives

- ✅ PDF Coordinate Transformation
- ✅ Field Overlay Component
- ✅ Integration with PDFViewer
- ✅ Color-Coded Borders (green/yellow/red)

### Implementation

**Coordinate Transformation**:
```typescript
// PDF coordinates (bottom-left origin) → Screen coordinates (top-left origin)
export const pdfToScreenCoords = (
  pdfRect: { x, y, width, height },
  pageHeight: number,
  scale: number = 1.0
) => ({
  x: pdfRect.x * scale,
  y: (pageHeight - pdfRect.y - pdfRect.height) * scale,
  width: pdfRect.width * scale,
  height: pdfRect.height * scale,
});
```

**Color-Coded Overlays**:
- 🟢 Green: Complete (all required info filled)
- 🟡 Yellow: Needs review (missing help text or spoken name)
- 🔴 Red: Has errors (missing required properties)
- Thick border (3px) for selected fields

**Hover Tooltips**:
- Show field name (spoken_name or id)
- Show field type in brackets [text], [checkbox], etc.
- Positioned above field to avoid covering content

**Test Coverage** (39 new tests):
- Coordinate transformation (22 tests)
- FieldOverlay component (17 tests)

### Technical Decisions

1. **Y-Axis Inversion**: Critical for correct positioning
2. **Test Math Early**: 22 coordinate tests caught edge cases before integration
3. **Separation of Concerns**: FieldOverlay is independent, easy to test and reuse
4. **Page Dimensions**: Store actual dimensions vs assuming US Letter
5. **Z-Index Layering**: Selected overlays need higher z-index

### Files Created

- `src/utils/pdfCoordinates.ts` (140 lines)
- `src/components/FieldOverlay.tsx` (135 lines)
- `src/utils/pdfCoordinates.test.ts` (230 lines)
- `src/components/FieldOverlay.test.tsx` (350 lines)

### Files Modified

- `src/components/PDFViewer.tsx` (+15 lines)

## Phase 4: Click Interactions

**Completion Date:** November 5, 2025  
**Duration:** ~1 hour (documentation and testing)  
**Status:** Complete

### Key Insight

Click functionality was **already integrated in Phase 3** when connecting FieldOverlay components. Phase 4 focused on documenting and testing the workflow.

### Objectives

- ✅ Click-to-Select Fields (already working)
- ✅ Hover Effects (background color, cursor)
- ✅ Tooltips (field name + type)
- ✅ Visual Selection Feedback (thicker border, darker color)
- ✅ Accessibility (title, data attributes)

### Implementation

**Click Handler** (from Phase 3):
```typescript
<FieldOverlay
  field={field}
  isSelected={field.id === selectedFieldId}
  onClick={() => onSelectField(field.id)} // ← Connected in Phase 3
/>
```

**Hover Effects**:
```typescript
const [isHovered, setIsHovered] = useState(false);

<div
  onMouseEnter={() => setIsHovered(true)}
  onMouseLeave={() => setIsHovered(false)}
  style={{
    backgroundColor: isHovered ? bgColor : 'transparent',
    cursor: 'pointer',
  }}
>
  {isHovered && <Tooltip />}
</div>
```

**Accessibility**:
```typescript
<div
  title={field.spoken_name || field.id}
  data-field-id={field.id}
  data-testid={`field-overlay-${field.id}`}
  style={{ cursor: 'pointer' }}
/>
```

**Test Coverage** (bd polyglot-pdf-840i): `PDFViewer.phase4.test.tsx` is PRESENT and
holds real tests -- its original 13 `expect(true)` placeholders (which documented
the workflow but ran no production code) were removed and the file rebuilt.
Click/hover/selection behavior on the overlay in isolation is covered with real
`fireEvent` assertions in `FieldOverlay.test.tsx`; the PDFViewer-to-FieldOverlay
WIRING -- that `PDFViewer` passes `onClick={() => onSelectField(field.id)}` and
drives `isSelected` from `selectedFieldId` -- is covered by the rebuilt
`PDFViewer.phase4.test.tsx`.

### Files

- `src/components/PDFViewer.phase4.test.tsx` -- click-to-select wiring regression
  (rewritten under bd 840i; the prior all-`expect(true)` version was removed)

## Phase 5: Zoom Presets

**Completion Date:** November 5, 2025  
**Duration:** ~2 hours  
**Status:** Complete

### Objectives

- ✅ Fit Width Button
- ✅ Fit Page Button
- ✅ Scale Calculation (dynamic based on container)
- ✅ Bounds Clamping (0.5 - 2.0)
- ✅ Safety Checks

### Implementation

**Fit Width**:
```typescript
const handleFitWidth = () => {
  const firstPageDims = pageDimensions.current.get(1);
  const scrollContainer = containerRef.current.querySelector('.overflow-auto');
  
  const containerWidth = scrollContainer.clientWidth - 64; // p-8 padding
  const pageWidth = firstPageDims.width;
  
  const newScale = Math.max(0.5, Math.min(2.0, containerWidth / pageWidth));
  setScale(newScale);
};
```

**Fit Page**:
```typescript
const handleFitPage = () => {
  const firstPageDims = pageDimensions.current.get(1);
  const scrollContainer = containerRef.current.querySelector('.overflow-auto');
  
  const containerWidth = scrollContainer.clientWidth - 64;
  const containerHeight = scrollContainer.clientHeight - 64;
  const pageWidth = firstPageDims.width;
  const pageHeight = firstPageDims.height;
  
  const scaleForWidth = containerWidth / pageWidth;
  const scaleForHeight = containerHeight / pageHeight;
  const newScale = Math.max(0.5, Math.min(2.0, Math.min(scaleForWidth, scaleForHeight)));
  
  setScale(newScale);
};
```

**Calculation Examples**:
- **Fit Width**: 800px container - 64px padding = 736px / 612px page = **120% scale**
- **Fit Page**: Min(width scale, height scale) ensures entire page visible

**Test Coverage** (bd polyglot-pdf-840i): the original suite was largely
`expect(true)` placeholders documenting the scale math; 22 such stubs were removed.
What remains asserts real behavior: the Fit Width / Fit Page buttons render, manual
zoom changes the displayed percentage, AND -- by stubbing the scroll container's
`clientWidth`/`clientHeight` to non-zero values so the handlers run -- the fit MATH
and its 0.5..2.0 clamp are exercised with exact-percentage assertions (Fit Width
153% in-range / 200% upper-clamp / 50% lower-clamp; Fit Page 106% height-constrained
/ 104% width-constrained / 200% upper-clamp). So the scale-clamp calculation IS
covered under jsdom via mocked container dimensions -- not deferred to a real
browser. Run `npm run test:run` for the live count.

### Technical Decisions

1. **Padding Accounting**: Subtract 64px (p-8 = 32px × 2) from container dimensions
2. **First Page Reference**: Use page 1 dimensions for all calculations
3. **Bounds Clamping**: Respect 0.5 - 2.0 limits from Phase 1
4. **querySelector**: Find scroll container dynamically
5. **Safety Checks**: Graceful handling of missing refs and dimensions

### Files Modified

- `src/components/PDFViewer.tsx` (Added fit-width/fit-page logic)
- `src/components/PDFViewer.phase5.test.tsx` (de-stubbed under bd 840i: 22
  `expect(true)` placeholders removed, the real assertions kept/strengthened)

---

# API Reference

## Hooks

### `usePDFDocument(pdfUrl: string | null)`

Load and manage a PDF document.

**Parameters**:
- `pdfUrl` - URL to PDF file (null if no PDF selected)

**Returns**:
```typescript
{
  document: PDFDocumentProxy | null,
  numPages: number,
  isLoading: boolean,
  error: string | null
}
```

**Usage**:
```typescript
const { document, numPages, isLoading, error } = usePDFDocument('/path/to/pdf');
```

## Components

### `<PDFViewer>`

Render PDF with field overlays and navigation.

**Props**:
```typescript
interface PDFViewerProps {
  pdfPath: string;
  schema: FormSchema;
  selectedFieldId: string | null;
  onSelectField: (fieldId: string) => void;
}
```

**Features**:
- Multi-page vertical scrolling
- Zoom controls (50% - 200%)
- Fit Width / Fit Page presets
- Page navigation
- Field overlays with color-coded borders

### `<FieldList>`

Display fields grouped by section.

**Props**:
```typescript
interface FieldListProps {
  schema: FormSchema;
  selectedFieldId: string | null;
  onSelectField: (fieldId: string) => void;
}
```

**Features**:
- Section expand/collapse
- Status icons (🟢🟡🔴)
- Field selection
- Auto-scroll on selection

### `<FieldEditor>`

Edit properties of selected field.

**Props**:
```typescript
interface FieldEditorProps {
  field: FormField | null;
  schema: FormSchema;
  onUpdateField: (field: FormField) => void;
}
```

**Sections**:
- Basic Info
- Display
- Help & Guidance
- Validation Rules
- Options
- Conditional Logic

### `<ValidationPanel>`

Show completion progress and validation errors.

**Props**:
```typescript
interface ValidationPanelProps {
  schema: FormSchema;
  selectedFieldId: string | null;
}
```

**Metrics**:
- Progress percentage
- Complete count
- Needs review count
- Validation errors

## Utilities

### `pdfToScreenCoords(pdfRect, pageHeight, scale)`

Transform PDF coordinates to screen coordinates.

**Parameters**:
```typescript
pdfRect: { x: number, y: number, width: number, height: number }
pageHeight: number
scale: number = 1.0
```

**Returns**:
```typescript
{ x: number, y: number, width: number, height: number }
```

**Formula**:
- `screenX = pdfX * scale`
- `screenY = (pageHeight - pdfY - fieldHeight) * scale`
- `screenWidth = pdfWidth * scale`
- `screenHeight = pdfHeight * scale`

### `screenToPdfCoords(screenRect, pageHeight, scale)`

Transform screen coordinates to PDF coordinates (inverse operation).

**Parameters**:
```typescript
screenRect: { x: number, y: number, width: number, height: number }
pageHeight: number
scale: number = 1.0
```

**Returns**:
```typescript
{ x: number, y: number, width: number, height: number }
```

### `checkFieldComplete(field: FormField): FieldStatus`

Determine field completion status.

**Returns**:
```typescript
{
  isComplete: boolean,
  needsReview: boolean,
  errors: string[]
}
```

**Logic**:
- `isComplete`: All required properties + spoken_name + help text
- `needsReview`: Missing spoken_name or has placeholder help
- `errors`: Array of validation error messages

### `loadSchema(schemaPath: string): Promise<FormSchema>`

Load schema from JSON file.

**Parameters**:
- `schemaPath` - URL to schema JSON

**Returns**: Promise resolving to FormSchema

**Throws**: Error if fetch fails or JSON invalid

### `saveSchema(schema: FormSchema, filename: string): void`

Download schema as JSON file.

**Parameters**:
- `schema` - FormSchema to save
- `filename` - Name for downloaded file

**Side Effects**: Triggers browser download

---

## Support & Contributing

**Issues?** Open a GitHub issue with:
- Form you're working on
- Steps to reproduce
- Screenshots if possible
- Browser console errors

**Contributing**: See main project README for development setup.

---

**End of Guide**
