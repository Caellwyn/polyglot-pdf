# PDF Schema Editor - Complete Guide

**Visual editor for PDF form schemas - built for human-in-the-loop schema extraction**

---

## Why This Exists

Manual JSON editing of PDF schemas is **painful and error-prone**. With 50+ forms to extract and 132+ fields per form, we needed a tool that makes human correction:
- **Fast** (~30 min vs 2-4 hours per form)
- **Visual** (see the PDF + fields side-by-side)
- **Safe** (real-time validation catches errors)
- **Pleasant** (no more scrolling through JSON)

---

## The Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                    EXTRACTION PIPELINE                       │
└─────────────────────────────────────────────────────────────┘

1. EXTRACT (Automated - 75-80% complete)
   ├─→ python automated_extractor.py form.pdf
   └─→ Output: form_draft_schema.json

2. EDIT (Human Review - 20-30 min)
   ├─→ ./scripts/run-schema-editor.sh
   ├─→ Fix field types (radio/checkbox/text)
   ├─→ Add help text + validation
   ├─→ Define conditional logic
   └─→ Save: form_final_schema.json

3. VALIDATE (Automated - < 1 min)
   ├─→ python compare_schemas.py draft.json final.json
   └─→ 100% validation pass rate required

4. DEPLOY
   └─→ Copy to backend/schemas/
```

---

## Quick Start

### Launch the Editor

```bash
# From project root
./scripts/run-schema-editor.sh
```

Opens at http://localhost:3001

### Select a Form

1. Choose from dropdown (I-90, I-589, etc.)
2. PDF loads on left, fields in center, properties on right
3. Validation panel at bottom shows progress

### Edit Fields

**Click any field** in the list or PDF to edit:

- **Field Type** - Change text/radio/checkbox/etc.
- **Spoken Name** - User-friendly name for voice AI
- **Help Text** - Instructions for users
- **Validation** - Patterns, formats, constraints
- **Conditional Logic** - show_if rules

### Save Your Work

- **Cmd+S** (Mac) or **Ctrl+S** (Windows/Linux)
- Downloads as `{form}_edited.json`
- Copy to appropriate location

---

## Interface Guide

### Layout

```
┌──────────────────────────────────────────────────────────────┐
│ Header: Form Selector | Save Button                          │
├─────────────┬─────────────┬──────────────────────────────────┤
│             │             │                                  │
│ PDF VIEWER  │ FIELD LIST  │   FIELD EDITOR                   │
│             │             │                                  │
│ - Zoom      │ ⊞ Part 1    │   Field Type: [text ▼]          │
│ - Navigate  │   ● field1  │   Spoken Name: ___________      │
│ - Overlays  │   ● field2  │   Section: [Part 1 ▼]          │
│             │   ○ field3  │   ☐ Required ☐ Read Only       │
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

### Field Status Icons

- 🟢 **Complete** - All required info filled
- 🟡 **Needs Review** - Missing help text or spoken name
- 🔴 **Error** - Missing required properties

### Keyboard Shortcuts

- **Cmd/Ctrl + S** - Save schema
- **Arrow Keys** - Navigate fields (coming soon)
- **Escape** - Deselect field (coming soon)

---

## Common Tasks

### Fix Field Types

Many fields are initially detected incorrectly:

1. Select field in list
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

**Templates coming soon:** Common patterns like A-numbers, SSNs, dates

### Define Conditional Logic

For fields that only show based on another field:

1. Select the dependent field
2. Scroll to "Conditional Logic"
3. Click "+ Add Conditional Logic"
4. Select trigger field from dropdown
5. Choose operator (equals, is_checked, etc.)
6. Enter expected value

**Example:** "Family name on card" only shows if "Name changed" = Yes

### Consolidate Checkbox Groups

Some forms have checkbox groups that should be radio buttons:

**Manual Method (for now):**
1. Note all checkboxes in group (e.g., P2_checkbox1[0-2])
2. Delete extra checkboxes
3. Change remaining to type: radio
4. Add options manually

**Coming Soon:** Visual consolidation tool

---

## Validation & Quality

### Real-Time Validation

Bottom panel shows:
- **Progress bar** - % of fields complete
- **Status counts** - Complete/Review/Total
- **Errors** - Schema validation issues
- **Warnings** - Field reference issues

### Before Deploying

Run comparison against gold standard (if available):

```bash
python pdf_schema_extractor/compare_schemas.py \
  your_edited_schema.json \
  gold_standard_schema.json
```

Target metrics:
- ✅ Field coverage: 95%+
- ✅ Type accuracy: 95%+
- ✅ No validation errors
- ✅ No broken references

---

## Setup & Installation

### First Time Setup

The schema editor requires the schema and PDF files to be available in its `public/schemas/` folder.

**Automated Setup** (Recommended):
```bash
# From project root
./scripts/run-schema-editor.sh
```

The script will:
1. Install npm dependencies if needed
2. Start the dev server at http://localhost:3001

**Manual Setup**:
```bash
cd schema-editor
npm install

# Copy schema files to public folder
mkdir -p public/schemas/i-90 public/schemas/i-589
cp ../pdf_schema_extractor/test_schemas/test_pdfs/i-90/*.{json,pdf} public/schemas/i-90/
cp ../pdf_schema_extractor/test_schemas/test_pdfs/i-589/*.{json,pdf} public/schemas/i-589/

# Start dev server
npm run dev
```

### Adding New Forms

When adding a new form to the editor:

1. **Extract with Automated Tool**:
```bash
cd pdf_schema_extractor
python automated_extractor.py path/to/form.pdf
```

2. **Copy files to public folder**:
```bash
mkdir -p schema-editor/public/schemas/your-form
cp pdf_schema_extractor/test_schemas/test_pdfs/your-form/*.{json,pdf} schema-editor/public/schemas/your-form/
```

3. **Update schemaLoader.ts**:
Edit `schema-editor/src/utils/schemaLoader.ts` and add to `AVAILABLE_FORMS`:

```typescript
{
  name: 'Your Form Name',
  pdfPath: '/schemas/your-form/form.pdf',
  schemaPath: '/schemas/your-form/schema.json',
}
```

4. **Restart the dev server** to see the new form in the dropdown.

5. **Edit in UI**:
   - Select new form from dropdown
   - Complete fields (~20-30 min)
   - Save with Cmd+S

6. **Validate**:
```bash
# Basic validation
python pdf_schema_extractor/compare_schemas.py \
  your-form_edited.json \
  your-form_draft_schema.json
```

---

## Tips & Best Practices

### Efficient Editing

1. **Sort by status** - Fix errors first, then reviews, then complete
2. **Use templates** - Copy help text from similar fields
3. **Batch edits** - Group similar fields, edit properties together
4. **Save often** - Cmd+S is your friend

### Help Text Guidelines

**Good:**
> "Your alien registration number (A-Number) is a 7-9 digit number found on your green card. It begins with an 'A'."

**Bad:**
> "[TODO: Add help text for alien registration number]"

### Validation Patterns

Common patterns:
- **A-Number:** `^\d{7,9}$`
- **SSN:** `^\d{3}-?\d{2}-?\d{4}$`
- **Date:** Various - use format_preset instead
- **Email:** Built-in browser validation
- **Phone:** `^\d{10}$` or `^\(\d{3}\) \d{3}-\d{4}$`

### Conditional Logic

Keep it simple:
- **One trigger per field** - Multiple triggers get complex fast
- **Test your logic** - Fill out a form to verify show_if works
- **Document edge cases** - Add notes in help text

---

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

### Editor Won't Start - Clean Install

```bash
# Clean install
cd schema-editor
rm -rf node_modules package-lock.json
npm install
npm run dev
```

### PDF Won't Load

PDF.js integration is not yet complete. You'll see a placeholder. This doesn't affect editing - use the field list to navigate.

### Changes Not Saving

- Check browser console for errors
- Verify you clicked "Save" or pressed Cmd+S
- Check Downloads folder for `_edited.json` file

### Validation Errors

Red errors in validation panel indicate schema issues:
- **Duplicate IDs** - Field IDs must be unique
- **Missing sections** - Field references non-existent section
- **Broken references** - show_if or controls_fields reference missing field

Fix by:
1. Click on error to see field ID
2. Find field in list
3. Fix the property causing issue

---

## Tech Stack

### Frontend
- **React 18.3** - UI framework
- **TypeScript** - Type safety
- **Vite** - Fast build tool
- **TailwindCSS** - Utility-first styling

### PDF Rendering (Coming Soon)
- **PDF.js** - Mozilla's PDF renderer
- Interactive field overlays
- Click-to-select

### Validation
- Real-time schema validation against form_models.py
- Reference integrity checking
- Completion tracking

---

## Current Status & Roadmap

### ✅ Phase 1: PDF.js Core Setup (Complete - Nov 5, 2025)
**Status**: PDF document loading and basic rendering working

**Completed Features**:
- ✅ PDF.js worker configuration with Vite/ES modules
- ✅ usePDFDocument hook for document lifecycle management
- ✅ PDFPage component for canvas-based rendering
- ✅ Zoom controls (50% - 200%, +/- buttons)
- ✅ Loading states and error handling
- ✅ Static toolbar with controls
- ✅ Comprehensive test suite (19 tests passing)

**Technical Implementation**:
- PDF.js v4.0.379 with ES modules
- Canvas-based rendering
- React hooks for state management
- Vitest + React Testing Library

**Documentation**: See `PHASE1_SUMMARY.md`

---

### ✅ Phase 2: Multi-Page Support (Complete - Nov 5, 2025)
**Status**: All pages render with full navigation

**Completed Features**:
- ✅ Render all PDF pages vertically (not just first page)
- ✅ Page navigation controls (prev/next buttons)
- ✅ Page number input with validation
- ✅ Current page indicator ("Page X of Y")
- ✅ Auto-scroll to field's page when selected
- ✅ Page number overlays on each page
- ✅ Scroll-based page tracking
- ✅ 15 new tests (34 total tests passing)

**User Experience**:
- Select field in list → PDF auto-scrolls to that page
- Use ← → buttons for quick page navigation
- Type page number to jump directly
- See all 9 pages of I-90 form at once

**Documentation**: See `PHASE2_SUMMARY.md`

---

### ✅ Schema Editor MVP (Complete)
**Status**: Fully functional schema editor (original Phase 1)

**Completed Features**:
- ✅ Field list with section grouping and status icons (complete/review/error)
- ✅ Property editor for all field types
- ✅ Real-time validation panel with progress tracking
- ✅ Form selector dropdown for multiple schemas
- ✅ Save functionality (Cmd+S to download edited JSON)
- ✅ Keyboard shortcuts (Cmd+S, unsaved changes warning)
- ✅ Conditional logic editor (show_if)
- ✅ Help text and validation rules editor
- ✅ Options editor for select/radio fields
- ✅ All field types supported: text, textarea, date, number, tel, email, select, radio, checkbox, signature

**Technical Stack**:
- React 18.3 + TypeScript
- Vite 5.4.1 (fast dev server with ES modules)
- TailwindCSS 3.4.13 (styling)
- Files served from `public/schemas/` folder

---

### ✅ Phase 3: Field Overlays (Complete - Nov 5, 2025)
**Status**: Color-coded field overlays render on PDF

**Completed Features**:
- ✅ Color-coded borders over PDF fields (Green/Yellow/Red)
- ✅ PDF coordinate transformation (`pdfCoordinates.ts`)
- ✅ FieldOverlay component with status-based colors
- ✅ Hover tooltips showing field name and type
- ✅ Correct positioning with Y-axis inversion
- ✅ Dynamic updates when zooming
- ✅ Thicker border for selected fields
- ✅ 39 new tests (22 coordinate + 17 overlay)
- ✅ 73 total tests passing

**Color Coding**:
- 🟢 Green: Complete (all required info filled)
- 🟡 Yellow: Needs review (missing help text or spoken name)
- 🔴 Red: Has errors (missing required properties)

**Technical Implementation**:
- Y-axis inversion: `screenY = (pageHeight - pdfY - fieldHeight) * scale`
- Per-page overlay rendering with dimension tracking
- Existing `checkFieldComplete()` for status determination
- Absolute positioning over PDF canvas

**Documentation**: See `PHASE3_SUMMARY.md`

---

### 🚧 Next Development Priorities

#### 1. **Phase 4: Click-to-Select Fields** (Upcoming)
**Goal**: Make field overlays clickable

**Features**:
- Click overlay → Select field in editor
- Highlight selected field with thicker border
- Hover effects (pointer cursor, lighter border)
- Sync: Click in list → Scroll PDF, Click PDF → Update list
- Keyboard navigation (arrows to cycle fields)

---

#### 3. **Phase 5: Zoom Presets** (Upcoming)
**Goal**: Implement functional zoom presets

**Features**:
- Fit Width: Scale to container width
- Fit Page: Scale entire page to fit height
- Maintain scroll position on zoom changes
- Update overlay positions on zoom

---

#### 4. **Phase 6: Polish & Performance** (Upcoming)
**Goal**: Production-ready with great UX

**Features**:
- Keyboard shortcuts (+ / - for zoom, arrows for pages)
- Debounce zoom changes
- Throttle scroll events
- Virtual scrolling for large PDFs (if needed)
- Responsive layout
- Comments and documentation

---

#### 7. **Update Extractor Field Ordering** (Backlog)
**Goal**: Improve field order parsing to handle alphabetic labels

**Change**: Update label parsing regex in extractor from `\d+\.` to `(\d+|[A-Z])\.`

**Why**: Some forms use mixed numbering (1., 2., A., B., etc.)

**Files to Update**:
- `pdf_schema_extractor/extract_field_order_from_labels.py`
- Test with forms that have alphabetic section labels

---

#### 8. **Drag-and-Drop Field Reordering** (Backlog)
**Goal**: Allow users to reorder fields within sections via drag-and-drop

**Features**:
- Visual drag handle on each field in the list
- Drag fields within same section
- Auto-update `question_number` or field order
- Save updated order to schema

**Libraries to Consider**:
- `@dnd-kit/core` (modern, accessible)
- `react-beautiful-dnd` (popular, well-documented)

**UX Considerations**:
- Only allow reordering within same section
- Visual feedback during drag
- Persist order in schema structure

---

#### 4. **Bulk Operations** (Medium Priority)
**Goal**: Edit multiple fields at once

**Features**:
- Multi-select fields (Cmd+Click, Shift+Click)
- Bulk actions:
  - Change field type for all selected
  - Set required/read-only flags
  - Apply validation pattern to all
  - Copy help text to selected fields
  - Move to different section
- Selection toolbar with action buttons
- Confirmation dialogs for destructive changes

**UX Design**:
- Checkbox selection mode toggle
- "Select All in Section" button
- Clear selection button
- Action menu with common operations

---

#### 5. **Templates - Common Help Text Patterns** (Medium Priority)
**Goal**: Speed up help text entry with pre-written templates

**Features**:
- Template library for common field types:
  - A-Number (alien registration number)
  - SSN (social security number)
  - Date fields (various formats)
  - Phone numbers
  - Email addresses
  - Names (given, middle, family)
  - Addresses (US and international)
- Template selector in help text editor
- One-click insert with customization
- User can save custom templates

**Template Structure**:
```typescript
interface HelpTemplate {
  name: string;
  category: string; // 'identification', 'contact', 'address', etc.
  instructions: string;
  format_hint?: string;
  validation_pattern?: string;
}
```

**Storage**:
- Built-in templates in JSON file
- User templates in localStorage

---

#### 6. **Gemini Integration - AI-Suggested Help Text** (Future)
**Goal**: Use AI to generate help text suggestions

**Features**:
- Analyze field name, type, and PDF label
- Generate contextual help text suggestions
- Multiple suggestions to choose from
- User can edit before accepting
- Learn from user edits to improve suggestions

**API Integration**:
- Call Gemini API with field context
- Prompt: "Generate help text for field: {name}, type: {type}, label: {label}"
- Stream response for real-time preview
- Rate limiting and error handling

**Privacy Considerations**:
- Only send field metadata (name, type, label)
- Never send user data from filled forms
- Optional feature (can be disabled)

---

#### 7. **Undo/Redo - Multi-Level History** (Future)
**Goal**: Allow users to undo/redo changes

**Features**:
- Multi-level undo/redo (20+ steps)
- Keyboard shortcuts: Cmd+Z (undo), Cmd+Shift+Z (redo)
- Visual history timeline (optional)
- Undo/redo buttons in header
- State snapshot on each change

**Implementation**:
- History stack in React state
- Immutable state updates
- Snapshot entire schema on change
- Memory-efficient (limit history depth)

**Technical Approach**:
- Use `useReducer` with history middleware
- Libraries: `use-undo` or custom implementation

---

### 📋 Future Enhancements (Backlog)

- **Field Consolidation Tool** - Visual merge for checkbox groups → radio
- **Conditional Logic Graph** - Visual dependency map
- **Export Formats** - CSV, Excel export for bulk editing
- **Import Formats** - Import from CSV/Excel
- **Schema Diff Viewer** - Compare two versions of a schema
- **Real-time Collaboration** - Multiple users editing simultaneously
- **Field Search** - Search by name, type, or content
- **Validation Rules Builder** - Visual regex pattern builder
- **Keyboard Navigation** - Arrow keys to navigate fields
- **Field Preview** - Show how field will render in form
- **Dark Mode** - UI theme toggle
- **Accessibility Improvements** - WCAG 2.1 AA compliance

---

### 🐛 Known Issues & Limitations

**Current Limitations**:
- PDF viewer is placeholder (no actual PDF rendering yet)
- No undo/redo functionality
- No bulk operations
- No drag-and-drop reordering
- No field search/filter
- Changes are local only (no server sync)

**Browser Compatibility**:
- Tested on Chrome/Edge (Chromium-based)
- Should work on Firefox and Safari
- Not tested on mobile browsers

**Performance**:
- Handles schemas with 200+ fields smoothly
- Large schemas (500+ fields) may have minor lag
- PDF rendering performance TBD (depends on PDF.js integration)

---

## FAQ

**Q: Can I edit the gold standard schemas?**
A: Yes! Select "Gold Standard" versions from dropdown to refine existing work.

**Q: Will my changes sync across team?**
A: Not yet - save and commit to git for now. Real-time collaboration coming later.

**Q: Can I import from Excel/CSV?**
A: Not yet, but it's on the roadmap. For now, use automated_extractor.py.

**Q: How do I test my schema works with the voice AI?**
A: Round-trip testing tool coming soon. For now, manually test filling the form.

**Q: Can I use this for non-USCIS forms?**
A: Yes! Any PDF form works. Just extract with automated_extractor.py and add to editor.

---

## Support

**Issues?** Open a GitHub issue with:
- Form you're working on
- Steps to reproduce
- Screenshots if possible
- Browser console errors

**Questions?** Check:
1. This guide
2. `schema-editor/README.md`
3. `pdf_schema_extractor/EXTRACTION_RESULTS.md`
4. Code comments

---

## Contributing

See main project README for development setup.

Key areas:
- PDF.js integration (help wanted!)
- Bulk operations UI
- Template system
- Undo/Redo implementation

---

**Version:** 1.0.0  
**Last Updated:** November 4, 2025  
**Status:** MVP Complete - Core editing functionality working  
**Next Priority:** Field ordering regex update, then drag-and-drop reordering
