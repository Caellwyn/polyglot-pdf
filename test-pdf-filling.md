# PDF Filling Debugging Guide

## Changes Made

### 1. Moved PDF Download Button Outside Form (SchemaForm.tsx)
- **Line 450-465**: PDF download section moved outside `</form>` tag
- **Why**: Being inside the form could cause hiding or submission conflicts

### 2. Added FieldValue Unwrapping (SchemaForm.tsx)
- **Line 21**: Import `unwrapFieldValue` utility
- **Line 345-349**: Unwrap FieldValue objects before sending to backend
- **Why**: Backend expects raw values like `"John"`, not wrapper objects like `{value: "John", confirmed: true}`

## Testing Steps

### Step 1: Restart Development Server
```bash
# Stop current server (Ctrl+C)
cd frontend
npm run dev:schema
```

### Step 2: Open Browser and Check
1. Go to `http://localhost:5176/schema-form-demo.html`
2. Select "I-90" from dropdown
3. Fill in some fields (e.g., name, email, checkbox)
4. Scroll to the VERY BOTTOM of the page
5. You should see a blue button: "📄 Download Filled PDF"

### Step 3: Test Download
1. Click the blue download button
2. Open browser console (F12 → Console tab)
3. Look for these log messages:
   ```
   [SchemaForm] Unwrapped field values for PDF filling: {...}
   [pdfFiller] Calling backend to fill PDF: ...
   [pdfFiller] Response status: 200 OK
   [pdfFiller] Received filled PDF: XXXXX bytes
   [pdfFiller] Downloaded PDF: I-90-filled-2025-11-20.pdf
   ```

### Step 4: Check Downloaded PDF
1. Find the downloaded PDF (usually in Downloads folder)
2. Open it
3. Your field values should be visible

## Debugging If Button Still Not Visible

### Check 1: Is the pdfUrl prop being passed?
Open console and type:
```javascript
// Check if PDF URL is set
document.querySelector('.schema-form__pdf-download')
```
- If null: pdfUrl prop is not being passed to SchemaForm
- If element exists: CSS might be hiding it

### Check 2: Inspect element
1. Right-click near bottom of form
2. "Inspect Element"
3. Look for `<div class="schema-form__pdf-download">`
4. Check if it has `display: none` or is being hidden

### Check 3: Console errors
Look for errors in console mentioning:
- "pdfUrl"
- "SchemaForm"
- "Cannot read property"

## Debugging If PDF is Still Blank

### Check Backend Logs
When you click download, check backend terminal for:
```
pdf_fill_request kit=i-90 pdf=form.pdf field_count=XX
field_mappings_built kit=i-90 mapping_count=XX
fill_complete kit=i-90 filled=XX skipped=XX errors=0
```

### Check Frontend Console Logs
Look for:
```
[SchemaForm] Unwrapped field values for PDF filling: {
  original_count: 5,
  unwrapped_count: 5,
  sample: [["field1", "value1"], ...]
}
```

If `sample` shows objects like `[["field1", {value: "test"}]]`, unwrapping failed.

### Check Backend Field Mappings
The backend needs `pdf_field_name` in the schema for each field.

Run this to check:
```bash
cd frontend/public/form-kits/i-90
cat schema.json | grep -A 5 "pdf_field_name" | head -20
```

Should see entries like:
```json
"pdf_field_name": "P1_line1a_AlienNumber"
```

## Common Issues

1. **Old build cached**: Hard refresh (Ctrl+Shift+R)
2. **Server not restarted**: Stop and restart `npm run dev:schema`
3. **Wrong URL**: Should be port 5176, not 5174 or 5173
4. **Backend not running**: Start backend with `uvicorn main:app --reload`

## If Nothing Works

Share these outputs:
1. Browser console logs when clicking download
2. Backend terminal output when download is clicked
3. Result of: `ls frontend/public/form-kits/i-90/`
4. Current URL you're accessing
