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

## Adding New Forms

### 1. Extract with Automated Tool

```bash
cd pdf_schema_extractor
python automated_extractor.py path/to/form.pdf
```

Creates `form_draft_schema.json`

### 2. Add to Editor

Edit `schema-editor/src/utils/schemaLoader.ts`:

```typescript
{
  name: 'I-485 (Adjust Status)',
  pdfPath: '../pdf_schema_extractor/test_schemas/test_pdfs/i-485/i-485.pdf',
  schemaPath: '../pdf_schema_extractor/test_schemas/test_pdfs/i-485/i-485_draft_schema.json',
}
```

### 3. Edit in UI

1. Restart editor: `./scripts/run-schema-editor.sh`
2. Select new form from dropdown
3. Complete fields (~20-30 min)
4. Save

### 4. Validate

```bash
# Basic validation
python pdf_schema_extractor/compare_schemas.py \
  i-485_edited.json \
  i-485_draft_schema.json

# Advanced: Round-trip test (if available)
python pdf_schema_extractor/round_trip_tester.py i-485_edited.json
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

### Editor Won't Start

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

## Roadmap

### Phase 1: Core Editor ✅ (Complete)
- Field list with status
- Property editor
- Validation panel
- Form selector
- Save functionality

### Phase 2: PDF Integration (Next)
- Full PDF.js rendering
- Interactive field overlays
- Click fields on PDF to select
- Zoom and navigation

### Phase 3: Advanced Features
- **Undo/Redo** - Multi-level history
- **Bulk Operations** - Change type for selected fields
- **Field Consolidation** - Visual merge tool for groups
- **Drag-and-Drop** - Reorder fields in list
- **Templates** - Help text patterns for common fields
- **Conditional Graph** - Visual dependency map
- **Export Formats** - JSON, CSV, Excel

### Phase 4: Gemini Integration
- **Auto-complete help text** - AI suggestions
- **Smart grouping** - AI-detected field groups
- **Type inference** - Better field type detection
- **Validation suggestions** - AI-suggested patterns

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
**Last Updated:** November 5, 2025
**Status:** MVP Complete, PDF integration in progress
