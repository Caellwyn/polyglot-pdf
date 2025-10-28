# Quick Reference: What Needs to Change

## The Big Three Issues 🎯

### Issue #1: Field IDs
**Current:** `form1__subform_PtAILine1_ANumber`  
**Need:** `part_a_i_a_number`

### Issue #2: Section IDs  
**Current:** `section_1`, `section_2`  
**Need:** `part_a_i`, `part_b_questions`

### Issue #3: Field Count
**Current:** 281 fields (too many!)  
**Need:** ~156 fields (filter barcodes, group radio buttons, create tables)

---

## Code Changes Needed in `extractor.py`

### 1. Add Missing Import (Line 9)
```python
from .models import (
    FormSchema,
    FormField,
    PDFPosition,
    FormMetadata,
    ExtractionInfo,
    FormSource,
    FieldType,
    FormSection,
    FormPart,
    FormSupplement,
    FieldOption,
    GroupKind,  # ← ADD THIS LINE
)
```

### 2. Fix Section ID Generation (Around Line 61)
**Replace:**
```python
section_id = f"section_{section_order}"
```

**With:**
```python
section_id = generate_semantic_section_id(full_line_text)
```

**Add New Function:**
```python
def generate_semantic_section_id(section_label):
    """Generate semantic section ID from label."""
    label_lower = section_label.lower()
    
    # Extract Part A.I, Part A.II, etc.
    match = re.match(r'part ([a-g])(\.([ivx]+))?', label_lower)
    if match:
        part = match.group(1)
        subsection = match.group(3) if match.group(3) else ""
        
        if subsection:
            # Part A.I → part_a_i
            return f"part_{part}_{subsection}"
        
        # Part D: Your Signature → part_d_signature
        if "signature" in label_lower:
            return f"part_{part}_signature"
        elif "declaration" in label_lower:
            return f"part_{part}_declaration"
        elif "interview" in label_lower:
            return f"part_{part}_interview"
        elif "hearing" in label_lower:
            return f"part_{part}_hearing"
        elif "question" in label_lower or "application" in label_lower:
            return f"part_{part}_questions"
        
        return f"part_{part}"
    
    # Supplements
    if "supplement a" in label_lower:
        return "supplement_a_section"
    elif "supplement b" in label_lower:
        return "supplement_b_section"
    
    return f"section_{hash(section_label) % 1000}"
```

### 3. Fix Field ID Generation (Around Line 152)
**Replace:**
```python
clean_id = re.sub(r'\[\d+\]', '', field.field_name)
clean_id = re.sub(r'[^a-zA-Z0-9_-]', '_', clean_id)
clean_id = clean_id.strip('_')
```

**With:**
```python
clean_id = generate_semantic_field_id(
    field.field_label or field.field_name,
    final_section_id
)
```

**Add New Function:**
```python
def generate_semantic_field_id(field_label, section_id):
    """Generate semantic field ID from label and section."""
    # Start with section ID
    base = section_id
    
    # Clean the label
    label = field_label.lower()
    
    # Remove common prefixes
    label = re.sub(r'^part\.?\s+[a-g]\.?\s+\d+\.?.*?\d+\.?\s+', '', label)
    label = re.sub(r'^(enter|provide|list|specify)\s+', '', label)
    
    # Extract key terms
    if 'a-number' in label or 'alien registration' in label:
        field_key = 'a_number'
    elif 'social security' in label or 'ssn' in label:
        field_key = 'ssn'
    elif 'uscis online account' in label:
        field_key = 'uscis_online_account_number'
    elif 'last name' in label:
        field_key = 'last_name'
    elif 'first name' in label:
        field_key = 'first_name'
    elif 'middle name' in label:
        field_key = 'middle_name'
    # ... add more patterns
    else:
        # Fallback: use sanitized label
        field_key = re.sub(r'[^a-z0-9]+', '_', label).strip('_')
        field_key = field_key[:50]  # Limit length
    
    return f"{base}_{field_key}"
```

### 4. Clean Field Names (Around Line 154)
**Add After field type detection:**
```python
clean_name = clean_field_name(field.field_label or field.field_name)
spoken_name = generate_spoken_name(clean_name)
```

**Add New Functions:**
```python
def clean_field_name(tooltip_text):
    """Extract clean field name from PDF tooltip."""
    # Remove part/section prefix
    text = re.sub(r'^Part\.?\s+[A-G]\.?\s+\d+\.?.*?\d+\.?\s+', '', tooltip_text)
    
    # Remove instruction verbs
    text = re.sub(r'^(Enter|Provide|List|Specify)\s+', '', text, flags=re.IGNORECASE)
    
    # Clean up
    text = text.strip('. ')
    
    return text

def generate_spoken_name(field_name):
    """Generate concise spoken name for voice UI."""
    # Extract content in parentheses that might be abbreviations
    paren_match = re.search(r'\(([A-Z]-?[A-Za-z]+)\)', field_name)
    if paren_match:
        abbrev = paren_match.group(1)
        # "Alien Registration Number (A-Number)" → "A-Number"
        return abbrev
    
    # Otherwise use the first few key words
    words = field_name.split()
    if len(words) <= 3:
        return field_name
    
    # Take first 3 words
    return ' '.join(words[:3])
```

### 5. Filter Non-User Fields (Around Line 138)
**Add Before Creating FormField:**
```python
# Skip barcode fields
if 'barcode' in field.field_name.lower():
    continue

# Skip hidden fields
if field.field_flags & (1 << 1):  # Hidden flag
    continue
```

### 6. Update FormField Creation (Around Line 154)
**Replace:**
```python
form_field = FormField(
    id=clean_id,
    name=field.field_label or field.field_name,
    spoken_name=field.field_label or field.field_name,
    type=field_type,
    options=options,
    pdf_position=PDFPosition(...),
    pdf_field_name=field.field_name,
    section_id=final_section_id,
    section_label=field_section_label.replace("(continued)", "").strip(),
)
```

**With:**
```python
# Extract attributes
clean_name = clean_field_name(field.field_label or field.field_name)
spoken_name = generate_spoken_name(clean_name)
help_text = extract_help_text(field.field_label or field.field_name)
validation = infer_validation(clean_name, field_type)

form_field = FormField(
    id=clean_id,
    name=clean_name,
    spoken_name=spoken_name,
    type=field_type,
    options=options,
    help=help_text,
    validation=validation,
    pdf_position=PDFPosition(...),
    pdf_field_name=field.field_name.split('[0]')[0],  # Clean PDF name
    section_id=final_section_id,
)
```

**Add Helper Functions:**
```python
def extract_help_text(field_label):
    """Extract help text from parentheses."""
    match = re.search(r'\(([^)]+)\)', field_label)
    if match:
        help = match.group(1)
        # Only include if it's actually helpful
        if help.lower() in ['if any', 'if applicable', 'optional']:
            return {'inline': help}
    return None

def infer_validation(field_name, field_type):
    """Infer validation rules from field name and type."""
    name_lower = field_name.lower()
    validation = {}
    
    # Format presets
    if 'social security' in name_lower or 'ssn' in name_lower:
        validation['format_preset'] = 'ssn'
    elif 'a-number' in name_lower or 'alien registration' in name_lower:
        validation['format_preset'] = 'a_number'
    elif 'zip' in name_lower:
        validation['format_preset'] = 'zip'
    
    # Required status (default to false, could check PDF flags)
    validation['required'] = False
    
    return validation if validation else None
```

### 7. Fix Metadata Extraction (Around Line 235)
**Replace:**
```python
metadata = doc.metadata
form_metadata = FormMetadata(
    title=metadata.get("title", pdf_path),
    version="1.0",
    page_count=doc.page_count,
)
```

**With:**
```python
form_metadata = extract_complete_metadata(doc)
```

**Add Function:**
```python
def extract_complete_metadata(doc):
    """Extract comprehensive form metadata."""
    metadata = doc.metadata
    first_page = doc[0]
    text = first_page.get_text()
    
    # Extract title
    title = metadata.get("title", "")
    
    # Extract form number from title
    form_number = None
    match = re.search(r'(I-\d+)', title)
    if match:
        form_number = match.group(1)
        # Clean title
        title = title.replace(f"Form {form_number}, ", "")
    
    # Extract OMB number
    omb_match = re.search(r'OMB No\.?\s+(\d+-\d+)', text)
    omb_number = omb_match.group(1) if omb_match else None
    
    # Extract dates (look for common patterns)
    edition_match = re.search(r'Edition Date\s+(\d{2}/\d{2}/\d{4})', text)
    edition_date = edition_match.group(1) if edition_match else None
    
    expires_match = re.search(r'Expires\s+(\d{2}/\d{2}/\d{4})', text)
    expiration_date = expires_match.group(1) if expires_match else None
    
    # Agency (often in header/footer)
    agency = None
    if 'U.S. Citizenship and Immigration Services' in text:
        agency = 'U.S. Citizenship and Immigration Services'
    elif 'USCIS' in text:
        agency = 'U.S. Citizenship and Immigration Services'
    
    return FormMetadata(
        title=title,
        form_number=form_number,
        edition_date=edition_date,
        expiration_date=expiration_date,
        omb_number=omb_number,
        page_count=doc.page_count,
        agency=agency,
        language="en"
    )
```

---

## Testing After Changes

```bash
cd pdf_schema_extractor
python run_extraction_test.py
python compare_schemas.py
```

**Expected Results After Fixes:**
- Field count: ~156 (down from 281)
- Section IDs: All match expected format
- Field IDs: 90%+ match expected format
- Metadata: All 8 fields populated

---

## Priority Order

1. ✅ Add missing `GroupKind` import
2. ✅ Fix section ID generation
3. ✅ Fix field ID generation  
4. ✅ Clean field names
5. ✅ Filter barcode fields
6. ✅ Extract complete metadata
7. ✅ Add help text extraction
8. ✅ Add validation rules

**Estimated Total Time:** 12-16 hours
