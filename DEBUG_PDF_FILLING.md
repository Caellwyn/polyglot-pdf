# PDF Filling Debug Guide

## Issue: PDF is blank after download/print

The backend PDF filling service exists and uses PyMuPDF. Let's debug why it's not working.

## Step 1: Check Browser Console

1. Open browser console (F12 → Console tab)
2. Fill in some form fields (name, email, etc.)
3. Click "Print Filled PDF" or "Download Filled PDF"
4. Look for these messages:

### Expected Frontend Logs:
```
[SchemaForm] Unwrapped field values for PDF filling: {
  original_count: 5,
  unwrapped_count: 5,
  sample: [
    ["p1_line3a_familyname", "Smith"],
    ["p1_line3b_givenname", "John"],
    ...
  ]
}
[pdfFiller] Calling backend to fill PDF: /form-kits/i-90/form.pdf kit: i-90
[pdfFiller] Backend URL: http://localhost:8000
[pdfFiller] Field values to fill: 5
[pdfFiller] Request URL: http://localhost:8000/api/fill-pdf
[pdfFiller] Response status: 200 OK
[pdfFiller] Received filled PDF: XXXXX bytes
```

### ⚠️ If you see this:
```
sample: [
  ["p1_line3a_familyname", {value: "Smith", confirmed: true}],  // ❌ BAD - not unwrapped
  ...
]
```
**Problem**: FieldValue objects not being unwrapped. Unwrapping failed.

### ⚠️ If you see this:
```
sample: [
  ["p1_line3a_familyname", null],  // ❌ BAD - all null
  ...
]
```
**Problem**: Field values are empty or not being saved to state.

## Step 2: Check Backend Logs

When you click Print/Download, your backend terminal should show:

### Expected Backend Logs:
```
pdf_fill_request kit=i-90 pdf=form.pdf field_count=5
pdf_fill_sample_values kit=i-90 sample={'p1_line3a_familyname': 'Smith', 'p1_line3b_givenname': 'John', ...}
pdf_loaded kit=i-90 pages=13
field_mappings_built kit=i-90 mapping_count=132
pdf_fill_start kit=i-90 total_values=5
processing_field kit=i-90 field_id=p1_line3a_familyname field_type=text has_value=True
...
fill_complete kit=i-90 filled=5 skipped=0 errors=0
pdf_generated kit=i-90 size_kb=XXX
```

### ⚠️ If you see this:
```
pdf_fill_request kit=i-90 pdf=form.pdf field_count=0
```
**Problem**: Backend receiving empty field_values. Frontend not sending data.

### ⚠️ If you see this:
```
fill_complete kit=i-90 filled=0 skipped=5 errors=0
```
**Problem**: Backend received data but couldn't fill any fields. Possible causes:
- Field values are null/empty
- pdf_field_name mappings don't match PDF
- Widget lookup failing

### ⚠️ If you see this:
```
field_not_in_schema kit=i-90 field_id=some_field
```
**Problem**: Schema doesn't contain the field ID being sent from frontend.

## Step 3: Manual Backend Test

Test the backend directly with curl:

```bash
curl -X POST http://localhost:8000/api/fill-pdf \
  -H "Content-Type: application/json" \
  -d '{
    "kit_id": "i-90",
    "pdf_filename": "form.pdf",
    "field_values": {
      "p1_line3a_familyname": "TestLastName",
      "p1_line3b_givenname": "TestFirstName"
    },
    "form_schema": {
      "fields": [
        {
          "id": "p1_line3a_familyname",
          "type": "text",
          "pdf_field_name": "P1_Line3a_FamilyName[0]"
        },
        {
          "id": "p1_line3b_givenname",
          "type": "text",
          "pdf_field_name": "P1_Line3b_GivenName[0]"
        }
      ]
    }
  }' \
  --output test-filled.pdf
```

Then open `test-filled.pdf` and check if the values appear.

## Step 4: Check Field Value Format

Add this to browser console to inspect current form state:

```javascript
// Get form state from sessionStorage
const state = JSON.parse(sessionStorage.getItem('schema_form_state'));
console.log('Current field values:', state.fieldValues);

// Check first field
const firstField = Object.entries(state.fieldValues)[0];
console.log('First field:', firstField);
console.log('Is wrapped?', typeof firstField[1] === 'object' && firstField[1].hasOwnProperty('value'));
```

### Expected Output:
```javascript
// If properly unwrapped:
First field: ["p1_line3a_familyname", "Smith"]
Is wrapped? false

// If still wrapped (BAD):
First field: ["p1_line3a_familyname", {value: "Smith", confirmed: true}]
Is wrapped? true
```

## Common Issues & Solutions

### Issue 1: Field values not saving
**Symptom**: `field_count=0` in backend logs
**Check**:
- Are you filling fields correctly?
- Does sessionStorage have data?
- Is SchemaFormStateManager saving properly?

### Issue 2: Values are wrapped objects
**Symptom**: Backend receives `{value: "X", confirmed: true}` instead of `"X"`
**Solution**: Frontend unwrapping not working. Check `unwrapFieldValue()` calls.

### Issue 3: PDF field names don't match
**Symptom**: `filled=0` but `field_count>0`
**Check**:
```bash
# Compare schema field names to actual PDF field names
cd form-kits/i-90
python3 -c "
import fitz
doc = fitz.open('form.pdf')
for page in doc:
    for widget in page.widgets():
        print(widget.field_name)
" | head -20
```

Then check if these match the `pdf_field_name` values in schema.json.

### Issue 4: Backend not running
**Symptom**: Frontend shows connection error
**Solution**:
```bash
cd backend
uvicorn main:app --reload --port 8000
```

## Next Steps

Please run Step 1 and Step 2, then share:
1. Browser console output (the full log messages)
2. Backend terminal output (when you click Print/Download)
3. Output from the JavaScript console commands in Step 4

This will tell us exactly where the problem is.
