# PDF Schema Editor

Visual editor for PDF form schemas - makes human correction of extracted schemas fast and pleasant!

## Features

✅ **Visual PDF Viewer** - See the actual form with field overlays
✅ **Field List** - Tree view with completion status (complete/review/error)
✅ **Property Editor** - Edit field types, help text, validation, conditional logic
✅ **Real-time Validation** - Instant feedback on schema errors
✅ **Form Selector** - Switch between different PDF/schema pairs
✅ **Progress Tracking** - See completion percentage at a glance
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

## Adding New Forms

Edit `src/utils/schemaLoader.ts` and add to `AVAILABLE_FORMS`:

```typescript
{
  name: 'Your Form Name',
  pdfPath: '../pdf_schema_extractor/test_schemas/test_pdfs/your-form/form.pdf',
  schemaPath: '../pdf_schema_extractor/test_schemas/test_pdfs/your-form/schema.json',
}
```

## Tech Stack

- **React 18** + **TypeScript**
- **Vite** - Fast build tool
- **TailwindCSS** - Utility-first styling
- **PDF.js** - PDF rendering (coming soon)

## Development

```bash
npm run dev      # Start dev server
npm run build    # Build for production
npm run preview  # Preview production build
```

## Known Limitations

- PDF viewer is currently a placeholder (PDF.js integration coming)
- Field overlays are not yet interactive with actual PDF
- No undo/redo (browser back button works)

## Future Enhancements

- Full PDF.js integration with clickable field overlays
- Drag-and-drop field reordering
- Bulk operations (change type for multiple fields)
- Field consolidation tool (merge checkbox groups into radio)
- Conditional logic visual graph
- Template system for help text
- Export to multiple formats

## Support

Questions? Check the main project README or open an issue.
